import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { AnchorNav, LoadingSkeleton, PaginatedList, RiskBadge, SectionCard, StatusBadge } from "./components";
import logoServinformacion from "./assets/logo-servinformacion.png";
import "./app.css";

const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;
const POLL_INTERVAL_MS = 2500;
const POLL_TIMEOUT_MS = 4 * 60 * 1000;
const REQUEST_TIMEOUT_MS = 30 * 1000;

function parseResponseJson(text) {
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function getErrorByType(type, messageOverride) {
  const catalog = {
    invalid_file: {
      title: "Arquivo invalido",
      message: "Selecione apenas um PDF valido para continuar.",
    },
    file_too_large: {
      title: "Arquivo muito grande",
      message: "O PDF excede o limite permitido para processamento.",
    },
    timeout: {
      title: "Tempo de processamento excedido",
      message: "A analise demorou alem do esperado. Tente novamente com um arquivo menor.",
    },
    queue_full: {
      title: "Fila de processamento cheia",
      message: "O servico esta com alta demanda no momento. Aguarde alguns segundos e tente novamente.",
    },
    api_unavailable: {
      title: "API indisponivel",
      message: "Nao foi possivel conectar ao servico agora. Verifique a conexao e tente novamente.",
    },
    processing_error: {
      title: "Falha no processamento",
      message: "Ocorreu um erro durante a analise do documento.",
    },
    parse_error: {
      title: "Falha na leitura do resultado",
      message: "A resposta da IA nao pode ser interpretada corretamente.",
    },
    dependency_error: {
      title: "Dependencia indisponivel",
      message: "O servico esta sem dependencias necessarias para analisar o arquivo.",
    },
    server_error: {
      title: "Erro interno no servidor",
      message: "O servidor encontrou um erro inesperado.",
    },
    not_found: {
      title: "Job nao encontrado",
      message: "A referencia da analise expirou ou nao foi encontrada.",
    },
    unknown: {
      title: "Erro inesperado",
      message: "Nao foi possivel concluir a operacao.",
    },
  };

  const base = catalog[type] || catalog.unknown;
  return {
    type,
    title: base.title,
    message: messageOverride || base.message,
  };
}

async function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

function getJobErrorInfo(jobData) {
  return getErrorByType(jobData?.error_type || "processing_error", jobData?.error_message);
}

export default function App() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [job, setJob] = useState(null);

  const pollStartedAtRef = useRef(null);
  const pollRequestInFlightRef = useRef(false);

  const resetAnalysisState = useCallback(() => {
    setResult(null);
    setError(null);
    setJob(null);
    setLoading(false);
    pollStartedAtRef.current = null;
    pollRequestInFlightRef.current = false;
  }, []);

  const onDropAccepted = useCallback((acceptedFiles) => {
    if (acceptedFiles.length === 0) {
      return;
    }

    setFile(acceptedFiles[0]);
    setResult(null);
    setError(null);
    setJob(null);
  }, []);

  const onDropRejected = useCallback((fileRejections) => {
    const firstError = fileRejections?.[0]?.errors?.[0];

    if (!firstError) {
      setError(getErrorByType("invalid_file"));
      return;
    }

    if (firstError.code === "file-too-large") {
      setError(
        getErrorByType(
          "file_too_large",
          `O limite atual e ${(MAX_FILE_SIZE_BYTES / 1024 / 1024).toFixed(0)}MB por arquivo.`
        )
      );
      return;
    }

    if (firstError.code === "file-invalid-type") {
      setError(getErrorByType("invalid_file", "Somente arquivos PDF sao aceitos."));
      return;
    }

    if (firstError.code === "too-many-files") {
      setError(getErrorByType("invalid_file", "Envie apenas um arquivo por analise."));
      return;
    }

    setError(getErrorByType("invalid_file", firstError.message));
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDropAccepted,
    onDropRejected,
    accept: { "application/pdf": [".pdf"] },
    maxFiles: 1,
    maxSize: MAX_FILE_SIZE_BYTES,
  });

  const handleBackendError = useCallback((status, payload, fallbackMessage) => {
    if (status === 503) {
      return getErrorByType("api_unavailable");
    }

    if (status === 408 || status === 504) {
      return getErrorByType("timeout");
    }

    if (payload && typeof payload === "object") {
      return getErrorByType(payload.error_type || "processing_error", payload.error || payload.message);
    }

    return getErrorByType("server_error", fallbackMessage);
  }, []);

  const fetchResult = useCallback(
    async (jobId) => {
      const response = await fetchWithTimeout(`/api/analyze/${jobId}/result`, {}, REQUEST_TIMEOUT_MS);
      const payload = parseResponseJson(await response.text());

      if (response.status === 202) {
        return false;
      }

      if (!response.ok || !payload?.success) {
        throw handleBackendError(response.status, payload, "Nao foi possivel obter o resultado da analise.");
      }

      setResult(payload);
      setLoading(false);
      setJob(payload.job || null);
      return true;
    },
    [handleBackendError]
  );

  const pollJobStatus = useCallback(async () => {
    if (!job?.job_id || pollRequestInFlightRef.current) {
      return;
    }

    if (!pollStartedAtRef.current) {
      pollStartedAtRef.current = Date.now();
    }

    if (Date.now() - pollStartedAtRef.current > POLL_TIMEOUT_MS) {
      setError(getErrorByType("timeout"));
      setLoading(false);
      setJob(null);
      return;
    }

    pollRequestInFlightRef.current = true;

    try {
      const response = await fetchWithTimeout(`/api/analyze/${job.job_id}/status`, {}, REQUEST_TIMEOUT_MS);
      const payload = parseResponseJson(await response.text());

      if (!response.ok || !payload?.success) {
        throw handleBackendError(response.status, payload, "Nao foi possivel consultar o status da analise.");
      }

      const nextJob = payload.job || null;
      if (nextJob) {
        setJob(nextJob);
      }

      if (nextJob?.status === "failed") {
        setError(getJobErrorInfo(nextJob));
        setLoading(false);
        return;
      }

      if (nextJob?.status === "completed") {
        await fetchResult(job.job_id);
      }
    } catch (err) {
      if (err?.name === "AbortError") {
        setError(getErrorByType("timeout"));
      } else if (err?.type && err?.title) {
        setError(err);
      } else {
        setError(getErrorByType("api_unavailable"));
      }
      setLoading(false);
    } finally {
      pollRequestInFlightRef.current = false;
    }
  }, [fetchResult, handleBackendError, job]);

  useEffect(() => {
    if (!loading || !job?.job_id) {
      return undefined;
    }

    pollJobStatus();
    const intervalId = setInterval(pollJobStatus, POLL_INTERVAL_MS);

    return () => {
      clearInterval(intervalId);
    };
  }, [loading, job?.job_id, pollJobStatus]);

  const handleAnalyze = async () => {
    if (!file) {
      return;
    }

    setLoading(true);
    setResult(null);
    setError(null);
    pollStartedAtRef.current = Date.now();

    let enqueueSucceeded = false;

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetchWithTimeout(
        "/api/analyze",
        {
          method: "POST",
          body: formData,
        },
        REQUEST_TIMEOUT_MS
      );

      const payload = parseResponseJson(await response.text());
      if (!response.ok || !payload?.success) {
        throw handleBackendError(response.status, payload, "Nao foi possivel iniciar a analise.");
      }

      if (!payload?.job?.job_id) {
        throw getErrorByType("server_error", "A API nao retornou o identificador do job.");
      }

      enqueueSucceeded = true;
      setJob(payload.job);
    } catch (err) {
      if (err?.name === "AbortError") {
        setError(getErrorByType("timeout", "O servidor demorou para responder ao iniciar a analise."));
      } else if (err?.type && err?.title) {
        setError(err);
      } else {
        setError(getErrorByType("api_unavailable"));
      }
    } finally {
      if (!enqueueSucceeded) {
        setLoading(false);
      }
    }
  };

  const handleReset = () => {
    setFile(null);
    resetAnalysisState();
  };

  const analysis = result?.analysis;
  const sections = useMemo(() => {
    if (!analysis) {
      return [];
    }

    const list = [{ id: "resumo", label: "Resumo" }];

    if (analysis.partes_envolvidas?.length) list.push({ id: "partes", label: "Partes" });
    if (analysis.datas_e_prazos?.length) list.push({ id: "prazos", label: "Prazos" });
    if (analysis.pontos_principais?.length) list.push({ id: "pontos", label: "Pontos" });
    if (analysis.clausulas_importantes?.length) list.push({ id: "clausulas", label: "Clausulas" });
    if (analysis.obrigacoes_contratante?.length || analysis.obrigacoes_contratado?.length) list.push({ id: "obrigacoes", label: "Obrigacoes" });
    if (analysis.alertas_e_riscos?.length) list.push({ id: "riscos", label: "Riscos" });
    if (analysis.checklist_validacao?.length) list.push({ id: "checklist", label: "Checklist" });

    return list;
  }, [analysis]);

  return (
    <div className="app-wrapper">
      <header className="app-header">
        <div className="header-inner">
          <div className="header-logo">
            <img src={logoServinformacion} alt="Servinformacion" className="logo-img" />
          </div>
          <div className="header-title">
            <h1>Analise Inteligente de Documentos e Contratos</h1>
            <p>Powered by Google Cloud Vertex AI · Gemini 2.5 Flash</p>
          </div>
        </div>
      </header>

      <main className="main-content">
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
                    <div className="file-icon">PDF</div>
                    <p className="file-name">{file.name}</p>
                    <p className="file-size">{(file.size / 1024 / 1024).toFixed(2)} MB · pronto para analise</p>
                  </>
                ) : (
                  <>
                    <div className="upload-icon">UPLOAD</div>
                    <p className="dropzone-text">
                      {isDragActive ? "Solte o PDF aqui" : "Arraste e solte um arquivo PDF aqui"}
                    </p>
                    <p className="dropzone-subtext">ou clique para selecionar</p>
                    <span className="dropzone-hint">Limite de 50MB · 1 arquivo por analise</span>
                  </>
                )}
              </div>
            </div>

            {file && !loading && (
              <button className="btn-analyze" onClick={handleAnalyze} type="button">
                Iniciar Analise Assincrona
              </button>
            )}

            {loading && <LoadingSkeleton stage={job?.stage} progress={job?.progress} />}

            {error && (
              <div className="error-box error-box-typed" role="alert">
                <strong>{error.title}</strong>
                <p>{error.message}</p>
              </div>
            )}
          </div>
        )}

        {result && analysis && (
          <div className="results-section">
            <div className="result-header" id="resumo">
              <div className="result-header-left">
                <h2>{analysis.titulo_documento || result.file_name}</h2>
                <p className="result-meta">
                  Arquivo: {result.file_name}
                  {analysis.numero_paginas_analisadas > 0 && <span> · {analysis.numero_paginas_analisadas} pagina(s)</span>}
                </p>
              </div>
              <button className="btn-reset" type="button" onClick={handleReset}>
                Nova Analise
              </button>
            </div>

            <AnchorNav sections={sections} />

            <div className="executive-summary">
              <h3>Resumo Executivo</h3>
              <p>{analysis.resumo_executivo}</p>
              <div className="summary-tags">
                {analysis.valor_contrato && analysis.valor_contrato !== "Nao especificado" && (
                  <div className="tag">Valor: {analysis.valor_contrato}</div>
                )}
                {analysis.objeto_contrato && (
                  <div className="tag">
                    Objeto: {analysis.objeto_contrato?.substring(0, 80)}
                    {analysis.objeto_contrato?.length > 80 ? "..." : ""}
                  </div>
                )}
              </div>
            </div>

            <div className="results-grid" id="partes-prazos-grid">
              {analysis.partes_envolvidas?.length > 0 && (
                <SectionCard sectionId="partes" title="Partes Envolvidas" icon="01">
                  <PaginatedList
                    items={analysis.partes_envolvidas}
                    pageSize={6}
                    className="parties-list"
                    itemLabel="partes"
                    renderItem={(party, index) => (
                      <div key={`${party.nome || "parte"}-${index}`} className="party-item">
                        <span className="party-role">{party.papel}</span>
                        <span className="party-name">{party.nome}</span>
                        {party.documento && <span className="party-doc">{party.documento}</span>}
                      </div>
                    )}
                  />
                </SectionCard>
              )}

              {analysis.datas_e_prazos?.length > 0 && (
                <SectionCard sectionId="prazos" title="Datas e Prazos" icon="02">
                  <PaginatedList
                    items={analysis.datas_e_prazos}
                    pageSize={8}
                    className="dates-list"
                    itemLabel="eventos"
                    renderItem={(dateItem, index) => (
                      <div key={`${dateItem.evento || "evento"}-${index}`} className="date-item">
                        <span className="date-event">{dateItem.evento}</span>
                        <span className="date-value">{dateItem.data_prazo}</span>
                      </div>
                    )}
                  />
                </SectionCard>
              )}
            </div>

            {analysis.pontos_principais?.length > 0 && (
              <SectionCard sectionId="pontos" title="Pontos Principais" icon="03">
                <PaginatedList
                  items={analysis.pontos_principais}
                  pageSize={4}
                  className="points-grid"
                  itemLabel="pontos"
                  renderItem={(point, index) => (
                    <div key={`${point.topico || "ponto"}-${index}`} className="point-card">
                      <h4>{point.topico}</h4>
                      <p>{point.descricao}</p>
                    </div>
                  )}
                />
              </SectionCard>
            )}

            {analysis.clausulas_importantes?.length > 0 && (
              <SectionCard sectionId="clausulas" title="Clausulas Importantes" icon="04">
                <PaginatedList
                  items={analysis.clausulas_importantes}
                  pageSize={4}
                  className="clauses-list"
                  itemLabel="clausulas"
                  renderItem={(clause, index) => (
                    <div key={`${clause.numero_clausula || "clausula"}-${index}`} className="clause-item">
                      <div className="clause-header">
                        <span className="clause-number">{clause.numero_clausula}</span>
                        <span className="clause-title">{clause.titulo}</span>
                      </div>
                      <p className="clause-summary">{clause.resumo}</p>
                    </div>
                  )}
                />
              </SectionCard>
            )}

            <div className="results-grid" id="obrigacoes">
              {analysis.obrigacoes_contratante?.length > 0 && (
                <SectionCard title="Obrigacoes do Contratante" icon="05">
                  <PaginatedList
                    items={analysis.obrigacoes_contratante}
                    pageSize={8}
                    className="obligations-list"
                    itemLabel="obrigacoes"
                    renderItem={(item, index) => (
                      <div key={`contratante-${index}`} className="obligation-item">
                        {item}
                      </div>
                    )}
                  />
                </SectionCard>
              )}

              {analysis.obrigacoes_contratado?.length > 0 && (
                <SectionCard title="Obrigacoes do Contratado" icon="06">
                  <PaginatedList
                    items={analysis.obrigacoes_contratado}
                    pageSize={8}
                    className="obligations-list"
                    itemLabel="obrigacoes"
                    renderItem={(item, index) => (
                      <div key={`contratado-${index}`} className="obligation-item">
                        {item}
                      </div>
                    )}
                  />
                </SectionCard>
              )}
            </div>

            {analysis.alertas_e_riscos?.length > 0 && (
              <SectionCard sectionId="riscos" title="Alertas e Riscos" icon="07">
                <PaginatedList
                  items={analysis.alertas_e_riscos}
                  pageSize={5}
                  className="risks-list"
                  itemLabel="riscos"
                  renderItem={(risk, index) => (
                    <div key={`${risk.categoria || "risco"}-${index}`} className={`risk-item risk-${risk.nivel?.toLowerCase()}`}>
                      <div className="risk-header">
                        <RiskBadge level={risk.nivel} />
                        <span className="risk-category">{risk.categoria}</span>
                      </div>
                      <p className="risk-description">{risk.descricao}</p>
                    </div>
                  )}
                />
              </SectionCard>
            )}

            {analysis.checklist_validacao?.length > 0 && (
              <SectionCard sectionId="checklist" title="Checklist de Validacao" icon="08">
                <PaginatedList
                  items={analysis.checklist_validacao}
                  pageSize={8}
                  className="checklist-grid"
                  itemLabel="itens"
                  renderItem={(checkItem, index) => (
                    <div key={`${checkItem.item || "check"}-${index}`} className="checklist-item">
                      <StatusBadge status={checkItem.status} />
                      <span className="checklist-label">{checkItem.item}</span>
                    </div>
                  )}
                />
              </SectionCard>
            )}

            <div className="result-footer">
              <p>
                Analise gerada por <strong>Google Vertex AI · Gemini 2.5 Flash</strong> · Servinformacion Demo Platform
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

