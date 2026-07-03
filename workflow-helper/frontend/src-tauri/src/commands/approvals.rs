use crate::domain::{models::ApprovalRequest, seed};
use crate::error::{AppError, CommandError};

#[tauri::command]
pub fn approvals_list() -> Result<Vec<ApprovalRequest>, CommandError> {
    Ok(seed::approvals())
}

#[tauri::command]
pub fn approvals_get(id: String) -> Result<ApprovalRequest, CommandError> {
    seed::approvals()
        .into_iter()
        .find(|approval| approval.id == id)
        .ok_or(AppError::NotFound {
            entity: "Approval request",
            id,
        })
        .map_err(Into::into)
}
