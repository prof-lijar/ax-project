use crate::domain::{models::TaskSummary, seed};
use crate::error::{AppError, CommandError};

#[tauri::command]
pub fn tasks_list() -> Result<Vec<TaskSummary>, CommandError> {
    Ok(seed::tasks())
}

#[tauri::command]
pub fn tasks_get(id: String) -> Result<TaskSummary, CommandError> {
    seed::tasks()
        .into_iter()
        .find(|task| task.id == id)
        .ok_or(AppError::NotFound { entity: "Task", id })
        .map_err(Into::into)
}
