import os
import uuid
import json
import re
import logging

from flask import Flask, request, jsonify, send_from_directory
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.cloud import storage
from werkzeug.utils import secure_filename

def _read_int_env(var_name, default_value):
    value = os.getenv(var_name, str(default_value))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_value


# --- Configuracao ---
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "servi-pruebas-infra-brasil-dev")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "demo-analise-contratos-data")
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
UPLOAD_PREFIX = os.getenv("GCS_UPLOAD_PREFIX", "uploads")
MAX_UPLOAD_SIZE_MB = _read_int_env("MAX_UPLOAD_SIZE_MB", 25)

# Inicializa Flask - serve arquivos estaticos do React a partir de /app/static
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE_MB * 1024 * 1024
app.logger.setLevel(logging.INFO)

_vertex_initialized = False

# =============================================
# PROMPT OTIMIZADO PARA ANALISE DE DOCUMENTOS
# =============================================
ANALYSIS_PROMPT = """Voce e um especialista senior em analise de contratos e documentos juridicos e corporativos em lingua portuguesa.

Analise o documento PDF fornecido com maxima atencao e retorne EXCLUSIVAMENTE um JSON valido com a seguinte estrutura, sem texto adicional, sem blocos de codigo markdown:

{
  "titulo_documento": "Titulo ou tipo do documento identificado",
  "numero_paginas_analisadas": 0,
  "resumo_executivo": "Resumo conciso em 3-5 frases dos pontos mais importantes do documento",
  "partes_envolvidas": [
    {"papel": "Contratante/Contratado/Parte A/etc", "nome": "Nome ou razao social", "documento": "CPF/CNPJ se disponivel"}
  ],
  "objeto_contrato": "Descricao clara do objeto principal do contrato ou documento",
  "valor_contrato": "Valor total ou estimado, se presente. Caso contrario: 'Nao especificado'",
  "pontos_principais": [
    {"topico": "Nome do topico", "descricao": "Descricao objetiva e completa"}
  ],
  "clausulas_importantes": [
    {"numero_clausula": "Ex: Clausula 5a", "titulo": "Titulo da clausula", "resumo": "Resumo do conteudo em 1-2 frases"}
  ],
  "datas_e_prazos": [
    {"evento": "Descricao do evento ou marco", "data_prazo": "Data ou prazo identificado"}
  ],
  "obrigacoes_contratante": ["Lista das principais obrigacoes do contratante"],
  "obrigacoes_contratado": ["Lista das principais obrigacoes do contratado"],
  "alertas_e_riscos": [
    {"nivel": "alto", "categoria": "Financeiro/Juridico/Operacional/Compliance", "descricao": "Descricao clara do risco ou ponto de atencao"},
    {"nivel": "medio", "categoria": "...", "descricao": "..."},
    {"nivel": "baixo", "categoria": "...", "descricao": "..."}
  ],
  "checklist_validacao": [
    {"item": "Identificacao completa das partes", "status": "presente"},
    {"item": "Objeto do contrato definido", "status": "presente"},
    {"item": "Valor e forma de pagamento", "status": "presente"},
    {"item": "Prazo de vigencia", "status": "ausente"},
    {"item": "Clausula de rescisao", "status": "pendente"},
    {"item": "Foro de eleicao", "status": "presente"},
    {"item": "Assinaturas e testemunhas", "status": "ausente"}
  ]
}

Regras importantes:
- Extraia SOMENTE informacoes presentes no documento. Nao invente dados.
- Para campos nao encontrados no documento, use "Nao identificado" ou lista vazia [].
- O JSON deve ser perfeitamente valido e parseavel.
- Retorne APENAS o JSON, sem nenhum texto antes ou depois.
"""


def _get_model():
    """Inicializa Vertex AI apenas quando necessario."""
    global _vertex_initialized
    if not _vertex_initialized:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        _vertex_initialized = True
    return GenerativeModel(MODEL_NAME)


def _extract_json_from_model_response(raw_text):
    """Extrai um JSON mesmo quando o modelo envolve a resposta em markdown."""
    if not raw_text:
        raise json.JSONDecodeError("Resposta vazia do modelo", "", 0)

    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


# =============================================
# ENDPOINTS
# =============================================

@app.route("/api/health")
def health_check():
    """Health check para o Cloud Run."""
    return jsonify({"status": "ok", "service": "analise-contratos-demo"})


@app.route("/api/analyze", methods=["POST"])
def analyze_document():
    """Recebe um PDF, armazena no GCS e analisa com Gemini."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "Nenhum arquivo enviado. Use o campo 'file'."}), 400

        file = request.files["file"]

        if not file or file.filename == "":
            return jsonify({"error": "Arquivo invalido ou sem nome."}), 400

        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Apenas arquivos PDF sao suportados."}), 400

        file_name = file.filename
        safe_file_name = secure_filename(file_name) or f"documento_{uuid.uuid4().hex}.pdf"

        # --- Upload para o Cloud Storage ---
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        prefix = UPLOAD_PREFIX.strip("/") or "uploads"
        blob_name = f"{prefix}/{uuid.uuid4()}/{safe_file_name}"
        blob = bucket.blob(blob_name)

        file.seek(0)
        blob.upload_from_file(file, content_type="application/pdf")
        gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"

        # --- Analise com Gemini 2.5 Flash via GCS URI ---
        model = _get_model()
        pdf_part = Part.from_uri(uri=gcs_uri, mime_type="application/pdf")

        response = model.generate_content(
            [pdf_part, ANALYSIS_PROMPT],
            generation_config={"temperature": 0.1, "max_output_tokens": 8192},
        )

        raw_text = (response.text or "").strip()
        analysis_data = _extract_json_from_model_response(raw_text)

        return jsonify(
            {
                "success": True,
                "file_name": file_name,
                "gcs_path": gcs_uri,
                "analysis": analysis_data,
            }
        )

    except json.JSONDecodeError as exc:
        app.logger.exception("Falha ao parsear resposta JSON do Gemini")
        return jsonify({"error": f"Erro ao interpretar resposta do Gemini: {str(exc)}"}), 500
    except Exception as exc:
        app.logger.exception("Erro interno no endpoint /api/analyze")
        return jsonify({"error": f"Erro interno: {str(exc)}"}), 500


@app.errorhandler(413)
def payload_too_large(_):
    return jsonify({"error": f"Arquivo muito grande. Limite de {MAX_UPLOAD_SIZE_MB}MB."}), 413


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    """Serve arquivos estaticos e fallback para o React Router."""
    if path.startswith("api/"):
        return jsonify({"error": "Endpoint nao encontrado."}), 404

    static_file = os.path.join(app.static_folder, path)
    if path and os.path.exists(static_file):
        return send_from_directory(app.static_folder, path)

    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
