import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

function selectPdfFile() {
  const input = document.querySelector('input[type="file"]');
  const file = new File(["%PDF-1.4 test"], "contrato.pdf", { type: "application/pdf" });
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

function buildResultResponse() {
  return {
    success: true,
    file_name: "contrato.pdf",
    analysis: {
      titulo_documento: "Contrato Exemplo",
      numero_paginas_analisadas: 12,
      resumo_executivo: "Resumo de teste.",
      partes_envolvidas: [{ papel: "Contratante", nome: "Empresa A", documento: "00.000.000/0001-00" }],
      objeto_contrato: "Prestacao de servicos",
      valor_contrato: "R$ 10.000,00",
      pontos_principais: [{ topico: "Objeto", descricao: "Descricao do objeto." }],
      clausulas_importantes: [{ numero_clausula: "Clausula 1", titulo: "Vigencia", resumo: "Resumo da vigencia." }],
      datas_e_prazos: [{ evento: "Inicio", data_prazo: "2026-01-01" }],
      obrigacoes_contratante: ["Pagar o valor acordado."],
      obrigacoes_contratado: ["Executar os servicos."],
      alertas_e_riscos: [{ nivel: "alto", categoria: "Juridico", descricao: "Risco de multa." }],
      checklist_validacao: [{ item: "Partes identificadas", status: "presente" }],
    },
    job: {
      job_id: "job-123",
      status: "completed",
      stage: "completed",
      progress: 100,
      file_name: "contrato.pdf",
    },
  };
}

describe("App", () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  it("renderiza a tela inicial de upload", () => {
    render(<App />);

    expect(screen.getByText(/analise inteligente de documentos/i)).toBeInTheDocument();
    expect(screen.getByText(/arraste e solte um arquivo pdf aqui/i)).toBeInTheDocument();
  });

  it("enfileira e processa a analise assincrona com polling", async () => {
    const resultPayload = buildResultResponse();

    global.fetch = jest.fn(async (url) => {
      if (url === "/api/analyze") {
        return {
          ok: true,
          status: 202,
          text: async () =>
            JSON.stringify({
              success: true,
              job: {
                job_id: "job-123",
                status: "queued",
                stage: "queued",
                progress: 5,
                file_name: "contrato.pdf",
              },
            }),
        };
      }

      if (url === "/api/analyze/job-123/status") {
        return {
          ok: true,
          status: 200,
          text: async () =>
            JSON.stringify({
              success: true,
              result_ready: true,
              job: {
                job_id: "job-123",
                status: "completed",
                stage: "completed",
                progress: 100,
                file_name: "contrato.pdf",
              },
            }),
        };
      }

      if (url === "/api/analyze/job-123/result") {
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify(resultPayload),
        };
      }

      throw new Error(`URL nao esperada no teste: ${url}`);
    });

    render(<App />);
    selectPdfFile();

    fireEvent.click(screen.getByRole("button", { name: /iniciar analise assincrona/i }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/analyze",
        expect.objectContaining({
          method: "POST",
          body: expect.any(FormData),
        })
      );
    });

    expect(await screen.findByText("Contrato Exemplo")).toBeInTheDocument();
    expect(screen.getByText(/resumo de teste/i)).toBeInTheDocument();
  });

  it("mostra erro tipado quando a API retorna arquivo invalido", async () => {
    global.fetch = jest.fn(async () => ({
      ok: false,
      status: 400,
      text: async () => JSON.stringify({ error_type: "invalid_file", error: "Apenas PDF e suportado." }),
    }));

    render(<App />);
    selectPdfFile();

    fireEvent.click(screen.getByRole("button", { name: /iniciar analise assincrona/i }));

    expect(await screen.findByText(/arquivo invalido/i)).toBeInTheDocument();
    expect(screen.getByText(/apenas pdf e suportado/i)).toBeInTheDocument();
  });

  it("mostra erro de API indisponivel quando fetch falha", async () => {
    global.fetch = jest.fn(async () => {
      throw new TypeError("Failed to fetch");
    });

    render(<App />);
    selectPdfFile();

    fireEvent.click(screen.getByRole("button", { name: /iniciar analise assincrona/i }));

    expect(await screen.findByText(/api indisponivel/i)).toBeInTheDocument();
  });
});
