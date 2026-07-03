use crate::domain::{models::ActivityEvent, seed};
use crate::error::CommandError;

#[tauri::command]
pub fn activity_list() -> Result<Vec<ActivityEvent>, CommandError> {
    Ok(seed::activity())
}
