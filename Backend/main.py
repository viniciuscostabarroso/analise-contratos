import os
import uuid
import json
import re
from flask import Flask, request, jsonify, send_from_directory
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.cloud import storage

# --- Configuração ---
PROJECT_ID = "servi-pruebas-infra-brasil-dev"
LOCATION = "us-central1"
BUCKET_NAME = "demo-analise-contratos-data"
MODEL_NAME = "gemini-2.5-flash"

# Inicializa Vertex AI
vertexai.init(project=PROJECT_ID, location=LOCATION)

# Inicializa Flask — serve arquivos estáticos do React a partir de /app/static
app = Flask(__name__, static_folder="static", static_url_path="")

# =============================================
# PROMPT OTIMIZADO PARA ANÁLISE DE DOCUMENTOS
# =============================================
ANALYSIS_PROMPT = """Você é um especialista sênior em análise de contratos e documentos jurídicos e corporativos em língua portuguesa.

Analise o documento PDF fornecido com máxima atenção e retorne EXCLUSIVAMENTE um JSON válido com a seguinte estrutura, sem texto adicional, sem blocos de código markdown:

{
  "titulo_documento": "Título ou tipo do documento identificado",
  "numero_paginas_analisadas": 0,
  "resumo_executivo": "Resumo conciso em 3-5 frases dos pontos mais importantes do documento",
  "partes_envolvidas": [
    {"papel": "Contratante/Contratado/Parte A/etc", "nome": "Nome ou razão social", "documento": "CPF/CNPJ se disponível"}
  ],
  "objeto_contrato": "Descrição clara do objeto principal do contrato ou documento",
  "valor_contrato": "Valor total ou estimado, se presente. Caso contrário: 'Não especificado'",
  "pontos_principais": [
    {"topico": "Nome do tópico", "descricao": "Descrição objetiva e completa"}
  ],
  "clausulas_importantes": [
    {"numero_clausula": "Ex: Cláusula 5ª", "titulo": "Título da cláusula", "resumo": "Resumo do conteúdo em 1-2 frases"}
  ],
  "datas_e_prazos": [
    {"evento": "Descrição do evento ou marco", "data_prazo": "Data ou prazo identificado"}
  ],
  "obrigacoes_contratante": ["Lista das principais obrigações do contratante"],
  "obrigacoes_contratado": ["Lista das principais obrigações do contratado"],
  "alertas_e_riscos": [
    {"nivel": "alto", "categoria": "Financeiro/Jurídico/Operacional/Compliance", "descricao": "Descrição clara do risco ou ponto de atenção"},
    {"nivel": "medio", "categoria": "...", "descricao": "..."},
    {"nivel": "baixo", "categoria": "...", "descricao": "..."}
  ],
  "checklist_validacao": [
    {"item": "Identificação completa das partes", "status": "presente"},
    {"item": "Objeto do contrato definido", "status": "presente"},
    {"item": "Valor e forma de pagamento", "status": "presente"},
    {"item": "Prazo de vigência", "status": "ausente"},
    {"item": "Cláusula de rescisão", "status": "pendente"},
    {"item": "Foro de eleição", "status": "presente"},
    {"item": "Assinaturas e testemunhas", "status": "ausente"}
  ]
}

Regras importantes:
- Extraia SOMENTE informações presentes no documento. Não invente dados.
- Para campos não encontrados no documento, use "Não identificado" ou lista vazia [].
- O JSON deve ser perfeitamente válido e parseável.
- Retorne APENAS o JSON, sem nenhum texto antes ou depois.
"""

# =============================================
# ENDPOINTS
# =============================================

@app.route("/")
def serve_index():
    """Serve o index.html do React."""
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/health")
def health_check():
    """Health check para o Cloud Run."""
    return jsonify({"status": "ok", "service": "analise-contratos-demo"})

@app.route("/api/analyze", methods=["POST"])
def analyze_document():
    """Recebe um PDF, armazena no GCS e analisa com Gemini."""
    try:
        # Valida o arquivo
        if "file" not in request.files:
            return jsonify({"error": "Nenhum arquivo enviado. Use o campo 'file'."}), 400

        file = request.files["file"]

        if not file or file.filename == "":
            return jsonify({"error": "Arquivo inválido ou sem nome."}), 400

        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Apenas arquivos PDF são suportados."}), 400

        file_name = file.filename

        # --- Upload para o Cloud Storage ---
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob_name = f"uploads/{uuid.uuid4()}/{file_name}"
        blob = bucket.blob(blob_name)

        file.seek(0)
        blob.upload_from_file(file, content_type="application/pdf")
        gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"

        # --- Análise com Gemini 2.5 Flash via GCS URI ---
        model = GenerativeModel(MODEL_NAME)
        pdf_part = Part.from_uri(uri=gcs_uri, mime_type="application/pdf")

        response = model.generate_content(
            [pdf_part, ANALYSIS_PROMPT],
            generation_config={"temperature": 0.1, "max_output_tokens": 8192},
        )

        # --- Limpa e parseia o JSON retornado ---
        raw_text = response.text.strip()
        raw_text = re.sub(r"^```json\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

        analysis_data = json.loads(raw_text)

        return jsonify({
            "success": True,
            "file_name": file_name,
            "gcs_path": gcs_uri,
            "analysis": analysis_data,
        })

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Erro ao interpretar resposta do Gemini: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500

# Rota catch-all para o React Router (SPA)
@app.errorhandler(404)
def not_found(e):
    return send_from_directory(app.static_folder, "index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
