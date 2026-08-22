import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import ProbeViewer from "../app/ProbeViewer";
import "../app/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ProbeViewer />
  </StrictMode>,
);
