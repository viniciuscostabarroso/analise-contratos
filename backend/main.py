import os
import uuid
import json
import re
import time
import queue
import atexit
import signal
import logging
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

try:
    import vertexai
    from vertexai.generative_models import GenerativeModel, Part
except ImportError:
    vertexai = None
    GenerativeModel = None
    Part = None

try:
    from google.cloud import storage
except ImportError:
    storage = None


def _read_int_env(var_name, default_value):
    value = os.getenv(var_name, str(default_value))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_value


def _read_float_env(var_name, default_value):
    value = os.getenv(var_name, str(default_value))
    try:
        return float(value)
    except (TypeError, ValueError):
        return default_value


# --- Configuracao ---
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "servi-pruebas-infra-brasil-dev")
LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "demo-analise-contratos-data")
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
UPLOAD_PREFIX = os.getenv("GCS_UPLOAD_PREFIX", "uploads")
SERVICE_NAME = os.getenv("SERVICE_NAME", "analise-contratos-demo")
MAX_UPLOAD_SIZE_MB = _read_int_env("MAX_UPLOAD_SIZE_MB", 25)
JOB_RETENTION_SECONDS = _read_int_env("JOB_RETENTION_SECONDS", 3600)
MAX_STORED_JOBS = _read_int_env("MAX_STORED_JOBS", 300)
MAX_QUEUE_SIZE = max(1, _read_int_env("MAX_QUEUE_SIZE", 20))
WORKER_QUEUE_POLL_SECONDS = max(0.1, _read_float_env("WORKER_QUEUE_POLL_SECONDS", 0.5))
WORKER_SHUTDOWN_TIMEOUT_SECONDS = max(1.0, _read_float_env("WORKER_SHUTDOWN_TIMEOUT_SECONDS", 8.0))
QUEUE_RETRY_AFTER_SECONDS = max(1, _read_int_env("QUEUE_RETRY_AFTER_SECONDS", 10))

# Inicializa Flask - serve arquivos estaticos do React a partir de /app/static
app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE_MB * 1024 * 1024
app.logger.setLevel(logging.INFO)

_vertex_initialized = False
_model_instance = None
_model_lock = threading.Lock()
_storage_client = None
_storage_lock = threading.Lock()

# Fila e armazenamento em memoria para jobs assincronos
_analysis_queue = queue.Queue(maxsize=MAX_QUEUE_SIZE)
_jobs = {}
_jobs_lock = threading.Lock()
_worker_thread = None
_worker_lock = threading.Lock()
_worker_stop_event = threading.Event()


class JobQueueFullError(Exception):
    """Erro levantado quando a fila de processamento esta no limite."""

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


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_model():
    """Inicializa Vertex AI apenas quando necessario."""
    if vertexai is None or GenerativeModel is None:
        raise RuntimeError("Dependencias do Vertex AI nao estao instaladas.")

    global _vertex_initialized, _model_instance
    with _model_lock:
        if not _vertex_initialized:
            vertexai.init(project=PROJECT_ID, location=LOCATION)
            _vertex_initialized = True
        if _model_instance is None:
            _model_instance = GenerativeModel(MODEL_NAME)
    return _model_instance


def _get_storage_client():
    if storage is None:
        raise RuntimeError("Dependencias de Storage nao estao instaladas.")

    global _storage_client
    with _storage_lock:
        if _storage_client is None:
            _storage_client = storage.Client()
    return _storage_client


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


def _public_job_data(job):
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "stage": job["stage"],
        "progress": job["progress"],
        "file_name": job["file_name"],
        "gcs_path": job.get("gcs_path"),
        "error_type": job.get("error_type"),
        "error_message": job.get("error_message"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "updated_at": job.get("updated_at"),
    }


def _get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return deepcopy(job) if job else None


def _update_job(job_id, **updates):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        job.update(updates)
        job["updated_at"] = _utc_now_iso()
        return deepcopy(job)


def _cleanup_job_storage():
    """Remove jobs antigos e limita o tamanho do dicionario em memoria."""
    now_ts = time.time()
    with _jobs_lock:
        to_delete = []
        for job_id, job in _jobs.items():
            finished_at = job.get("finished_at")
            if not finished_at:
                continue
            try:
                finished_ts = datetime.fromisoformat(finished_at).timestamp()
            except ValueError:
                finished_ts = now_ts
            if now_ts - finished_ts > JOB_RETENTION_SECONDS:
                to_delete.append(job_id)

        for job_id in to_delete:
            _jobs.pop(job_id, None)

        if len(_jobs) <= MAX_STORED_JOBS:
            return

        ordered_jobs = sorted(
            _jobs.values(),
            key=lambda item: item.get("updated_at") or item.get("created_at") or "",
        )
        overflow = len(_jobs) - MAX_STORED_JOBS
        for job in ordered_jobs[:overflow]:
            _jobs.pop(job["job_id"], None)


