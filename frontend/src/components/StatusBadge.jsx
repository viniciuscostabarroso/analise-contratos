import React from "react";

export default function StatusBadge({ status }) {
  const map = {
    presente: { label: "Presente", className: "status-presente" },
    ausente: { label: "Ausente", className: "status-ausente" },
    pendente: { label: "Pendente", className: "status-pendente" },
  };

  const normalizedStatus = typeof status === "string" ? status.toLowerCase() : "";
  const config = map[normalizedStatus] || { label: status || "Nao informado", className: "status-pendente" };

  return <span className={`status-badge ${config.className}`}>{config.label}</span>;
}
