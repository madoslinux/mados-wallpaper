#[cfg(feature = "wayland_gl")]
use wayland_client::globals::{registry_queue_init, Global, GlobalList, GlobalListContents};
#[cfg(feature = "wayland_gl")]
use wayland_client::protocol::wl_buffer;
#[cfg(feature = "wayland_gl")]
use wayland_client::protocol::wl_callback;
#[cfg(feature = "wayland_gl")]
use wayland_client::protocol::wl_compositor;
#[cfg(feature = "wayland_gl")]
use wayland_client::protocol::wl_output;
#[cfg(feature = "wayland_gl")]
use wayland_client::protocol::wl_registry;
#[cfg(feature = "wayland_gl")]
use wayland_client::protocol::wl_shm;
#[cfg(feature = "wayland_gl")]
use wayland_client::protocol::wl_shm_pool;
#[cfg(feature = "wayland_gl")]
use wayland_client::protocol::wl_surface;
#[cfg(feature = "wayland_gl")]
use wayland_client::{Connection, Dispatch, EventQueue, QueueHandle};
#[cfg(feature = "wayland_gl")]
use wayland_protocols_wlr::layer_shell::v1::client::zwlr_layer_shell_v1;
#[cfg(feature = "wayland_gl")]
use wayland_protocols_wlr::layer_shell::v1::client::zwlr_layer_surface_v1;

use std::collections::HashMap;
use std::fs::OpenOptions;
use std::io::Write;
use std::os::fd::AsFd;
use std::path::Path;
use std::time::Duration;
use std::time::Instant;

use image::imageops::FilterType;
use image::GenericImageView;

use crate::backend::RenderBackend;
use crate::gpu_pipeline::{GpuPipeline, GpuUpload};

