use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::sync::mpsc;
use std::sync::mpsc::SyncSender;
use std::thread;
mod backend;
mod gpu_pipeline;
mod shell_backend;
mod wayland_gl_backend;

use backend::RenderBackend;
use shell_backend::ShellBackend;
#[cfg(feature = "wayland_gl")]
use wayland_gl_backend::WaylandGlBackend;

#[derive(Debug, Deserialize)]
struct Request {
    cmd: String,
    workspace: Option<u32>,
    path: Option<String>,
    mode: Option<String>,
    transition: Option<Transition>,
    shader_preset: Option<String>,
    transition_type: Option<String>,
    transition_duration: Option<f32>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
struct Transition {
    #[serde(rename = "type")]
    kind: Option<String>,
    duration: Option<f32>,
}

#[derive(Debug, Serialize)]
struct Response {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    service: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    gl: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    details: Option<String>,
}

#[derive(Debug, Clone)]
struct WorkspaceSettings {
    path: String,
    mode: String,
    transition_type: String,
    transition_duration: f32,
    shader_preset: String,
}

struct RendererState {
    workspaces: HashMap<u32, WorkspaceSettings>,
    backend: Box<dyn RenderBackend>,
    transition_type: String,
    transition_duration: f32,
    shader_preset: String,
    last_async_error: Option<String>,
    last_apply_ok: bool,
    queued_jobs: u64,
    applied_jobs: u64,
    failed_jobs: u64,
    dropped_jobs: u64,
}

struct WorkerRequest {
    request: Request,
    response_tx: Option<mpsc::Sender<Response>>,
}

const WORKER_QUEUE_CAPACITY: usize = 128;

impl RendererState {
    fn new() -> Self {
        Self {
            workspaces: HashMap::new(),
            backend: backend_from_env(),
            transition_type: "wipe".to_string(),
            transition_duration: 2.0,
            shader_preset: "none".to_string(),
            last_async_error: None,
            last_apply_ok: true,
            queued_jobs: 0,
            applied_jobs: 0,
            failed_jobs: 0,
            dropped_jobs: 0,
        }
    }

    fn handle_request(&mut self, req: Request) -> Response {
        match req.cmd.as_str() {
            "health" => Response {
                ok: true,
                error: None,
                service: Some(format!("internal_renderer:{}", self.backend.name())),
                gl: Some(self.backend.gl_enabled()),
                details: Some(format!(
                    "transition={} {:.2}s shader={} last_apply_ok={} last_error={} queued={} applied={} failed={} dropped={}",
                    self.transition_type,
                    self.transition_duration,
                    self.shader_preset,
                    self.last_apply_ok,
                    self
                        .last_async_error
                        .clone()
                        .unwrap_or_else(|| "none".to_string()),
                    self.queued_jobs,
                    self.applied_jobs,
                    self.failed_jobs,
                    self.dropped_jobs,
                )),
            },
            "reload_outputs" => match self.backend.reload_outputs() {
                Ok(()) => Response {
                    ok: true,
                    error: None,
                    service: None,
                    gl: None,
                    details: None,
                },
                Err(err) => Response {
                    ok: false,
                    error: Some(err),
                    service: None,
                    gl: None,
                    details: None,
                },
            },
            "set_transition" => self.set_transition(req),
            "set_shader_preset" => self.set_shader_preset(req),
            "set_wallpaper" => self.set_wallpaper(req),
            "get_state" => self.get_state(),
            _ => Response {
                ok: false,
                error: Some("unknown command".to_string()),
                service: None,
                gl: None,
                details: None,
            },
        }
    }

