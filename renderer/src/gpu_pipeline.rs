use libloading::Library;
use std::ffi::c_void;
use std::ffi::CString;

pub struct GpuUpload {
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

pub struct TransitionState {
    pub kind: String,
    pub duration: f32,
    pub progress: f32,
}

type EglDisplay = *mut c_void;
type EglContext = *mut c_void;
type EglConfig = *mut c_void;
type EglSurface = *mut c_void;
type EglBoolean = u32;
type EglInt = i32;

const EGL_NONE: EglInt = 0x3038;
const EGL_RED_SIZE: EglInt = 0x3024;
const EGL_GREEN_SIZE: EglInt = 0x3023;
const EGL_BLUE_SIZE: EglInt = 0x3022;
const EGL_ALPHA_SIZE: EglInt = 0x3021;
const EGL_RENDERABLE_TYPE: EglInt = 0x3040;
const EGL_OPENGL_ES2_BIT: EglInt = 0x0004;
const EGL_CONTEXT_CLIENT_VERSION: EglInt = 0x3098;
const EGL_WIDTH: EglInt = 0x3057;
const EGL_HEIGHT: EglInt = 0x3056;
const EGL_OPENGL_ES_API: u32 = 0x30A0;
const EGL_DEFAULT_DISPLAY: *mut c_void = std::ptr::null_mut();

const GL_TEXTURE_2D: u32 = 0x0DE1;
const GL_RGBA: u32 = 0x1908;
const GL_UNSIGNED_BYTE: u32 = 0x1401;
const GL_COLOR_BUFFER_BIT: u32 = 0x00004000;
const GL_VERTEX_SHADER: u32 = 0x8B31;
const GL_FRAGMENT_SHADER: u32 = 0x8B30;
const GL_COMPILE_STATUS: u32 = 0x8B81;
const GL_LINK_STATUS: u32 = 0x8B82;
const GL_TEXTURE_MIN_FILTER: i32 = 0x2801;
const GL_TEXTURE_MAG_FILTER: i32 = 0x2800;
const GL_LINEAR: i32 = 0x2601;

struct EglFns {
    get_display: unsafe extern "C" fn(*mut c_void) -> EglDisplay,
    initialize: unsafe extern "C" fn(EglDisplay, *mut EglInt, *mut EglInt) -> EglBoolean,
    terminate: unsafe extern "C" fn(EglDisplay) -> EglBoolean,
    choose_config: unsafe extern "C" fn(
        EglDisplay,
        *const EglInt,
        *mut EglConfig,
        EglInt,
        *mut EglInt,
    ) -> EglBoolean,
    bind_api: unsafe extern "C" fn(u32) -> EglBoolean,
    create_context:
        unsafe extern "C" fn(EglDisplay, EglConfig, EglContext, *const EglInt) -> EglContext,
    create_pbuffer_surface:
        unsafe extern "C" fn(EglDisplay, EglConfig, *const EglInt) -> EglSurface,
    make_current:
        unsafe extern "C" fn(EglDisplay, EglSurface, EglSurface, EglContext) -> EglBoolean,
    destroy_surface: unsafe extern "C" fn(EglDisplay, EglSurface) -> EglBoolean,
    destroy_context: unsafe extern "C" fn(EglDisplay, EglContext) -> EglBoolean,
    swap_buffers: unsafe extern "C" fn(EglDisplay, EglSurface) -> EglBoolean,
}

struct GlFns {
    viewport: unsafe extern "C" fn(i32, i32, i32, i32),
    clear_color: unsafe extern "C" fn(f32, f32, f32, f32),
    clear: unsafe extern "C" fn(u32),
    gen_textures: unsafe extern "C" fn(i32, *mut u32),
    bind_texture: unsafe extern "C" fn(u32, u32),
    tex_parameteri: unsafe extern "C" fn(u32, i32, i32),
    tex_image_2d: unsafe extern "C" fn(u32, i32, i32, i32, i32, i32, u32, u32, *const c_void),
    create_shader: unsafe extern "C" fn(u32) -> u32,
    shader_source: unsafe extern "C" fn(u32, i32, *const *const i8, *const i32),
    compile_shader: unsafe extern "C" fn(u32),
    get_shader_iv: unsafe extern "C" fn(u32, u32, *mut i32),
    delete_shader: unsafe extern "C" fn(u32),
    create_program: unsafe extern "C" fn() -> u32,
    attach_shader: unsafe extern "C" fn(u32, u32),
    link_program: unsafe extern "C" fn(u32),
    get_program_iv: unsafe extern "C" fn(u32, u32, *mut i32),
    use_program: unsafe extern "C" fn(u32),
    delete_program: unsafe extern "C" fn(u32),
}

pub struct GpuPipeline {
    initialized: bool,
    egl: Option<Library>,
    gl: Option<Library>,
    egl_fns: Option<EglFns>,
    gl_fns: Option<GlFns>,
    display: EglDisplay,
    context: EglContext,
    surface: EglSurface,
    texture: u32,
    program: u32,
    transition: TransitionState,
    shader_preset: String,
    last_error: Option<String>,
    egl_version: Option<(i32, i32)>,
}

impl GpuPipeline {
    pub fn new() -> Self {
        Self {
            initialized: false,
            egl: None,
            gl: None,
            egl_fns: None,
            gl_fns: None,
            display: std::ptr::null_mut(),
            context: std::ptr::null_mut(),
            surface: std::ptr::null_mut(),
            texture: 0,
            program: 0,
            transition: TransitionState {
                kind: "wipe".to_string(),
                duration: 2.0,
                progress: 1.0,
            },
            shader_preset: "none".to_string(),
            last_error: None,
            egl_version: None,
        }
    }

