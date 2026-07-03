use crate::domain::{models::AgentSummary, seed};
use crate::error::{AppError, CommandError};

#[tauri::command]
pub fn agents_list() -> Result<Vec<AgentSummary>, CommandError> {
    Ok(seed::agents())
}

#[tauri::command]
pub fn agents_get(id: String) -> Result<AgentSummary, CommandError> {
    seed::agents()
        .into_iter()
        .find(|agent| agent.id == id)
        .ok_or(AppError::NotFound { entity: "Agent", id })
        .map_err(Into::into)
}
