use std::env;
use std::process::Command;

use crate::backend::RenderBackend;

pub struct ShellBackend;

impl RenderBackend for ShellBackend {
    fn name(&self) -> &'static str {
        "shell"
    }

    fn gl_enabled(&self) -> bool {
        false
    }

    fn apply_wallpaper(&mut self, path: &str, mode: &str) -> Result<(), String> {
        apply_wallpaper_shell(path, mode)
    }
}

fn detect_wm() -> String {
    let desktop = env::var("XDG_CURRENT_DESKTOP")
        .unwrap_or_default()
        .to_lowercase();
    if desktop.contains("sway") {
        return "sway".to_string();
    }
    if desktop.contains("hypr") {
        return "hyprland".to_string();
    }
    "unknown".to_string()
}

fn apply_wallpaper_shell(path: &str, mode: &str) -> Result<(), String> {
    let wm = detect_wm();
    if wm == "sway" {
        let output = Command::new("swaymsg")
            .args(["output", "*", "bg", path, mode])
            .output()
            .map_err(|e| format!("failed to execute swaymsg: {e}"))?;
        if output.status.success() {
            return Ok(());
        }
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        return Err(format!("swaymsg failed: {stderr}"));
    }

    if wm == "hyprland" {
        let value = format!("{path},{mode}");
        let output = Command::new("hyprctl")
            .args(["keyword", "monitor ,background", &value])
            .output()
            .map_err(|e| format!("failed to execute hyprctl: {e}"))?;
        if output.status.success() {
            return Ok(());
        }
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        return Err(format!("hyprctl failed: {stderr}"));
    }

    Err("unsupported compositor".to_string())
}
