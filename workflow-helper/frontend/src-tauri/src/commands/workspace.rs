use crate::domain::{models::WorkspaceOverview, seed};
use crate::error::CommandError;

#[tauri::command]
pub fn workspace_get() -> Result<WorkspaceOverview, CommandError> {
    Ok(seed::workspace())
}
