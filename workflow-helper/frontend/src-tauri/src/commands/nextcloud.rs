use std::time::Duration;

use reqwest::{Client, StatusCode, Url};
use serde::de::DeserializeOwned;
use serde::Deserialize;
use uuid::Uuid;

use crate::domain::nextcloud::{
    NextcloudListFilesResponse, NextcloudStatus, NextcloudTextFileResponse,
};
use crate::error::CommandError;

const DEFAULT_BACKEND_URL: &str = "http://127.0.0.1:8000";

#[derive(Debug, Deserialize)]
struct BackendError {
    detail: String,
}

#[tauri::command]
pub async fn nextcloud_health() -> Result<NextcloudStatus, CommandError> {
    let backend_url = backend_base_url();
    let client = http_client()?;
    let url = backend_endpoint("capabilities")?;

    match client.get(url).send().await {
        Ok(response) if response.status().is_success() => Ok(NextcloudStatus {
            ok: true,
            backend_url,
            detail: None,
            capabilities_available: true,
        }),
        Ok(response) => {
            let status = response.status();
            Ok(NextcloudStatus {
                ok: false,
                backend_url,
                detail: Some(backend_error_message(response, status).await),
                capabilities_available: false,
            })
        }
        Err(error) => Ok(NextcloudStatus {
            ok: false,
            backend_url,
            detail: Some(format!("Unable to reach local backend: {error}")),
            capabilities_available: false,
        }),
    }
}

#[tauri::command]
pub async fn nextcloud_list_files(
    path: String,
) -> Result<NextcloudListFilesResponse, CommandError> {
    let client = http_client()?;
    let mut url = backend_endpoint("files")?;
    url.query_pairs_mut()
        .append_pair("path", &path)
        .append_pair("depth", "1");

    request_json(&client, url).await
}

#[tauri::command]
pub async fn nextcloud_read_text_file(
    path: String,
) -> Result<NextcloudTextFileResponse, CommandError> {
    let client = http_client()?;
    let mut url = backend_endpoint("files/content")?;
    url.query_pairs_mut().append_pair("path", &path);

    request_json(&client, url).await
}

#[tauri::command]
pub fn nextcloud_download_url(path: String) -> Result<String, CommandError> {
    let mut url = backend_endpoint("files/download")?;
    url.query_pairs_mut().append_pair("path", &path);
    Ok(url.to_string())
}

async fn request_json<T>(client: &Client, url: Url) -> Result<T, CommandError>
where
    T: DeserializeOwned,
{
    let response = client.get(url).send().await.map_err(|error| CommandError {
        code: "nextcloud_backend_unreachable",
        message: format!("Unable to reach local backend: {error}"),
        recovery_action: Some("Start the backend and refresh the NextCloud view."),
        correlation_id: Uuid::new_v4().to_string(),
    })?;

    let status = response.status();
    if !status.is_success() {
        return Err(CommandError {
            code: "nextcloud_backend_error",
            message: backend_error_message(response, status).await,
            recovery_action: Some("Check backend and Nextcloud configuration."),
            correlation_id: Uuid::new_v4().to_string(),
        });
    }

    response.json::<T>().await.map_err(|error| CommandError {
        code: "nextcloud_invalid_response",
        message: format!("Backend returned an unreadable Nextcloud response: {error}"),
        recovery_action: Some("Refresh the view and check backend logs."),
        correlation_id: Uuid::new_v4().to_string(),
    })
}

async fn backend_error_message(response: reqwest::Response, status: StatusCode) -> String {
    match response.json::<BackendError>().await {
        Ok(error) => error.detail,
        Err(_) => format!("Local backend returned HTTP {status}."),
    }
}

fn http_client() -> Result<Client, CommandError> {
    Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|error| CommandError {
            code: "nextcloud_client_error",
            message: format!("Unable to create Nextcloud backend client: {error}"),
            recovery_action: Some("Restart the desktop app."),
            correlation_id: Uuid::new_v4().to_string(),
        })
}

fn backend_endpoint(path: &str) -> Result<Url, CommandError> {
    Url::parse(&format!(
        "{}/api/nextcloud/{path}",
        backend_base_url().trim_end_matches('/')
    ))
    .map_err(|error| CommandError {
        code: "nextcloud_backend_url_invalid",
        message: format!("Backend URL is invalid: {error}"),
        recovery_action: Some("Set WH_BACKEND_URL to a valid local backend URL."),
        correlation_id: Uuid::new_v4().to_string(),
    })
}

fn backend_base_url() -> String {
    std::env::var("WH_BACKEND_URL").unwrap_or_else(|_| DEFAULT_BACKEND_URL.to_string())
}
