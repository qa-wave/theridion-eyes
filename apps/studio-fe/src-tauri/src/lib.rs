// Tauri 2 entry point. Mobile-friendly export so the same crate can be
// reused for future iOS/Android targets.

mod event_watcher;
mod sidecar;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_log::Builder::new().build())
        .manage(sidecar::SidecarState::default())
        .invoke_handler(tauri::generate_handler![
            sidecar::get_sidecar_port,
            sidecar::get_sidecar_token,
            register_event_listener,
        ])
        .setup(|app| {
            // Bundled Python sidecar lives in src-tauri/binaries and is
            // bundled by Tauri at build time. In `tauri dev` it gets
            // copied into the dev binary's resource path automatically.
            sidecar::spawn(&app.handle())?;

            // Start the cross-module event watcher on the default workspace
            // root (~/.theridion). The frontend can re-trigger via the
            // `register_event_listener` command to watch a project-specific
            // workspace root.
            let default_workspace = dirs_home().join(".theridion");
            if let Err(e) = event_watcher::start_watching(app.handle().clone(), &default_workspace) {
                log::warn!("[setup] event watcher failed to start: {e}");
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Tauri command: (re-)register the event watcher on a caller-supplied
/// workspace root path. Called by the frontend when the user opens a project
/// stored at a non-default location.
///
/// Returns Ok(()) on success; the error string is surfaced in the JS promise.
#[tauri::command]
fn register_event_listener(
    app: tauri::AppHandle,
    workspace_path: String,
) -> Result<(), String> {
    event_watcher::start_watching(app, &workspace_path)
        .map_err(|e| e.to_string())
}

/// Resolve the user home directory for the default workspace path.
fn dirs_home() -> std::path::PathBuf {
    // Try HOME / USERPROFILE env vars for cross-platform compat without
    // pulling in the `dirs` crate.
    if let Ok(h) = std::env::var("HOME") {
        return std::path::PathBuf::from(h);
    }
    if let Ok(h) = std::env::var("USERPROFILE") {
        return std::path::PathBuf::from(h);
    }
    std::path::PathBuf::from(".")
}
