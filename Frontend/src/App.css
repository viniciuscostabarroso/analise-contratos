import React, { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import "./App.css";

// ⚠️ Adicione o arquivo logo-servinformacion.png em src/assets/
// Se não tiver o logo, comente a linha abaixo e use o texto no header.
// import logo from "./assets/logo-servinformacion.png";

// =============================================
// COMPONENTES AUXILIARES
// =============================================

const RiskBadge = ({ level }) => {
  const map = {
    alto:  { label: "Alto",  className: "badge-alto" },
    medio: { label: "Médio", className: "badge-medio" },
    baixo: { label: "Baixo", className: "badge-baixo" },
  };
  const config = map[level?.toLowerCase()] || { label: level, className: "badge-baixo" };
  return <span className={`badge ${config.className}`}>{config.label}</span>;
};

const StatusBadge = ({ status }) => {
  const map = {
    presente: { label: "✔ Presente", className: "status-presente" },
    ausente:  { label: "✘ Ausente",  className: "status-ausente" },
    pendente: { label: "⚠ Pendente", className: "status-pendente" },
  };
  const config = map[status?.toLowerCase()] || { label: status, className: "status-pendente" };
  return <span className={`status-badge ${config.className}`}>{config.label}</span>;
};

const SectionCard = ({ title, icon, children }) => (
  <div className="section-card">
    <h3 className="section-title">
      <span className="section-icon">{icon}</span> {title}
    </h3>
    {children}
  </div>
);

// =============================================
// COMPONENTE PRINCIPAL
// =============================================

export default function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
      setResult(null);
      setError(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
  });

  const handleAnalyze = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "Erro desconhecido na análise.");
      }

      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setResult(null);
    setError(null);
  };

  const analysis = result?.analysis;

  return (
    <div className="app-wrapper">
      {/* HEADER */}
      <header className="app-header">
        <div className="header-inner">
          <div className="header-logo">
            {/* Se tiver o logo: <img src={logo} alt="Servinformacion" className="logo-img" /> */}
            <div className="logo-text">
              <span className="logo-serv">SERV</span>
              <span className="logo-info">INFORMACION</span>
            </div>
          </div>
          <div className="header-title">
            <h1>Análise Inteligente de Documentos & Contratos</h1>
            <p>Powered by Google Cloud Vertex AI · Gemini 2.5 Flash</p>
          </div>
        </div>
      </header>

      <main className="main-content">
        {/* UPLOAD SECTION */}
        {!result && (
          <div className="upload-section">
            <div
              {...getRootProps()}
              className={`dropzone ${isDragActive ? "dropzone-active" : ""} ${file ? "dropzone-filled" : ""}`}
            >
              <input {...getInputProps()} />
              <div className="dropzone-content">
                {file ? (
                  <>
                    <div className="file-icon">📄</div>
                    <p className="file-name">{file.name}</p>
                    <p className="file-size">{(file.size / 1024 / 1024).toFixed(2)} MB · PDF pronto para análise</p>
                  </>
                ) : (
                  <>
                    <div className="upload-icon">☁️</div>
                    <p className="dropzone-text">
                      {isDragActive ? "Solte o PDF aqui!" : "Arraste e solte um arquivo PDF aqui"}
                    </p>
                    <p className="dropzone-subtext">ou clique para selecionar</p>
                    <span className="dropzone-hint">Suporta contratos, termos de referência, acordos e outros documentos PDF</span>
                  </>
                )}
              </div>
            </div>

            {file && !loading && (
              <button className="btn-analyze" onClick={handleAnalyze}>
                🔍 Analisar Documento com IA
              </button>
            )}

            {loading && (
              <div className="loading-container">
                <div className="spinner"></div>
                <p className="loading-text">Analisando documento com Gemini 2.5 Flash...</p>
                <p className="loading-subtext">Isso pode levar alguns segundos dependendo do tamanho do arquivo.</p>
              </div>
            )}

            {error && (
              <div className="error-box">
                <strong>⚠ Erro na análise:</strong> {error}
              </div>
            )}
          </div>
        )}

        {/* RESULTS SECTION */}
        {result && analysis && (
          <div className="results-section">
            {/* HEADER DO RESULTADO */}
            <div className="result-header">
              <div className="result-header-left">
                <h2>{analysis.titulo_documento || result.file_name}</h2>
                <p className="result-meta">
                  📎 {result.file_name}
                  {analysis.numero_paginas_analisadas > 0 && (
                    <span> · {analysis.numero_paginas_analisadas} página(s)</span>
                  )}
                </p>
              </div>
              <button className="btn-reset" onClick={handleReset}>
                ↩ Nova Análise
              </button>
            </div>

            {/* RESUMO EXECUTIVO */}
            <div className="executive-summary">
              <h3>📋 Resumo Executivo</h3>
              <p>{analysis.resumo_executivo}</p>
              <div className="summary-tags">
                {analysis.valor_contrato && analysis.valor_contrato !== "Não especificado" && (
                  <div className="tag">💰 {analysis.valor_contrato}</div>
                )}
                {analysis.objeto_contrato && (
                  <div className="tag">📌 {analysis.objeto_contrato?.substring(0, 80)}{analysis.objeto_contrato?.length > 80 ? "..." : ""}</div>
                )}
              </div>
            </div>

            <div className="results-grid">
              {/* PARTES ENVOLVIDAS */}
              {analysis.partes_envolvidas?.length > 0 && (
                <SectionCard title="Partes Envolvidas" icon="👥">
                  <div className="parties-list">
                    {analysis.partes_envolvidas.map((p, i) => (
                      <div key={i} className="party-item">
                        <span className="party-role">{p.papel}</span>
                        <span className="party-name">{p.nome}</span>
                        {p.documento && <span className="party-doc">{p.documento}</span>}
                      </div>
                    ))}
                  </div>
                </SectionCard>
              )}

              {/* DATAS E PRAZOS */}
              {analysis.datas_e_prazos?.length > 0 && (
                <SectionCard title="Datas & Prazos" icon="📅">
                  <div className="dates-list">
                    {analysis.datas_e_prazos.map((d, i) => (
                      <div key={i} className="date-item">
                        <span className="date-event">{d.evento}</span>
                        <span className="date-value">{d.data_prazo}</span>
                      </div>
                    ))}
                  </div>
                </SectionCard>
              )}
            </div>

            {/* PONTOS PRINCIPAIS */}
            {analysis.pontos_principais?.length > 0 && (
              <SectionCard title="Pontos Principais" icon="🎯">
                <div className="points-grid">
                  {analysis.pontos_principais.map((p, i) => (
                    <div key={i} className="point-card">
                      <h4>{p.topico}</h4>
                      <p>{p.descricao}</p>
                    </div>
                  ))}
                </div>
              </SectionCard>
            )}

            {/* CLÁUSULAS IMPORTANTES */}
            {analysis.clausulas_importantes?.length > 0 && (
              <SectionCard title="Cláusulas Importantes" icon="⚖️">
                <div className="clauses-list">
                  {analysis.clausulas_importantes.map((c, i) => (
                    <div key={i} className="clause-item">
                      <div className="clause-header">
                        <span className="clause-number">{c.numero_clausula}</span>
                        <span className="clause-title">{c.titulo}</span>
                      </div>
                      <p className="clause-summary">{c.resumo}</p>
                    </div>
                  ))}
                </div>
              </SectionCard>
            )}

            {/* OBRIGAÇÕES */}
            <div className="results-grid">
              {analysis.obrigacoes_contratante?.length > 0 && (
                <SectionCard title="Obrigações do Contratante" icon="📌">
                  <ul className="obligations-list">
                    {analysis.obrigacoes_contratante.map((o, i) => (
                      <li key={i}>{o}</li>
                    ))}
                  </ul>
                </SectionCard>
              )}
              {analysis.obrigacoes_contratado?.length > 0 && (
                <SectionCard title="Obrigações do Contratado" icon="📎">
                  <ul className="obligations-list">
                    {analysis.obrigacoes_contratado.map((o, i) => (
                      <li key={i}>{o}</li>
                    ))}
                  </ul>
                </SectionCard>
              )}
            </div>

            {/* ALERTAS E RISCOS */}
            {analysis.alertas_e_riscos?.length > 0 && (
              <SectionCard title="Alertas & Riscos" icon="🚨">
                <div className="risks-list">
                  {analysis.alertas_e_riscos.map((r, i) => (
                    <div key={i} className={`risk-item risk-${r.nivel?.toLowerCase()}`}>
                      <div className="risk-header">
                        <RiskBadge level={r.nivel} />
                        <span className="risk-category">{r.categoria}</span>
                      </div>
                      <p className="risk-description">{r.descricao}</p>
                    </div>
                  ))}
                </div>
              </SectionCard>
            )}

            {/* CHECKLIST DE VALIDAÇÃO */}
            {analysis.checklist_validacao?.length > 0 && (
              <SectionCard title="Checklist de Validação" icon="✅">
                <div className="checklist-grid">
                  {analysis.checklist_validacao.map((c, i) => (
                    <div key={i} className="checklist-item">
                      <StatusBadge status={c.status} />
                      <span className="checklist-label">{c.item}</span>
                    </div>
                  ))}
                </div>
              </SectionCard>
            )}

            <div className="result-footer">
              <p>Análise gerada por <strong>Google Vertex AI · Gemini 2.5 Flash</strong> · Servinformacion Demo Platform</p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
