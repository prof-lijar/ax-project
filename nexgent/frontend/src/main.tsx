import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./app/App";
import { AppProviders } from "./app/providers";
import { AuthGate } from "./features/accounts/AuthGate";
import "./styles/tokens.css";
import "./styles/base.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AppProviders>
      <AuthGate><App /></AuthGate>
    </AppProviders>
  </React.StrictMode>
);
