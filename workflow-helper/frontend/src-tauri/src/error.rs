use serde::Serialize;
use uuid::Uuid;

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("{entity} with id '{id}' was not found")]
    NotFound { entity: &'static str, id: String },
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CommandError {
    pub code: &'static str,
    pub message: String,
    pub recovery_action: Option<&'static str>,
    pub correlation_id: String,
}

impl From<AppError> for CommandError {
    fn from(error: AppError) -> Self {
        match error {
            AppError::NotFound { entity, id } => Self {
                code: "not_found",
                message: format!("{entity} with id '{id}' was not found"),
                recovery_action: Some("Refresh the view and try again."),
                correlation_id: Uuid::new_v4().to_string(),
            },
        }
    }
}