#[cfg(feature = "wayland_gl")]
#[derive(Default)]
struct WaylandState {
    outputs: Vec<u32>,
    layer_shell_available: bool,
    layer_sizes: HashMap<u32, (u32, u32)>,
    frame_done: HashMap<u32, bool>,
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<wl_registry::WlRegistry, GlobalListContents> for WaylandState {
    fn event(
        state: &mut Self,
        _proxy: &wl_registry::WlRegistry,
        event: wl_registry::Event,
        _data: &GlobalListContents,
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
        match event {
            wl_registry::Event::Global {
                name,
                interface,
                version: _,
            } => {
                if interface == "wl_output" && !state.outputs.contains(&name) {
                    state.outputs.push(name);
                }
                if interface == "zwlr_layer_shell_v1" {
                    state.layer_shell_available = true;
                }
            }
            wl_registry::Event::GlobalRemove { name } => {
                state.outputs.retain(|n| *n != name);
            }
            _ => {}
        }
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<wl_registry::WlRegistry, ()> for WaylandState {
    fn event(
        _state: &mut Self,
        _proxy: &wl_registry::WlRegistry,
        _event: wl_registry::Event,
        _data: &(),
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<wl_compositor::WlCompositor, ()> for WaylandState {
    fn event(
        _state: &mut Self,
        _proxy: &wl_compositor::WlCompositor,
        _event: wl_compositor::Event,
        _data: &(),
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<wl_surface::WlSurface, ()> for WaylandState {
    fn event(
        _state: &mut Self,
        _proxy: &wl_surface::WlSurface,
        _event: wl_surface::Event,
        _data: &(),
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<wl_shm::WlShm, ()> for WaylandState {
    fn event(
        _state: &mut Self,
        _proxy: &wl_shm::WlShm,
        _event: wl_shm::Event,
        _data: &(),
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<wl_shm_pool::WlShmPool, ()> for WaylandState {
    fn event(
        _state: &mut Self,
        _proxy: &wl_shm_pool::WlShmPool,
        _event: wl_shm_pool::Event,
        _data: &(),
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<wl_buffer::WlBuffer, ()> for WaylandState {
    fn event(
        _state: &mut Self,
        _proxy: &wl_buffer::WlBuffer,
        _event: wl_buffer::Event,
        _data: &(),
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<wl_callback::WlCallback, u32> for WaylandState {
    fn event(
        state: &mut Self,
        _proxy: &wl_callback::WlCallback,
        event: wl_callback::Event,
        data: &u32,
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
        if let wl_callback::Event::Done { callback_data: _ } = event {
            state.frame_done.insert(*data, true);
        }
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<wl_output::WlOutput, u32> for WaylandState {
    fn event(
        _state: &mut Self,
        _proxy: &wl_output::WlOutput,
        _event: wl_output::Event,
        _data: &u32,
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<zwlr_layer_shell_v1::ZwlrLayerShellV1, ()> for WaylandState {
    fn event(
        _state: &mut Self,
        _proxy: &zwlr_layer_shell_v1::ZwlrLayerShellV1,
        _event: zwlr_layer_shell_v1::Event,
        _data: &(),
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

#[cfg(feature = "wayland_gl")]
impl Dispatch<zwlr_layer_surface_v1::ZwlrLayerSurfaceV1, u32> for WaylandState {
    fn event(
        state: &mut Self,
        proxy: &zwlr_layer_surface_v1::ZwlrLayerSurfaceV1,
        event: zwlr_layer_surface_v1::Event,
        data: &u32,
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
        if let zwlr_layer_surface_v1::Event::Configure {
            serial,
            width,
            height,
        } = event
        {
            proxy.ack_configure(serial);
            if width > 0 && height > 0 {
                state.layer_sizes.insert(*data, (width, height));
            }
        }
    }
}

#[cfg(feature = "wayland_gl")]
fn has_layer_shell(globals: &GlobalList) -> bool {
    globals.contents().with_list(|list| {
        list.iter()
            .any(|Global { interface, .. }| interface == "zwlr_layer_shell_v1")
    })
}

#[derive(Debug, Clone)]
struct WallpaperRequest {
    path: String,
    mode: String,
    transition_type: String,
    transition_duration: f32,
    shader_preset: String,
}

#[derive(Debug, Clone)]
struct OutputSurfaceState {
    output_name: u32,
    has_layer_surface: bool,
    #[cfg(feature = "wayland_gl")]
    output: Option<wl_output::WlOutput>,
    #[cfg(feature = "wayland_gl")]
    surface: Option<wl_surface::WlSurface>,
    #[cfg(feature = "wayland_gl")]
    layer_surface: Option<zwlr_layer_surface_v1::ZwlrLayerSurfaceV1>,
    #[cfg(feature = "wayland_gl")]
    buffer: Option<wl_buffer::WlBuffer>,
    #[cfg(feature = "wayland_gl")]
    last_rgba: Option<Vec<u8>>,
    #[cfg(feature = "wayland_gl")]
    last_size: Option<(u32, u32)>,
}

#[cfg_attr(not(feature = "wayland_gl"), allow(dead_code))]
pub struct WaylandGlBackend {
    connected: bool,
    output_count: usize,
    layer_shell: bool,
    surfaces: HashMap<u32, OutputSurfaceState>,
    last_request: Option<WallpaperRequest>,
    transition_type: String,
    transition_duration: f32,
    shader_preset: String,
    gpu: GpuPipeline,
    #[cfg(feature = "wayland_gl")]
    connection: Option<Connection>,
    #[cfg(feature = "wayland_gl")]
    event_queue: Option<EventQueue<WaylandState>>,
    #[cfg(feature = "wayland_gl")]
    globals: Option<GlobalList>,
    #[cfg(feature = "wayland_gl")]
    compositor: Option<wl_compositor::WlCompositor>,
    #[cfg(feature = "wayland_gl")]
    shm: Option<wl_shm::WlShm>,
    #[cfg(feature = "wayland_gl")]
    layer_shell_handle: Option<zwlr_layer_shell_v1::ZwlrLayerShellV1>,
    #[cfg(feature = "wayland_gl")]
    state: WaylandState,
    last_runtime_error: Option<String>,
}

#[cfg_attr(not(feature = "wayland_gl"), allow(dead_code))]
impl WaylandGlBackend {
    pub fn new() -> Self {
        #[cfg(feature = "wayland_gl")]
        {
            let mut backend = Self {
                connected: false,
                output_count: 0,
                layer_shell: false,
                surfaces: HashMap::new(),
                last_request: None,
                transition_type: "wipe".to_string(),
                transition_duration: 2.0,
                shader_preset: "none".to_string(),
                gpu: GpuPipeline::new(),
                connection: None,
                event_queue: None,
                globals: None,
                compositor: None,
                shm: None,
                layer_shell_handle: None,
                state: WaylandState::default(),
                last_runtime_error: None,
            };
            let _ = backend.gpu.try_initialize();
            let _ = backend.initialize();
            return backend;
        }

        #[cfg(not(feature = "wayland_gl"))]
        {
            Self {
                connected: false,
                output_count: 0,
                layer_shell: false,
                surfaces: HashMap::new(),
                last_request: None,
                transition_type: "wipe".to_string(),
                transition_duration: 2.0,
                shader_preset: "none".to_string(),
                gpu: GpuPipeline::new(),
                last_runtime_error: None,
            }
        }
    }

    #[cfg(feature = "wayland_gl")]
    fn initialize(&mut self) -> Result<(), String> {
        let conn =
            Connection::connect_to_env().map_err(|e| format!("wayland connect failed: {e}"))?;
        let (globals, mut queue) = registry_queue_init::<WaylandState>(&conn)
            .map_err(|e| format!("registry init failed: {e}"))?;
        let qh = queue.handle();

        let compositor = globals
            .bind::<wl_compositor::WlCompositor, WaylandState, _>(&qh, 1..=6, ())
            .map_err(|e| format!("bind wl_compositor failed: {e}"))?;
        let shm = globals
            .bind::<wl_shm::WlShm, WaylandState, _>(&qh, 1..=1, ())
            .map_err(|e| format!("bind wl_shm failed: {e}"))?;
        let layer_shell_handle = globals
            .bind::<zwlr_layer_shell_v1::ZwlrLayerShellV1, WaylandState, _>(&qh, 1..=4, ())
            .map_err(|e| format!("bind layer_shell failed: {e}"))?;

        self.layer_shell = has_layer_shell(&globals);
        self.output_count = globals
            .contents()
            .with_list(|list| list.iter().filter(|g| g.interface == "wl_output").count());

        let _ = queue.roundtrip(&mut self.state);
        if self.output_count == 0 {
            self.output_count = self.state.outputs.len();
        }
        if !self.layer_shell {
            self.layer_shell = self.state.layer_shell_available;
        }
        self.sync_surface_slots();

        self.connected = true;
        self.connection = Some(conn);
        self.event_queue = Some(queue);
        self.globals = Some(globals);
        self.compositor = Some(compositor);
        self.shm = Some(shm);
        self.layer_shell_handle = Some(layer_shell_handle);
        let _ = self.create_layer_surfaces_for_outputs();
        Ok(())
    }

    #[cfg(feature = "wayland_gl")]
    fn refresh_registry(&mut self) -> Result<(), String> {
        if let Some(queue) = self.event_queue.as_mut() {
            queue
                .roundtrip(&mut self.state)
                .map_err(|e| format!("wayland roundtrip failed: {e}"))?;
            self.output_count = self.state.outputs.len();
            self.layer_shell = self.state.layer_shell_available;
            self.sync_surface_slots();
            let _ = self.create_layer_surfaces_for_outputs();
            return Ok(());
        }
        Err("wayland queue not initialized".to_string())
    }

    #[cfg(feature = "wayland_gl")]
    fn create_layer_surfaces_for_outputs(&mut self) -> Result<(), String> {
        let Some(globals) = self.globals.as_ref() else {
            return Err("globals not initialized".to_string());
        };
        let Some(compositor) = self.compositor.as_ref() else {
            return Err("compositor not initialized".to_string());
        };
        let Some(layer_shell_handle) = self.layer_shell_handle.as_ref() else {
            return Err("layer shell not initialized".to_string());
        };
        let Some(queue) = self.event_queue.as_ref() else {
            return Err("event queue not initialized".to_string());
        };

        let qh = queue.handle();
        for output_name in &self.state.outputs {
            if self
                .surfaces
                .get(output_name)
                .and_then(|s| s.layer_surface.as_ref())
                .is_some()
            {
                continue;
            }

            let output = globals
                .bind::<wl_output::WlOutput, WaylandState, _>(&qh, 1..=4, *output_name)
                .map_err(|e| format!("bind wl_output {output_name} failed: {e}"))?;
            let surface = compositor.create_surface(&qh, ());
            let layer_surface = layer_shell_handle.get_layer_surface(
                &surface,
                Some(&output),
                zwlr_layer_shell_v1::Layer::Background,
                "mados-wallpaper".to_string(),
                &qh,
                *output_name,
            );
            layer_surface.set_anchor(
                zwlr_layer_surface_v1::Anchor::Top
                    | zwlr_layer_surface_v1::Anchor::Bottom
                    | zwlr_layer_surface_v1::Anchor::Left
                    | zwlr_layer_surface_v1::Anchor::Right,
            );
            layer_surface.set_size(0, 0);
            layer_surface.set_exclusive_zone(-1);
            surface.commit();

            if let Some(slot) = self.surfaces.get_mut(output_name) {
                slot.output = Some(output);
                slot.surface = Some(surface);
                slot.layer_surface = Some(layer_surface);
                slot.has_layer_surface = true;
            }
        }

        Ok(())
    }

    fn sync_surface_slots(&mut self) {
        let mut fresh = HashMap::new();
        #[cfg(feature = "wayland_gl")]
        {
            for output_name in &self.state.outputs {
                let current =
                    self.surfaces
                        .get(output_name)
                        .cloned()
                        .unwrap_or(OutputSurfaceState {
                            output_name: *output_name,
                            has_layer_surface: false,
                            output: None,
                            surface: None,
                            layer_surface: None,
                            buffer: None,
                            last_rgba: None,
                            last_size: None,
                        });
                fresh.insert(*output_name, current);
            }
        }
        self.surfaces = fresh;
        self.output_count = self.surfaces.len();
    }

    #[cfg(feature = "wayland_gl")]
    fn wait_for_frame_callback(
        &mut self,
        output_name: u32,
        surface: &wl_surface::WlSurface,
        qh: &QueueHandle<WaylandState>,
    ) -> Result<(), String> {
        let Some(queue) = self.event_queue.as_mut() else {
            return Err("event queue not initialized".to_string());
        };

        self.state.frame_done.insert(output_name, false);
        let _cb = surface.frame(qh, output_name);
        let started = Instant::now();
        loop {
            queue
                .blocking_dispatch(&mut self.state)
                .map_err(|e| format!("frame dispatch failed: {e}"))?;
            if self.state.frame_done.remove(&output_name).unwrap_or(false) {
                break;
            }
            if started.elapsed() > Duration::from_millis(1000) {
                break;
            }
        }
        Ok(())
    }
}

#[cfg(feature = "wayland_gl")]
fn make_solid_buffer_with_shm(
    shm: &wl_shm::WlShm,
    width: u32,
    height: u32,
    qh: &QueueHandle<WaylandState>,
) -> Result<wl_buffer::WlBuffer, String> {
    make_solid_buffer_with_shm_inner(shm, width, height, qh)
}

#[cfg(feature = "wayland_gl")]
fn make_solid_buffer_with_shm_inner(
    shm: &wl_shm::WlShm,
    width: u32,
    height: u32,
    qh: &QueueHandle<WaylandState>,
) -> Result<wl_buffer::WlBuffer, String> {
    let stride = (width * 4) as usize;
    let size = stride
        .checked_mul(height as usize)
        .ok_or_else(|| "buffer size overflow".to_string())?;

    let tmp_name = format!(
        "mados-wallpaper-{}-{}x{}",
        std::process::id(),
        width,
        height
    );
    let file_path = std::env::temp_dir().join(tmp_name);
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .read(true)
        .write(true)
        .open(&file_path)
        .map_err(|e| format!("create shm file failed: {e}"))?;
    file.set_len(size as u64)
        .map_err(|e| format!("resize shm file failed: {e}"))?;

    let mut bytes = vec![0u8; size];
    for px in bytes.chunks_exact_mut(4) {
        px[0] = 0x24;
        px[1] = 0x1A;
        px[2] = 0x12;
        px[3] = 0xFF;
    }
    file.write_all(&bytes)
        .map_err(|e| format!("write shm buffer failed: {e}"))?;

    let pool = shm.create_pool(file.as_fd(), size as i32, qh, ());
    let buffer = pool.create_buffer(
        0,
        width as i32,
        height as i32,
        stride as i32,
        wl_shm::Format::Argb8888,
        qh,
        (),
    );
    pool.destroy();

    let _ = std::fs::remove_file(file_path);
    Ok(buffer)
}

#[cfg(feature = "wayland_gl")]
fn make_image_buffer_with_shm(
    shm: &wl_shm::WlShm,
    wallpaper_path: &str,
    width: u32,
    height: u32,
    qh: &QueueHandle<WaylandState>,
) -> Result<wl_buffer::WlBuffer, String> {
    let img = image::open(wallpaper_path)
        .map_err(|e| format!("image decode failed for '{wallpaper_path}': {e}"))?;
    let (src_w, src_h) = img.dimensions();
    if src_w == 0 || src_h == 0 {
        return Err("invalid source image dimensions".to_string());
    }

    let target_ratio = width as f32 / height as f32;
    let source_ratio = src_w as f32 / src_h as f32;

    let (crop_w, crop_h) = if source_ratio > target_ratio {
        let new_w = (src_h as f32 * target_ratio).round() as u32;
        (new_w.max(1).min(src_w), src_h)
    } else {
        let new_h = (src_w as f32 / target_ratio).round() as u32;
        (src_w, new_h.max(1).min(src_h))
    };
    let crop_x = (src_w.saturating_sub(crop_w)) / 2;
    let crop_y = (src_h.saturating_sub(crop_h)) / 2;

    let cropped = img.crop_imm(crop_x, crop_y, crop_w, crop_h);
    let resized = cropped.resize_exact(width, height, FilterType::Lanczos3);
    let rgba = resized.to_rgba8();

    let stride = (width * 4) as usize;
    let size = stride
        .checked_mul(height as usize)
        .ok_or_else(|| "buffer size overflow".to_string())?;

    let tmp_name = format!(
        "mados-wallpaper-img-{}-{}x{}",
        std::process::id(),
        width,
        height
    );
    let file_path = std::env::temp_dir().join(tmp_name);
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .read(true)
        .write(true)
        .open(&file_path)
        .map_err(|e| format!("create shm file failed: {e}"))?;
    file.set_len(size as u64)
        .map_err(|e| format!("resize shm file failed: {e}"))?;

    let mut argb_bytes = vec![0u8; size];
    for (src, dst) in rgba.chunks_exact(4).zip(argb_bytes.chunks_exact_mut(4)) {
        let r = src[0];
        let g = src[1];
        let b = src[2];
        let a = src[3];
        dst[0] = b;
        dst[1] = g;
        dst[2] = r;
        dst[3] = a;
    }

    file.write_all(&argb_bytes)
        .map_err(|e| format!("write shm image buffer failed: {e}"))?;

    let pool = shm.create_pool(file.as_fd(), size as i32, qh, ());
    let buffer = pool.create_buffer(
        0,
        width as i32,
        height as i32,
        stride as i32,
        wl_shm::Format::Argb8888,
        qh,
        (),
    );
    pool.destroy();
    let _ = std::fs::remove_file(file_path);
    Ok(buffer)
}

#[cfg(feature = "wayland_gl")]
fn make_buffer_from_rgba_with_shm(
    shm: &wl_shm::WlShm,
    rgba: &[u8],
    width: u32,
    height: u32,
    qh: &QueueHandle<WaylandState>,
) -> Result<wl_buffer::WlBuffer, String> {
    let stride = (width * 4) as usize;
    let size = stride
        .checked_mul(height as usize)
        .ok_or_else(|| "buffer size overflow".to_string())?;
    if rgba.len() != size {
        return Err("invalid rgba byte size".to_string());
    }

    let tmp_name = format!(
        "mados-wallpaper-rgba-{}-{}x{}",
        std::process::id(),
        width,
        height
    );
    let file_path = std::env::temp_dir().join(tmp_name);
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .read(true)
        .write(true)
        .open(&file_path)
        .map_err(|e| format!("create shm file failed: {e}"))?;
    file.set_len(size as u64)
        .map_err(|e| format!("resize shm file failed: {e}"))?;

    let mut argb_bytes = vec![0u8; size];
    for (src, dst) in rgba.chunks_exact(4).zip(argb_bytes.chunks_exact_mut(4)) {
        let r = src[0];
        let g = src[1];
        let b = src[2];
        let a = src[3];
        dst[0] = b;
        dst[1] = g;
        dst[2] = r;
        dst[3] = a;
    }

    file.write_all(&argb_bytes)
        .map_err(|e| format!("write shm rgba buffer failed: {e}"))?;

    let pool = shm.create_pool(file.as_fd(), size as i32, qh, ());
    let buffer = pool.create_buffer(
        0,
        width as i32,
        height as i32,
        stride as i32,
        wl_shm::Format::Argb8888,
        qh,
        (),
    );
    pool.destroy();
    let _ = std::fs::remove_file(file_path);
    Ok(buffer)
}

fn decode_wallpaper_cover_rgba(
    wallpaper_path: &str,
    width: u32,
    height: u32,
) -> Result<Vec<u8>, String> {
    let img = image::open(wallpaper_path)
        .map_err(|e| format!("image decode failed for '{wallpaper_path}': {e}"))?;
    let (src_w, src_h) = img.dimensions();
    if src_w == 0 || src_h == 0 {
        return Err("invalid source image dimensions".to_string());
    }

    let target_ratio = width as f32 / height as f32;
    let source_ratio = src_w as f32 / src_h as f32;

    let (crop_w, crop_h) = if source_ratio > target_ratio {
        let new_w = (src_h as f32 * target_ratio).round() as u32;
        (new_w.max(1).min(src_w), src_h)
    } else {
        let new_h = (src_w as f32 / target_ratio).round() as u32;
        (src_w, new_h.max(1).min(src_h))
    };
    let crop_x = (src_w.saturating_sub(crop_w)) / 2;
    let crop_y = (src_h.saturating_sub(crop_h)) / 2;

    let cropped = img.crop_imm(crop_x, crop_y, crop_w, crop_h);
    let resized = cropped.resize_exact(width, height, FilterType::Lanczos3);
    Ok(resized.to_rgba8().into_raw())
}

fn apply_shader_preset_cpu(rgba: &mut [u8], preset: &str) {
    if preset == "none" {
        return;
    }
    for px in rgba.chunks_exact_mut(4) {
        let r = px[0] as f32;
        let g = px[1] as f32;
        let b = px[2] as f32;
        if preset == "nord" {
            px[0] = ((r * 0.88) + (b * 0.04)).clamp(0.0, 255.0) as u8;
            px[1] = ((g * 0.92) + 4.0).clamp(0.0, 255.0) as u8;
            px[2] = ((b * 1.05) + 6.0).clamp(0.0, 255.0) as u8;
        } else if preset == "cinematic" {
            let luma = (0.2126 * r + 0.7152 * g + 0.0722 * b).clamp(0.0, 255.0);
            px[0] = (luma * 0.95).clamp(0.0, 255.0) as u8;
            px[1] = (luma * 0.82).clamp(0.0, 255.0) as u8;
            px[2] = (luma * 0.70).clamp(0.0, 255.0) as u8;
        }
    }
}

fn mix_wipe(prev: &[u8], next: &[u8], width: u32, progress: f32) -> Vec<u8> {
    let split = ((width as f32) * progress.clamp(0.0, 1.0)) as usize;
    let mut out = next.to_vec();
    let row = (width as usize) * 4;
    if prev.len() != next.len() || row == 0 {
        return out;
    }
    for y in 0..(next.len() / row) {
        let base = y * row;
        let keep = split.min(width as usize) * 4;
        out[base + keep..base + row].copy_from_slice(&prev[base + keep..base + row]);
    }
    out
}

impl RenderBackend for WaylandGlBackend {
    fn name(&self) -> &'static str {
        "wayland_gl"
    }

    fn can_render(&self) -> bool {
        self.connected && self.layer_shell && self.output_count > 0
    }

    fn gl_enabled(&self) -> bool {
        self.connected && self.layer_shell && self.output_count > 0 && self.gpu.is_initialized()
    }

    fn status_details(&self) -> String {
        let egl = self
            .gpu
            .egl_version()
            .map(|(a, b)| format!("{a}.{b}"))
            .unwrap_or_else(|| "unknown".to_string());
        let gpu_error = self
            .gpu
            .last_error()
            .map(|s| s.to_string())
            .unwrap_or_else(|| "none".to_string());
        let rt_error = self
            .last_runtime_error
            .clone()
            .unwrap_or_else(|| "none".to_string());
        format!(
            "backend=wayland_gl connected={} layer_shell={} outputs={} gl={} egl={} gpu_error={} runtime_error={}",
            self.connected,
            self.layer_shell,
            self.output_count,
            self.gl_enabled(),
            egl,
            gpu_error,
            rt_error
        )
    }

    fn set_transition(&mut self, kind: &str, duration: f32) -> Result<(), String> {
        self.transition_type = kind.to_string();
        self.transition_duration = duration.max(0.01);
        self.gpu
            .set_transition(&self.transition_type, self.transition_duration);
        Ok(())
    }

    fn set_shader_preset(&mut self, preset: &str) -> Result<(), String> {
        self.shader_preset = preset.to_string();
        self.gpu.set_shader_preset(&self.shader_preset);
        Ok(())
    }

    fn reload_outputs(&mut self) -> Result<(), String> {
        #[cfg(feature = "wayland_gl")]
        {
            let res = self.refresh_registry();
            if let Err(err) = &res {
                self.last_runtime_error = Some(err.clone());
            } else {
                self.last_runtime_error = None;
            }
            return res;
        }

        #[cfg(not(feature = "wayland_gl"))]
        {
            Err("wayland_gl feature not enabled".to_string())
        }
    }

    fn apply_wallpaper(&mut self, path: &str, mode: &str) -> Result<(), String> {
        if !Path::new(path).is_file() {
            return Err("invalid path".to_string());
        }

        self.gpu
            .set_transition(&self.transition_type, self.transition_duration);

        self.last_request = Some(WallpaperRequest {
            path: path.to_string(),
            mode: mode.to_string(),
            transition_type: self.transition_type.clone(),
            transition_duration: self.transition_duration,
            shader_preset: self.shader_preset.clone(),
        });

        #[cfg(feature = "wayland_gl")]
        for surface in self.surfaces.values_mut() {
            surface.has_layer_surface = surface.layer_surface.is_some();
        }

        #[cfg(feature = "wayland_gl")]
        {
            if self.event_queue.is_some() {
                let qh = match self.event_queue.as_ref() {
                    Some(queue) => queue.handle(),
                    None => return Err("event queue not initialized".to_string()),
                };
                let output_names: Vec<u32> = self.surfaces.keys().copied().collect();
                for output_name in output_names {
                    let (surface, prev_rgba, prev_size) = {
                        let Some(surface_state) = self.surfaces.get(&output_name) else {
                            continue;
                        };
                        let Some(surface) = surface_state.surface.as_ref() else {
                            continue;
                        };
                        (
                            surface.clone(),
                            surface_state.last_rgba.clone(),
                            surface_state.last_size,
                        )
                    };

                    let (w, h) = self
                        .state
                        .layer_sizes
                        .get(&output_name)
                        .copied()
                        .unwrap_or((1920, 1080));
                    let width = w.max(1);
                    let height = h.max(1);
                    let mut rgba = decode_wallpaper_cover_rgba(path, width, height)?;
                    apply_shader_preset_cpu(&mut rgba, &self.shader_preset);
                    let _ = self.gpu.upload(&GpuUpload {
                        width,
                        height,
                        rgba: rgba.clone(),
                    });

                    let do_wipe = self.transition_type == "wipe"
                        && prev_size.map(|s| s == (width, height)).unwrap_or(false)
                        && prev_rgba.is_some();

                    if do_wipe {
                        if let Some(prev) = &prev_rgba {
                            let fps = 60.0f32;
                            let duration = self.transition_duration.max(0.05);
                            let steps = (duration * fps).round().clamp(3.0, 180.0) as usize;
                            for step in 1..=steps {
                                let progress = step as f32 / steps as f32;
                                let frame = mix_wipe(prev, &rgba, width, progress);
                                let buffer = {
                                    let Some(shm) = self.shm.as_ref() else {
                                        return Err("wl_shm not initialized".to_string());
                                    };
                                    make_buffer_from_rgba_with_shm(shm, &frame, width, height, &qh)
                                        .or_else(|_| {
                                            make_image_buffer_with_shm(
                                                shm, path, width, height, &qh,
                                            )
                                        })?
                                };
                                surface.attach(Some(&buffer), 0, 0);
                                surface.damage_buffer(0, 0, i32::MAX, i32::MAX);
                                surface.commit();
                                if let Some(surface_state) = self.surfaces.get_mut(&output_name) {
                                    surface_state.buffer = Some(buffer);
                                }
                                self.wait_for_frame_callback(output_name, &surface, &qh)?;
                            }
                        }
                    } else {
                        let buffer = {
                            let Some(shm) = self.shm.as_ref() else {
                                return Err("wl_shm not initialized".to_string());
                            };
                            make_buffer_from_rgba_with_shm(shm, &rgba, width, height, &qh).or_else(
                                |_| make_image_buffer_with_shm(shm, path, width, height, &qh),
                            )?
                        };
                        surface.attach(Some(&buffer), 0, 0);
                        surface.damage_buffer(0, 0, i32::MAX, i32::MAX);
                        surface.commit();
                        if let Some(surface_state) = self.surfaces.get_mut(&output_name) {
                            surface_state.buffer = Some(buffer);
                        }
                    }

                    if let Some(surface_state) = self.surfaces.get_mut(&output_name) {
                        surface_state.last_rgba = Some(rgba);
                        surface_state.last_size = Some((width, height));
                    }
                }
            }
        }

        if let Some(request) = &self.last_request {
            let _ = (
                &request.path,
                &request.mode,
                &request.transition_type,
                request.transition_duration,
                &request.shader_preset,
            );
        }
        for surface in self.surfaces.values() {
            let _ = surface.output_name;
        }

        self.last_runtime_error = None;
        Ok(())
    }
}
