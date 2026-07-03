use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NextcloudStatus {
    pub ok: bool,
    pub backend_url: String,
    pub detail: Option<String>,
    pub capabilities_available: bool,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NextcloudFileItem {
    pub path: String,
    pub name: String,
    pub is_directory: bool,
    pub content_type: Option<String>,
    pub size: Option<u64>,
    pub etag: Option<String>,
    pub last_modified: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NextcloudListFilesResponse {
    pub path: String,
    pub depth: u8,
    pub items: Vec<NextcloudFileItem>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NextcloudTextFileResponse {
    pub path: String,
    pub content: String,
    pub content_type: Option<String>,
}
