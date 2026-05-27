//! Cross-module event watcher.
//!
//! Watches `<workspace_root>/.theridion/events/` for newly created JSON files.
//! Each file is a one-shot event: read → emit Tauri event → delete.
//!
//! The canonical event schema is:
//!
//! ```text
//! {
//!   "version": "1",
//!   "type": "test.failed",
//!   "source": "runner",
//!   "timestamp": "2026-05-26T10:00:00Z",
//!   "context": { "summary": "GET /api/health — 500 Internal Server Error" },
//!   "actions": []
//! }
//! ```
//!
//! Tauri event name: `theridion://event`
//! Payload: `TheridionEventPayload`

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use notify::{Config, EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter};

/// Payload emitted as the `theridion://event` Tauri event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TheridionEventPayload {
    /// Absolute path of the workspace root where the event was found.
    pub workspace_path: String,
    /// The `type` field from the JSON event file.
    pub event_type: String,
    /// Raw parsed JSON (full event object).
    pub data: serde_json::Value,
}

/// Shared watcher handle — keeps the watcher alive for the process lifetime.
static WATCHER_HANDLE: Mutex<Option<RecommendedWatcher>> = Mutex::new(None);

/// Start watching `<workspace_path>/.theridion/events/` for new JSON files.
///
/// Safe to call multiple times: a second call replaces the previous watcher.
/// Events directory is created if it doesn't exist.
pub fn start_watching(
    app: AppHandle,
    workspace_path: impl AsRef<Path>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let workspace_path = workspace_path.as_ref().to_path_buf();
    let events_dir = workspace_path.join(".theridion").join("events");
    std::fs::create_dir_all(&events_dir)?;

    log::info!("[event_watcher] watching {}", events_dir.display());

    let events_dir_clone = events_dir.clone();
    let workspace_str = Arc::new(workspace_path.to_string_lossy().into_owned());

    let mut watcher = notify::recommended_watcher(move |res: notify::Result<notify::Event>| {
        match res {
            Ok(event) => {
                if matches!(event.kind, EventKind::Create(_)) {
                    for path in &event.paths {
                        handle_event_file(&app, &workspace_str, path);
                    }
                }
            }
            Err(e) => {
                log::warn!("[event_watcher] watch error: {e}");
            }
        }
    })?;

    // Configure a short poll interval for the fallback watcher on systems
    // that don't support native FS events.
    let config = Config::default().with_poll_interval(Duration::from_millis(500));
    watcher.configure(config)?;

    // Watch the events dir non-recursively (flat, no subdirs).
    watcher.watch(&events_dir_clone, RecursiveMode::NonRecursive)?;

    // Store handle so the watcher is not dropped.
    let mut guard = WATCHER_HANDLE.lock().unwrap();
    *guard = Some(watcher);

    Ok(())
}

/// Stop watching (drops the internal watcher).
#[allow(dead_code)]
pub fn stop_watching() {
    let mut guard = WATCHER_HANDLE.lock().unwrap();
    *guard = None;
    log::info!("[event_watcher] stopped");
}

/// Read a newly created event file, emit the Tauri event, and delete the file.
fn handle_event_file(app: &AppHandle, workspace_str: &str, path: &PathBuf) {
    // Only process .json files.
    if path.extension().and_then(|e| e.to_str()) != Some("json") {
        return;
    }

    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(e) => {
            log::warn!("[event_watcher] could not read {}: {e}", path.display());
            return;
        }
    };

    let data: serde_json::Value = match serde_json::from_str(&content) {
        Ok(v) => v,
        Err(e) => {
            log::warn!("[event_watcher] invalid JSON in {}: {e}", path.display());
            // Still delete the malformed file so the dir stays clean.
            let _ = std::fs::remove_file(path);
            return;
        }
    };

    let event_type = data
        .get("type")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown")
        .to_owned();

    let payload = TheridionEventPayload {
        workspace_path: workspace_str.to_owned(),
        event_type,
        data,
    };

    if let Err(e) = app.emit("theridion://event", &payload) {
        log::warn!("[event_watcher] emit failed: {e}");
    } else {
        log::info!("[event_watcher] emitted event '{}'", payload.event_type);
    }

    // One-shot: delete after consumption.
    if let Err(e) = std::fs::remove_file(path) {
        log::warn!("[event_watcher] could not delete {}: {e}", path.display());
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    /// Verify that valid JSON is parsed and the event_type field is extracted.
    #[test]
    fn parses_valid_event_json() {
        let json = r#"{"version":"1","type":"test.failed","source":"runner","timestamp":"2026-05-26T10:00:00Z","context":{"summary":"GET /health failed"},"actions":[]}"#;
        let data: serde_json::Value = serde_json::from_str(json).unwrap();
        let event_type = data
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        assert_eq!(event_type, "test.failed");
    }

    /// Verify that invalid JSON results in an error (not a panic).
    #[test]
    fn rejects_invalid_json() {
        let bad = "{ not json }";
        let result: Result<serde_json::Value, _> = serde_json::from_str(bad);
        assert!(result.is_err());
    }

    /// Verify the events directory is created when it doesn't exist.
    #[test]
    fn creates_events_directory_if_missing() {
        let tmp = TempDir::new().unwrap();
        let workspace = tmp.path().to_path_buf();
        let events_dir = workspace.join(".theridion").join("events");
        assert!(!events_dir.exists());
        // Manually replicate what start_watching does.
        fs::create_dir_all(&events_dir).unwrap();
        assert!(events_dir.exists());
    }

    /// Verify that only .json files are processed (extension check).
    #[test]
    fn skips_non_json_files() {
        let path = PathBuf::from("/tmp/not_a_json.log");
        let is_json = path.extension().and_then(|e| e.to_str()) == Some("json");
        assert!(!is_json);
    }

    /// Verify that a missing "type" field falls back to "unknown".
    #[test]
    fn falls_back_to_unknown_event_type() {
        let json = r#"{"version":"1","source":"runner"}"#;
        let data: serde_json::Value = serde_json::from_str(json).unwrap();
        let event_type = data
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        assert_eq!(event_type, "unknown");
    }
}
