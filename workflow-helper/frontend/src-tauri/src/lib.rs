mod commands;
mod domain;
mod error;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            commands::workspace::workspace_get,
            commands::system::system_health,
            commands::tasks::tasks_list,
            commands::tasks::tasks_get,
            commands::approvals::approvals_list,
            commands::approvals::approvals_get,
            commands::agents::agents_list,
            commands::agents::agents_get,
            commands::activity::activity_list
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Workflow Helper desktop app");
}
