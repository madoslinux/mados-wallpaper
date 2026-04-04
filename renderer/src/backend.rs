pub trait RenderBackend {
    fn name(&self) -> &'static str;
    fn can_render(&self) -> bool {
        true
    }
    fn gl_enabled(&self) -> bool;
    fn status_details(&self) -> String {
        "ok".to_string()
    }
    fn set_transition(&mut self, _kind: &str, _duration: f32) -> Result<(), String> {
        Ok(())
    }
    fn set_shader_preset(&mut self, _preset: &str) -> Result<(), String> {
        Ok(())
    }
    fn reload_outputs(&mut self) -> Result<(), String> {
        Ok(())
    }
    fn apply_wallpaper(&mut self, path: &str, mode: &str) -> Result<(), String>;
}