    pub fn is_initialized(&self) -> bool {
        self.initialized
    }

    pub fn set_transition(&mut self, kind: &str, duration: f32) {
        self.transition.kind = kind.to_string();
        self.transition.duration = duration.max(0.01);
        self.transition.progress = 0.0;
    }

    pub fn set_shader_preset(&mut self, preset: &str) {
        self.shader_preset = preset.to_string();
    }

    pub fn tick_transition(&mut self, dt: f32) {
        if self.transition.progress >= 1.0 {
            return;
        }
        self.transition.progress =
            (self.transition.progress + dt / self.transition.duration).clamp(0.0, 1.0);
    }

    pub fn last_error(&self) -> Option<&str> {
        self.last_error.as_deref()
    }

    pub fn egl_version(&self) -> Option<(i32, i32)> {
        self.egl_version
    }

    pub fn try_initialize(&mut self) -> Result<(), String> {
        if self.initialized {
            return Ok(());
        }

        let egl = load_lib_any(&["libEGL.so.1", "libEGL.so"])?;
        let gl = load_lib_any(&["libGLESv2.so.2", "libGLESv2.so", "libGL.so.1"])?;

        let egl_fns = load_egl_fns(&egl)?;
        let gl_fns = load_gl_fns(&gl)?;

        let mut major = 0;
        let mut minor = 0;

        // SAFETY: EGL calls with validated function pointers and initialized out params.
        let display = unsafe { (egl_fns.get_display)(EGL_DEFAULT_DISPLAY) };
        if display.is_null() {
            return Err("eglGetDisplay returned null".to_string());
        }
        // SAFETY: valid pointers provided.
        let ok_init = unsafe { (egl_fns.initialize)(display, &mut major, &mut minor) };
        if ok_init == 0 {
            self.last_error = Some("eglInitialize failed".to_string());
            return Err("eglInitialize failed".to_string());
        }

        // SAFETY: valid EGL display.
        let ok_bind = unsafe { (egl_fns.bind_api)(EGL_OPENGL_ES_API) };
        if ok_bind == 0 {
            self.last_error = Some("eglBindAPI failed".to_string());
            return Err("eglBindAPI(EGL_OPENGL_ES_API) failed".to_string());
        }

        let config_attribs = [
            EGL_RED_SIZE,
            8,
            EGL_GREEN_SIZE,
            8,
            EGL_BLUE_SIZE,
            8,
            EGL_ALPHA_SIZE,
            8,
            EGL_RENDERABLE_TYPE,
            EGL_OPENGL_ES2_BIT,
            EGL_NONE,
        ];
        let mut config: EglConfig = std::ptr::null_mut();
        let mut num_configs: EglInt = 0;
        // SAFETY: pointers valid for output.
        let ok_choose = unsafe {
            (egl_fns.choose_config)(
                display,
                config_attribs.as_ptr(),
                &mut config,
                1,
                &mut num_configs,
            )
        };
        if ok_choose == 0 || num_configs == 0 || config.is_null() {
            self.last_error = Some("eglChooseConfig failed".to_string());
            return Err("eglChooseConfig failed".to_string());
        }

        let ctx_attribs = [EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE];
        // SAFETY: valid display/config and attrs.
        let context = unsafe {
            (egl_fns.create_context)(display, config, std::ptr::null_mut(), ctx_attribs.as_ptr())
        };
        if context.is_null() {
            self.last_error = Some("eglCreateContext failed".to_string());
            return Err("eglCreateContext failed".to_string());
        }

        let surf_attribs = [EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE];
        // SAFETY: valid display/config and attrs.
        let surface =
            unsafe { (egl_fns.create_pbuffer_surface)(display, config, surf_attribs.as_ptr()) };
        if surface.is_null() {
            self.last_error = Some("eglCreatePbufferSurface failed".to_string());
            return Err("eglCreatePbufferSurface failed".to_string());
        }

        // SAFETY: valid display/surface/context.
        let ok_current = unsafe { (egl_fns.make_current)(display, surface, surface, context) };
        if ok_current == 0 {
            self.last_error = Some("eglMakeCurrent failed".to_string());
            return Err("eglMakeCurrent failed".to_string());
        }

        let vs = compile_shader(&gl_fns, GL_VERTEX_SHADER, VERT_SRC)?;
        let fs = compile_shader(&gl_fns, GL_FRAGMENT_SHADER, FRAG_SRC)?;
        let program = link_program(&gl_fns, vs, fs)?;
        // SAFETY: shader handles are valid.
        unsafe {
            (gl_fns.delete_shader)(vs);
            (gl_fns.delete_shader)(fs);
        }

        let mut tex = 0u32;
        // SAFETY: valid GL context current.
        unsafe {
            (gl_fns.gen_textures)(1, &mut tex);
            (gl_fns.bind_texture)(GL_TEXTURE_2D, tex);
            (gl_fns.tex_parameteri)(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
            (gl_fns.tex_parameteri)(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
            (gl_fns.use_program)(program);
        }

        self.egl = Some(egl);
        self.gl = Some(gl);
        self.egl_fns = Some(egl_fns);
        self.gl_fns = Some(gl_fns);
        self.display = display;
        self.context = context;
        self.surface = surface;
        self.texture = tex;
        self.program = program;
        self.egl_version = Some((major, minor));
        self.last_error = None;
        self.initialized = true;
        let _ = (major, minor);
        Ok(())
    }

    pub fn upload(&mut self, frame: &GpuUpload) -> Result<(), String> {
        if !self.initialized {
            return Err("GPU pipeline not initialized".to_string());
        }
        let expected = frame
            .width
            .checked_mul(frame.height)
            .and_then(|px| px.checked_mul(4))
            .ok_or_else(|| "frame size overflow".to_string())? as usize;
        if frame.rgba.len() != expected {
            return Err("invalid frame byte size".to_string());
        }

        let gl = self
            .gl_fns
            .as_ref()
            .ok_or_else(|| "GL functions missing".to_string())?;
        let egl = self
            .egl_fns
            .as_ref()
            .ok_or_else(|| "EGL functions missing".to_string())?;

        // SAFETY: GL context is current and pointers are valid.
        unsafe {
            (gl.viewport)(0, 0, frame.width as i32, frame.height as i32);
            (gl.bind_texture)(GL_TEXTURE_2D, self.texture);
            (gl.tex_image_2d)(
                GL_TEXTURE_2D,
                0,
                GL_RGBA as i32,
                frame.width as i32,
                frame.height as i32,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                frame.rgba.as_ptr() as *const c_void,
            );

            let t = self.transition.progress;
            let (r, g, b) = if self.transition.kind == "wipe" {
                if self.shader_preset == "nord" {
                    (0.18 * (1.0 - t), 0.23 * (1.0 - t), 0.28 * (1.0 - t))
                } else {
                    (0.08 * (1.0 - t), 0.10 * (1.0 - t), 0.12 * (1.0 - t))
                }
            } else {
                (0.02, 0.02, 0.02)
            };
            (gl.clear_color)(r, g, b, 1.0);
            (gl.clear)(GL_COLOR_BUFFER_BIT);
            (egl.swap_buffers)(self.display, self.surface);
        }

        self.tick_transition(1.0 / 60.0);
        Ok(())
    }
}

impl Drop for GpuPipeline {
    fn drop(&mut self) {
        if !self.initialized {
            return;
        }
        if let Some(egl) = &self.egl_fns {
            // SAFETY: handles were created by EGL and can be destroyed in reverse order.
            unsafe {
                let _ = (egl.make_current)(
                    self.display,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                );
                let _ = (egl.destroy_surface)(self.display, self.surface);
                let _ = (egl.destroy_context)(self.display, self.context);
                let _ = (egl.terminate)(self.display);
            }
        }
    }
}

fn load_lib_any(candidates: &[&str]) -> Result<Library, String> {
    for candidate in candidates {
        // SAFETY: opening a dynamic library is unsafe; we validate symbol loads before use.
        let lib = unsafe { Library::new(candidate) };
        if let Ok(lib) = lib {
            return Ok(lib);
        }
    }
    Err(format!("could not load any library from {candidates:?}"))
}

fn load_egl_fns(egl: &Library) -> Result<EglFns, String> {
    type EglGetDisplay = unsafe extern "C" fn(*mut c_void) -> EglDisplay;
    type EglInitialize = unsafe extern "C" fn(EglDisplay, *mut EglInt, *mut EglInt) -> EglBoolean;
    type EglTerminate = unsafe extern "C" fn(EglDisplay) -> EglBoolean;
    type EglChooseConfig = unsafe extern "C" fn(
        EglDisplay,
        *const EglInt,
        *mut EglConfig,
        EglInt,
        *mut EglInt,
    ) -> EglBoolean;
    type EglBindApi = unsafe extern "C" fn(u32) -> EglBoolean;
    type EglCreateContext =
        unsafe extern "C" fn(EglDisplay, EglConfig, EglContext, *const EglInt) -> EglContext;
    type EglCreatePbufferSurface =
        unsafe extern "C" fn(EglDisplay, EglConfig, *const EglInt) -> EglSurface;
    type EglMakeCurrent =
        unsafe extern "C" fn(EglDisplay, EglSurface, EglSurface, EglContext) -> EglBoolean;
    type EglDestroySurface = unsafe extern "C" fn(EglDisplay, EglSurface) -> EglBoolean;
    type EglDestroyContext = unsafe extern "C" fn(EglDisplay, EglContext) -> EglBoolean;
    type EglSwapBuffers = unsafe extern "C" fn(EglDisplay, EglSurface) -> EglBoolean;

    // SAFETY: symbol signatures match EGL API.
    unsafe {
        Ok(EglFns {
            get_display: *egl
                .get::<EglGetDisplay>(b"eglGetDisplay")
                .map_err(|e| format!("eglGetDisplay: {e}"))?,
            initialize: *egl
                .get::<EglInitialize>(b"eglInitialize")
                .map_err(|e| format!("eglInitialize: {e}"))?,
            terminate: *egl
                .get::<EglTerminate>(b"eglTerminate")
                .map_err(|e| format!("eglTerminate: {e}"))?,
            choose_config: *egl
                .get::<EglChooseConfig>(b"eglChooseConfig")
                .map_err(|e| format!("eglChooseConfig: {e}"))?,
            bind_api: *egl
                .get::<EglBindApi>(b"eglBindAPI")
                .map_err(|e| format!("eglBindAPI: {e}"))?,
            create_context: *egl
                .get::<EglCreateContext>(b"eglCreateContext")
                .map_err(|e| format!("eglCreateContext: {e}"))?,
            create_pbuffer_surface: *egl
                .get::<EglCreatePbufferSurface>(b"eglCreatePbufferSurface")
                .map_err(|e| format!("eglCreatePbufferSurface: {e}"))?,
            make_current: *egl
                .get::<EglMakeCurrent>(b"eglMakeCurrent")
                .map_err(|e| format!("eglMakeCurrent: {e}"))?,
            destroy_surface: *egl
                .get::<EglDestroySurface>(b"eglDestroySurface")
                .map_err(|e| format!("eglDestroySurface: {e}"))?,
            destroy_context: *egl
                .get::<EglDestroyContext>(b"eglDestroyContext")
                .map_err(|e| format!("eglDestroyContext: {e}"))?,
            swap_buffers: *egl
                .get::<EglSwapBuffers>(b"eglSwapBuffers")
                .map_err(|e| format!("eglSwapBuffers: {e}"))?,
        })
    }
}

fn load_gl_fns(gl: &Library) -> Result<GlFns, String> {
    type GlViewport = unsafe extern "C" fn(i32, i32, i32, i32);
    type GlClearColor = unsafe extern "C" fn(f32, f32, f32, f32);
    type GlClear = unsafe extern "C" fn(u32);
    type GlGenTextures = unsafe extern "C" fn(i32, *mut u32);
    type GlBindTexture = unsafe extern "C" fn(u32, u32);
    type GlTexParameteri = unsafe extern "C" fn(u32, i32, i32);
    type GlTexImage2D = unsafe extern "C" fn(u32, i32, i32, i32, i32, i32, u32, u32, *const c_void);
    type GlCreateShader = unsafe extern "C" fn(u32) -> u32;
    type GlShaderSource = unsafe extern "C" fn(u32, i32, *const *const i8, *const i32);
    type GlCompileShader = unsafe extern "C" fn(u32);
    type GlGetShaderiv = unsafe extern "C" fn(u32, u32, *mut i32);
    type GlDeleteShader = unsafe extern "C" fn(u32);
    type GlCreateProgram = unsafe extern "C" fn() -> u32;
    type GlAttachShader = unsafe extern "C" fn(u32, u32);
    type GlLinkProgram = unsafe extern "C" fn(u32);
    type GlGetProgramiv = unsafe extern "C" fn(u32, u32, *mut i32);
    type GlUseProgram = unsafe extern "C" fn(u32);
    type GlDeleteProgram = unsafe extern "C" fn(u32);

    // SAFETY: symbol signatures match GLES API.
    unsafe {
        Ok(GlFns {
            viewport: *gl
                .get::<GlViewport>(b"glViewport")
                .map_err(|e| format!("glViewport: {e}"))?,
            clear_color: *gl
                .get::<GlClearColor>(b"glClearColor")
                .map_err(|e| format!("glClearColor: {e}"))?,
            clear: *gl
                .get::<GlClear>(b"glClear")
                .map_err(|e| format!("glClear: {e}"))?,
            gen_textures: *gl
                .get::<GlGenTextures>(b"glGenTextures")
                .map_err(|e| format!("glGenTextures: {e}"))?,
            bind_texture: *gl
                .get::<GlBindTexture>(b"glBindTexture")
                .map_err(|e| format!("glBindTexture: {e}"))?,
            tex_parameteri: *gl
                .get::<GlTexParameteri>(b"glTexParameteri")
                .map_err(|e| format!("glTexParameteri: {e}"))?,
            tex_image_2d: *gl
                .get::<GlTexImage2D>(b"glTexImage2D")
                .map_err(|e| format!("glTexImage2D: {e}"))?,
            create_shader: *gl
                .get::<GlCreateShader>(b"glCreateShader")
                .map_err(|e| format!("glCreateShader: {e}"))?,
            shader_source: *gl
                .get::<GlShaderSource>(b"glShaderSource")
                .map_err(|e| format!("glShaderSource: {e}"))?,
            compile_shader: *gl
                .get::<GlCompileShader>(b"glCompileShader")
                .map_err(|e| format!("glCompileShader: {e}"))?,
            get_shader_iv: *gl
                .get::<GlGetShaderiv>(b"glGetShaderiv")
                .map_err(|e| format!("glGetShaderiv: {e}"))?,
            delete_shader: *gl
                .get::<GlDeleteShader>(b"glDeleteShader")
                .map_err(|e| format!("glDeleteShader: {e}"))?,
            create_program: *gl
                .get::<GlCreateProgram>(b"glCreateProgram")
                .map_err(|e| format!("glCreateProgram: {e}"))?,
            attach_shader: *gl
                .get::<GlAttachShader>(b"glAttachShader")
                .map_err(|e| format!("glAttachShader: {e}"))?,
            link_program: *gl
                .get::<GlLinkProgram>(b"glLinkProgram")
                .map_err(|e| format!("glLinkProgram: {e}"))?,
            get_program_iv: *gl
                .get::<GlGetProgramiv>(b"glGetProgramiv")
                .map_err(|e| format!("glGetProgramiv: {e}"))?,
            use_program: *gl
                .get::<GlUseProgram>(b"glUseProgram")
                .map_err(|e| format!("glUseProgram: {e}"))?,
            delete_program: *gl
                .get::<GlDeleteProgram>(b"glDeleteProgram")
                .map_err(|e| format!("glDeleteProgram: {e}"))?,
        })
    }
}

fn compile_shader(gl: &GlFns, kind: u32, src: &str) -> Result<u32, String> {
    // SAFETY: valid GL context and function pointers.
    let shader = unsafe { (gl.create_shader)(kind) };
    if shader == 0 {
        return Err("glCreateShader failed".to_string());
    }
    let c_src = CString::new(src).map_err(|e| format!("shader source: {e}"))?;
    let ptr = c_src.as_ptr();
    // SAFETY: pointers valid during call.
    unsafe {
        (gl.shader_source)(shader, 1, &ptr, std::ptr::null());
        (gl.compile_shader)(shader);
    }
    let mut status = 0;
    // SAFETY: valid shader handle.
    unsafe { (gl.get_shader_iv)(shader, GL_COMPILE_STATUS, &mut status) };
    if status == 0 {
        // SAFETY: valid handle.
        unsafe { (gl.delete_shader)(shader) };
        return Err("shader compile failed".to_string());
    }
    Ok(shader)
}

fn link_program(gl: &GlFns, vs: u32, fs: u32) -> Result<u32, String> {
    // SAFETY: valid GL context and handles.
    let program = unsafe { (gl.create_program)() };
    if program == 0 {
        return Err("glCreateProgram failed".to_string());
    }
    // SAFETY: valid handles.
    unsafe {
        (gl.attach_shader)(program, vs);
        (gl.attach_shader)(program, fs);
        (gl.link_program)(program);
    }
    let mut status = 0;
    // SAFETY: valid handle.
    unsafe { (gl.get_program_iv)(program, GL_LINK_STATUS, &mut status) };
    if status == 0 {
        // SAFETY: valid handle.
        unsafe { (gl.delete_program)(program) };
        return Err("program link failed".to_string());
    }
    Ok(program)
}

const VERT_SRC: &str =
    "#version 100\nattribute vec2 a_pos; void main(){ gl_Position = vec4(a_pos,0.0,1.0); }";
const FRAG_SRC: &str = "#version 100\nprecision mediump float; uniform float u_progress; void main(){ gl_FragColor = vec4(vec3(u_progress),1.0); }";
