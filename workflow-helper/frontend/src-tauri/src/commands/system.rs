use crate::domain::{models::SystemHealth, seed};
use crate::error::CommandError;

#[tauri::command]
pub fn system_health() -> Result<SystemHealth, CommandError> {
    Ok(seed::system_health())
}
