# Nexgent Desktop

Tauri 2 desktop shell for the Nexgent operator console.

## Prerequisites

- Node.js LTS with npm
- Rust stable
- Linux Tauri system dependencies, including WebKitGTK 4.1

For Debian/Ubuntu:

```bash
sudo apt update
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

## Development

```bash
npm install
npm run tauri:dev
```

## Web Preview

For preview on this machine only:

```bash
npm run dev -- --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:5173/
```

For access from another PC on the same network, bind Vite to all interfaces:

```bash
npm run dev -- --host 0.0.0.0
```

Open from the other PC, replacing the IP address if this machine changes:

```text
http://192.168.0.18:5173/
```

If the other PC cannot connect, confirm the server prints a `Network:` URL, then check that local firewall rules allow inbound TCP traffic on port `5173`.

## Build

```bash
npm run tauri:build
```

The first implementation uses local command-backed sample data. The frontend API is isolated in `src/shared/api`, so persistent SQLite commands can replace the mock data without changing UI components.

## Icons

UI icons use `lucide-react`. Lucide provides tree-shakable React SVG components with TypeScript support and is released under the ISC license; inherited Feather icons are MIT licensed.
