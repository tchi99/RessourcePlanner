/// <reference types="vite/client" />

import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { AuthProvider } from "./AuthContext";
import "./styles.css";
import "./shift-editor.css";
import "./quick-shift.css";
import "./demands.css";
import "./demand-history.css";
import "./demand-periods.css";
import "./demand-workflow.css";
import "./medium-term.css";
import "./projects.css";
import "./resource-admin.css";
import "./segments.css";
import "./segment-parent.css";
import "./technician-schedule.css";
import "./communications.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </React.StrictMode>,
);
