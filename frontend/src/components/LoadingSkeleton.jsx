import React from "react";

const STAGE_LABELS = {
  queued: "Documento enfileirado",
  uploading: "Enviando PDF para armazenamento",
  analyzing: "Analisando contrato com IA",
  parsing: "Estruturando resposta",
  completed: "Analise concluida",
  failed: "Falha no processamento",
};

export default function LoadingSkeleton({ stage, progress }) {
  const safeProgress = Math.max(0, Math.min(100, progress || 0));

  return (
    <div className="loading-block">
      <p className="loading-stage">{STAGE_LABELS[stage] || "Processando..."}</p>
      <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={safeProgress}>
        <div className="progress-fill" style={{ width: `${safeProgress}%` }}></div>
      </div>
      <p className="loading-subtext">Progresso estimado: {safeProgress}%</p>

      <div className="skeleton-grid" aria-hidden="true">
        <div className="skeleton-card skeleton-card-wide"></div>
        <div className="skeleton-card"></div>
        <div className="skeleton-card"></div>
        <div className="skeleton-card skeleton-card-tall"></div>
      </div>
    </div>
  );
}
