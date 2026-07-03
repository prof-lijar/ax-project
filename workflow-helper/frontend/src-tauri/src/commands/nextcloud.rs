use std::path::{Path, PathBuf};
use std::time::Duration;

use reqwest::{Client, StatusCode, Url};
use serde::de::DeserializeOwned;
use serde::Deserialize;
use uuid::Uuid;

use crate::domain::nextcloud::{
    NextcloudDownloadResponse, NextcloudListFilesResponse, NextcloudStatus,
    NextcloudTextFileResponse,
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
pub async fn nextcloud_download_file(
    path: String,
) -> Result<NextcloudDownloadResponse, CommandError> {
    let client = http_client()?;
    let mut url = backend_endpoint("files/download")?;
    url.query_pairs_mut().append_pair("path", &path);

    let response = client.get(url).send().await.map_err(|error| CommandError {
        code: "nextcloud_backend_unreachable",
        message: format!("Unable to reach local backend: {error}"),
        recovery_action: Some("Start the backend and try downloading again."),
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

    let filename = safe_filename(&path);
    let downloads_dir = downloads_dir()?;
    let saved_path = available_download_path(&downloads_dir, &filename);
    let bytes = response.bytes().await.map_err(|error| CommandError {
        code: "nextcloud_download_failed",
        message: format!("Unable to read downloaded file: {error}"),
        recovery_action: Some("Try the download again."),
        correlation_id: Uuid::new_v4().to_string(),
    })?;
    let bytes_written = bytes.len() as u64;

    std::fs::create_dir_all(&downloads_dir).map_err(|error| CommandError {
        code: "nextcloud_download_save_failed",
        message: format!("Unable to create Downloads folder: {error}"),
        recovery_action: Some("Check that the Downloads folder is writable."),
        correlation_id: Uuid::new_v4().to_string(),
    })?;

    std::fs::write(&saved_path, &bytes).map_err(|error| CommandError {
        code: "nextcloud_download_save_failed",
        message: format!("Unable to save file to Downloads: {error}"),
        recovery_action: Some("Check that the Downloads folder is writable."),
        correlation_id: Uuid::new_v4().to_string(),
    })?;

    Ok(NextcloudDownloadResponse {
        path,
        filename,
        saved_path: saved_path.to_string_lossy().to_string(),
        bytes_written,
    })
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

fn downloads_dir() -> Result<PathBuf, CommandError> {
    if let Some(path) = std::env::var_os("XDG_DOWNLOAD_DIR").map(PathBuf::from) {
        return Ok(path);
    }

    if let Some(home) = std::env::var_os("HOME").map(PathBuf::from) {
        return Ok(home.join("Downloads"));
    }

    Err(CommandError {
        code: "downloads_dir_unavailable",
        message: "Unable to find the Downloads folder.".into(),
        recovery_action: Some("Set HOME or XDG_DOWNLOAD_DIR and try again."),
        correlation_id: Uuid::new_v4().to_string(),
    })
}

fn safe_filename(path: &str) -> String {
    let filename = path
        .rsplit('/')
        .next()
        .unwrap_or("download")
        .trim()
        .trim_matches('.');

    let safe = filename
        .chars()
        .map(|character| match character {
            '/' | '\\' | ':' | '*' | '?' | '"' | '<' | '>' | '|' => '_',
            _ => character,
        })
        .collect::<String>();

    if safe.is_empty() {
        "download".into()
    } else {
        safe
    }
}

fn available_download_path(downloads_dir: &Path, filename: &str) -> PathBuf {
    let candidate = downloads_dir.join(filename);
    if !candidate.exists() {
        return candidate;
    }

    let path = Path::new(filename);
    let stem = path
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("download");
    let extension = path.extension().and_then(|value| value.to_str());

    for index in 1..1000 {
        let numbered_name = match extension {
            Some(extension) => format!("{stem} ({index}).{extension}"),
            None => format!("{stem} ({index})"),
        };
        let candidate = downloads_dir.join(numbered_name);
        if !candidate.exists() {
            return candidate;
        }
    }

    downloads_dir.join(format!("{}-{}", Uuid::new_v4(), filename))
}
