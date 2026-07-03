fn main() {
    ensure_icon();
    tauri_build::build();
}

fn ensure_icon() {
    let manifest_dir =
        std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR is set by Cargo");
    let icon_dir = std::path::Path::new(&manifest_dir).join("icons");
    let icon_path = icon_dir.join("icon.png");

    std::fs::create_dir_all(&icon_dir).expect("failed to create Tauri icon directory");
    std::fs::write(icon_path, ICON_PNG).expect("failed to write placeholder Tauri icon");
}

const ICON_PNG: &[u8] = &[
    137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0, 0, 1, 8,
    6, 0, 0, 0, 31, 21, 196, 137, 0, 0, 0, 13, 73, 68, 65, 84, 120, 218, 99, 208, 203, 143,
    251, 15, 0, 3, 197, 1, 251, 19, 175, 116, 107, 0, 0, 0, 0, 73, 69, 78, 68, 174, 66, 96,
    130,
];
