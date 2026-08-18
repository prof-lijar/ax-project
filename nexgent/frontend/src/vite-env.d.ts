/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AGENT_SERVER_BASE_URL?: string;
  readonly VITE_BACKEND_URL?: string;
  readonly VITE_BACKEND_PORT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.module.css" {
  const classes: Record<string, string>;
  export default classes;
}