def _create_job(file_name, safe_file_name, local_path):
    job_id = uuid.uuid4().hex
    now = _utc_now_iso()
    job_data = {
        "job_id": job_id,
        "file_name": file_name,
        "safe_file_name": safe_file_name,
        "local_path": local_path,
        "status": "queued",
        "stage": "queued",
        "progress": 5,
        "analysis": None,
        "gcs_path": None,
        "error_type": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
    }

    _cleanup_job_storage()
    with _jobs_lock:
        _jobs[job_id] = job_data
    return deepcopy(job_data)


def _stage_progress(stage):
    mapping = {
        "queued": 5,
        "uploading": 25,
        "analyzing": 65,
        "parsing": 85,
        "completed": 100,
        "failed": 100,
    }
    return mapping.get(stage, 5)


def _set_job_stage(job_id, stage):
    _update_job(job_id, stage=stage, progress=_stage_progress(stage))


def _build_blob_name(safe_file_name):
    prefix = UPLOAD_PREFIX.strip("/") or "uploads"
    return f"{prefix}/{uuid.uuid4()}/{safe_file_name}"


def _classify_error(message):
    lowered = (message or "").lower()
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "dependencias" in lowered:
        return "dependency_error"
    if "nao foi encontrado" in lowered:
        return "not_found"
    if "fila" in lowered and "cheia" in lowered:
        return "queue_full"
    return "processing_error"


def _process_analysis_job(job_id):
    job = _get_job(job_id)
    if not job:
        return

    local_path = job.get("local_path")
    safe_file_name = job.get("safe_file_name")

    try:
        _update_job(job_id, status="processing", started_at=_utc_now_iso(), error_type=None, error_message=None)

        if Part is None:
            raise RuntimeError("Dependencias de IA/Storage nao estao instaladas.")

        _set_job_stage(job_id, "uploading")
        storage_client = _get_storage_client()
        bucket = storage_client.bucket(BUCKET_NAME)
        blob_name = _build_blob_name(safe_file_name)
        blob = bucket.blob(blob_name)

        with open(local_path, "rb") as temp_pdf:
            blob.upload_from_file(temp_pdf, content_type="application/pdf")

        gcs_uri = f"gs://{BUCKET_NAME}/{blob_name}"
        _update_job(job_id, gcs_path=gcs_uri)

        _set_job_stage(job_id, "analyzing")
        model = _get_model()
        pdf_part = Part.from_uri(uri=gcs_uri, mime_type="application/pdf")

        response = model.generate_content(
            [pdf_part, ANALYSIS_PROMPT],
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 8192,
                "response_mime_type": "application/json",
            },
        )

        _set_job_stage(job_id, "parsing")
        raw_text = (response.text or "").strip()
        analysis_data = _extract_json_from_model_response(raw_text)

        _update_job(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            analysis=analysis_data,
            finished_at=_utc_now_iso(),
        )
    except json.JSONDecodeError as exc:
        app.logger.exception("Falha ao parsear resposta JSON do Gemini")
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            error_type="parse_error",
            error_message=f"Erro ao interpretar resposta do Gemini: {str(exc)}",
            finished_at=_utc_now_iso(),
        )
    except Exception as exc:
        app.logger.exception("Erro no processamento assincrono do job %s", job_id)
        message = str(exc)
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            error_type=_classify_error(message),
            error_message=message,
            finished_at=_utc_now_iso(),
        )
    finally:
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError:
                app.logger.warning("Nao foi possivel remover arquivo temporario: %s", local_path)
        _update_job(job_id, local_path=None)


def _analysis_worker_loop():
    app.logger.info("Worker de analise iniciado")
    while not _worker_stop_event.is_set():
        try:
            job_id = _analysis_queue.get(timeout=WORKER_QUEUE_POLL_SECONDS)
        except queue.Empty:
            continue

        if job_id is None:
            _analysis_queue.task_done()
            break

        try:
            _process_analysis_job(job_id)
        finally:
            _analysis_queue.task_done()

    app.logger.info("Worker de analise finalizado")


def _start_worker():
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive():
            return

        _worker_stop_event.clear()
        _worker_thread = threading.Thread(
            target=_analysis_worker_loop,
            name="analysis-worker",
            daemon=True,
        )
        _worker_thread.start()


def _stop_worker():
    global _worker_thread
    with _worker_lock:
        thread = _worker_thread
        if not thread:
            return

        _worker_stop_event.set()
        try:
            _analysis_queue.put_nowait(None)
        except queue.Full:
            # O worker encerra no proximo ciclo ao detectar o stop_event.
            pass

    if thread.is_alive():
        thread.join(timeout=WORKER_SHUTDOWN_TIMEOUT_SECONDS)

    with _worker_lock:
        if _worker_thread is thread:
            _worker_thread = None


def _register_signal_handlers():
    def _handle_shutdown(_signum, _frame):
        app.logger.info("Sinal de encerramento recebido. Finalizando worker.")
        _stop_worker()

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle_shutdown)
        except (ValueError, OSError):
            # Evita erro quando nao estamos no thread principal.
            pass


@atexit.register
def _shutdown_background_worker():
    _stop_worker()


