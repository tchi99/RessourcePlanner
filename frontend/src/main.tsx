/// <reference types="vite/client" />

import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";
import "./shift-editor.css";
import "./quick-shift.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