    fn set_wallpaper(&mut self, req: Request) -> Response {
        let (transition_type, transition_duration) = workspace_transition(&req);
        let workspace = req.workspace.unwrap_or(1);
        let path = match req.path.as_ref() {
            Some(p) => p.clone(),
            None => {
                return Response {
                    ok: false,
                    error: Some("invalid path".to_string()),
                    service: None,
                    gl: None,
                    details: None,
                }
            }
        };
        if !Path::new(&path).is_file() {
            return Response {
                ok: false,
                error: Some("invalid path".to_string()),
                service: None,
                gl: None,
                details: None,
            };
        }

        let mode = req.mode.unwrap_or_else(|| "fill".to_string());
        let shader_preset = req.shader_preset.unwrap_or_else(|| "none".to_string());
        let _ = self
            .backend
            .set_transition(&transition_type, transition_duration);
        let _ = self.backend.set_shader_preset(&shader_preset);

        match self.backend.apply_wallpaper(&path, &mode) {
            Ok(()) => {
                self.last_apply_ok = true;
                self.last_async_error = None;
                self.workspaces.insert(
                    workspace,
                    WorkspaceSettings {
                        path,
                        mode,
                        transition_type,
                        transition_duration,
                        shader_preset,
                    },
                );
                Response {
                    ok: true,
                    error: None,
                    service: None,
                    gl: None,
                    details: None,
                }
            }
            Err(err) => {
                self.last_apply_ok = false;
                self.last_async_error = Some(err.clone());
                Response {
                    ok: false,
                    error: Some(err),
                    service: None,
                    gl: None,
                    details: None,
                }
            }
        }
    }

    fn set_transition(&mut self, req: Request) -> Response {
        let (kind, duration) = workspace_transition(&req);
        self.transition_type = kind.clone();
        self.transition_duration = duration;
        match self.backend.set_transition(&kind, duration) {
            Ok(()) => Response {
                ok: true,
                error: None,
                service: None,
                gl: None,
                details: Some(format!("transition={} {:.2}s", kind, duration)),
            },
            Err(err) => Response {
                ok: false,
                error: Some(err),
                service: None,
                gl: None,
                details: None,
            },
        }
    }

    fn set_shader_preset(&mut self, req: Request) -> Response {
        let preset = req
            .shader_preset
            .or(req.path)
            .unwrap_or_else(|| "none".to_string());
        self.shader_preset = preset.clone();
        match self.backend.set_shader_preset(&preset) {
            Ok(()) => Response {
                ok: true,
                error: None,
                service: None,
                gl: None,
                details: Some(format!("shader_preset={preset}")),
            },
            Err(err) => Response {
                ok: false,
                error: Some(err),
                service: None,
                gl: None,
                details: None,
            },
        }
    }