def _enqueue_analysis_job(file_obj):
    file_name = file_obj.filename
    safe_file_name = secure_filename(file_name) or f"documento_{uuid.uuid4().hex}.pdf"

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_file_path = temp_file.name
    try:
        file_obj.stream.seek(0)
        file_obj.save(temp_file.name)
    finally:
        temp_file.close()

    job = _create_job(file_name=file_name, safe_file_name=safe_file_name, local_path=temp_file_path)
    try:
        _analysis_queue.put_nowait(job["job_id"])
    except queue.Full as exc:
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                app.logger.warning("Nao foi possivel remover arquivo temporario rejeitado: %s", temp_file_path)
        with _jobs_lock:
            _jobs.pop(job["job_id"], None)
        raise JobQueueFullError("Fila de processamento cheia.") from exc

    return job


def _queue_snapshot():
    with _jobs_lock:
        active_jobs = sum(1 for job in _jobs.values() if job.get("status") in ("queued", "processing"))
    return {
        "current_size": _analysis_queue.qsize(),
        "max_size": MAX_QUEUE_SIZE,
        "active_jobs": active_jobs,
    }


_register_signal_handlers()
_start_worker()

# =============================================
# ENDPOINTS
# =============================================

@app.route("/api/health")
def health_check():
    """Health check para o Cloud Run."""
    queue_info = _queue_snapshot()
    worker_alive = _worker_thread.is_alive() if _worker_thread else False
    return jsonify(
        {
            "status": "ok",
            "service": SERVICE_NAME,
            "worker_alive": worker_alive,
            "queue": queue_info,
            "limits": {
                "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
                "job_retention_seconds": JOB_RETENTION_SECONDS,
            },
        }
    )


@app.route("/api/analyze", methods=["POST"])
def analyze_document_async():
    """Recebe um PDF e enfileira para processamento assincrono."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "Nenhum arquivo enviado. Use o campo 'file'.", "error_type": "invalid_file"}), 400

        file = request.files["file"]

        if not file or file.filename == "":
            return jsonify({"error": "Arquivo invalido ou sem nome.", "error_type": "invalid_file"}), 400

        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Apenas arquivos PDF sao suportados.", "error_type": "invalid_file"}), 400

        job = _enqueue_analysis_job(file)
        response_payload = {
            "success": True,
            "message": "Arquivo recebido e enfileirado para analise.",
            "job": _public_job_data(job),
            "status_url": f"/api/analyze/{job['job_id']}/status",
            "result_url": f"/api/analyze/{job['job_id']}/result",
        }
        return jsonify(response_payload), 202
    except JobQueueFullError as exc:
        app.logger.warning("Fila cheia ao tentar enfileirar novo job.")
        response = jsonify(
            {
                "error": str(exc),
                "error_type": "queue_full",
                "retry_after_seconds": QUEUE_RETRY_AFTER_SECONDS,
            }
        )
        response.headers["Retry-After"] = str(QUEUE_RETRY_AFTER_SECONDS)
        return response, 429
    except Exception as exc:
        app.logger.exception("Erro interno no endpoint /api/analyze")
        return jsonify({"error": f"Erro interno: {str(exc)}", "error_type": "server_error"}), 500


@app.route("/api/analyze/<job_id>/status", methods=["GET"])
def analyze_status(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Job nao encontrado.", "error_type": "not_found"}), 404

    payload = {
        "success": True,
        "job": _public_job_data(job),
        "result_ready": job["status"] == "completed",
    }

    if job["status"] == "queued" or job["status"] == "processing":
        return jsonify(payload), 202

    if job["status"] == "failed":
        return jsonify(payload), 200

    return jsonify(payload), 200


@app.route("/api/analyze/<job_id>/result", methods=["GET"])
def analyze_result(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify({"error": "Job nao encontrado.", "error_type": "not_found"}), 404

    if job["status"] == "completed":
        return jsonify(
            {
                "success": True,
                "file_name": job["file_name"],
                "gcs_path": job.get("gcs_path"),
                "analysis": job.get("analysis"),
                "job": _public_job_data(job),
            }
        )

    if job["status"] == "failed":
        return (
            jsonify(
                {
                    "success": False,
                    "error": job.get("error_message") or "Falha no processamento.",
                    "error_type": job.get("error_type") or "processing_error",
                    "job": _public_job_data(job),
                }
            ),
            500,
        )

    return (
        jsonify(
            {
                "success": False,
                "message": "Analise ainda em processamento.",
                "job": _public_job_data(job),
            }
        ),
        202,
    )


@app.errorhandler(413)
def payload_too_large(_):
    return jsonify({"error": f"Arquivo muito grande. Limite de {MAX_UPLOAD_SIZE_MB}MB.", "error_type": "file_too_large"}), 413


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    """Serve arquivos estaticos e fallback para o React Router."""
    if path.startswith("api/"):
        return jsonify({"error": "Endpoint nao encontrado.", "error_type": "not_found"}), 404

    static_file = os.path.join(app.static_folder, path)
    if path and os.path.exists(static_file):
        return send_from_directory(app.static_folder, path)

    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

