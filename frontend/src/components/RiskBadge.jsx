import React from "react";

export default function RiskBadge({ level }) {
  const map = {
    alto: { label: "Alto", className: "badge-alto" },
    medio: { label: "Medio", className: "badge-medio" },
    baixo: { label: "Baixo", className: "badge-baixo" },
  };

  const normalizedLevel = typeof level === "string" ? level.toLowerCase() : "";
  const config = map[normalizedLevel] || { label: level || "Nivel nao informado", className: "badge-baixo" };

  return <span className={`badge ${config.className}`}>{config.label}</span>;
}