    fn get_state(&self) -> Response {
        let _acc = self.workspaces.values().fold(0usize, |acc, ws| {
            acc
                + ws.path.len()
                + ws.mode.len()
                + ws.transition_type.len()
                + ws.shader_preset.len()
                + ws.transition_duration as usize
        });
        Response {
            ok: true,
            error: None,
            service: None,
            gl: None,
            details: Some(format!(
                "workspaces={} transition={} {:.2}s shader={} last_apply_ok={} last_error={} queued={} applied={} failed={} dropped={}",
                self.workspaces.len(),
                self.transition_type,
                self.transition_duration,
                self.shader_preset,
                self.last_apply_ok,
                self
                    .last_async_error
                    .clone()
                    .unwrap_or_else(|| "none".to_string()),
                self.queued_jobs,
                self.applied_jobs,
                self.failed_jobs,
                self.dropped_jobs,
            )),
        }
    }
}

fn default_transition_type() -> String {
    "wipe".to_string()
}

fn default_transition_duration() -> f32 {
    2.0
}

fn workspace_transition(req: &Request) -> (String, f32) {
    if let Some(transition) = &req.transition {
        let kind = transition
            .kind
            .clone()
            .unwrap_or_else(default_transition_type);
        let duration = transition.duration.unwrap_or_else(default_transition_duration);
        return (kind, duration);
    }

    let kind = req
        .transition_type
        .clone()
        .unwrap_or_else(default_transition_type);
    let duration = req
        .transition_duration
        .unwrap_or_else(default_transition_duration);
    (kind, duration)
}

fn backend_from_env() -> Box<dyn RenderBackend> {
    let backend = env::var("MADOS_RENDERER_BACKEND").unwrap_or_else(|_| "auto".to_string());

    if backend == "shell" {
        return Box::new(ShellBackend);
    }

    #[cfg(feature = "wayland_gl")]
    {
        if backend == "wayland_gl" {
            return Box::new(WaylandGlBackend::new());
        }
        if backend == "auto" {
            let backend = WaylandGlBackend::new();
            if backend.gl_enabled() {
                return Box::new(backend);
            }
        }
    }

    Box::new(ShellBackend)
}

fn handle_connection(worker_tx: &SyncSender<WorkerRequest>, mut stream: UnixStream) {
    let cloned = match stream.try_clone() {
        Ok(c) => c,
        Err(_) => return,
    };
    let mut reader = BufReader::new(cloned);
    let mut line = String::new();
    if reader.read_line(&mut line).is_err() {
        return;
    }
    if line.trim().is_empty() {
        return;
    }

    let response = match serde_json::from_str::<Request>(line.trim_end()) {
        Ok(req) => dispatch_request(worker_tx, req),
        Err(_) => Response {
            ok: false,
            error: Some("invalid json".to_string()),
            service: None,
            gl: None,
            details: None,
        },
    };

    if let Ok(body) = serde_json::to_string(&response) {
        let _ = stream.write_all(body.as_bytes());
        let _ = stream.write_all(b"\n");
    }
}

fn dispatch_request(worker_tx: &SyncSender<WorkerRequest>, req: Request) -> Response {
    if req.cmd == "set_wallpaper" {
        if let Some(path) = req.path.as_ref() {
            if !Path::new(path).is_file() {
                return Response {
                    ok: false,
                    error: Some("invalid path".to_string()),
                    service: None,
                    gl: None,
                    details: None,
                };
            }
        }
        if worker_tx
            .send(WorkerRequest {
                request: req,
                response_tx: None,
            })
            .is_ok()
        {
            return Response {
                ok: true,
                error: None,
                service: None,
                gl: None,
                details: Some("queued".to_string()),
            };
        }
        return Response {
            ok: false,
            error: Some("renderer worker unavailable".to_string()),
            service: None,
            gl: None,
            details: None,
        };
    }

    let (tx, rx) = mpsc::channel();
    if worker_tx
        .send(WorkerRequest {
            request: req,
            response_tx: Some(tx),
        })
        .is_err()
    {
        return Response {
            ok: false,
            error: Some("renderer worker unavailable".to_string()),
            service: None,
            gl: None,
            details: None,
        };
    }

    match rx.recv() {
        Ok(resp) => resp,
        Err(_) => Response {
            ok: false,
            error: Some("renderer worker response failed".to_string()),
            service: None,
            gl: None,
            details: None,
        },
    }
}

fn process_worker_message(
    state: &mut RendererState,
    pending_wallpapers: &mut HashMap<u32, WorkerRequest>,
    msg: WorkerRequest,
) {
    let is_async_wallpaper = msg.request.cmd == "set_wallpaper" && msg.response_tx.is_none();
    if is_async_wallpaper {
        let ws = msg.request.workspace.unwrap_or(1);
        if pending_wallpapers.insert(ws, msg).is_some() {
            state.dropped_jobs += 1;
        }
        state.queued_jobs += 1;
        return;
    }

    let response = state.handle_request(msg.request);
    if let Some(tx) = msg.response_tx {
        let _ = tx.send(response);
    }
}

fn parse_socket_arg() -> Result<String, String> {
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--socket" {
            if let Some(path) = args.next() {
                return Ok(path);
            }
            return Err("missing socket path".to_string());
        }
    }
    Err("--socket is required".to_string())
}

fn main() -> Result<(), String> {
    let socket_path = parse_socket_arg()?;
    let socket = Path::new(&socket_path);
    if let Some(parent) = socket.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("mkdir failed: {e}"))?;
    }

    if socket.exists() {
        let _ = fs::remove_file(socket);
    }

    let listener = UnixListener::bind(socket).map_err(|e| format!("bind failed: {e}"))?;
    let perms = fs::Permissions::from_mode(0o600);
    fs::set_permissions(socket, perms).map_err(|e| format!("chmod failed: {e}"))?;

    let (worker_tx, worker_rx) = mpsc::sync_channel::<WorkerRequest>(WORKER_QUEUE_CAPACITY);
    thread::spawn(move || {
        let mut state = RendererState::new();
        let mut pending_wallpapers: HashMap<u32, WorkerRequest> = HashMap::new();
        while let Ok(msg) = worker_rx.recv() {
            process_worker_message(&mut state, &mut pending_wallpapers, msg);

            while let Ok(next) = worker_rx.try_recv() {
                process_worker_message(&mut state, &mut pending_wallpapers, next);
            }

            for (_, pending) in pending_wallpapers.drain() {
                let response = state.handle_request(pending.request);
                if response.ok {
                    state.applied_jobs += 1;
                } else {
                    state.failed_jobs += 1;
                }
            }
        }
    });

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => handle_connection(&worker_tx, stream),
            Err(err) => return Err(format!("socket accept failed: {err}")),
        }
    }

    Ok(())
}
