import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend import main


@pytest.fixture(autouse=True)
def clear_jobs_state():
    with main._jobs_lock:
        main._jobs.clear()


def _create_sample_job(status="queued"):
    job = main._create_job("contrato.pdf", "contrato.pdf", None)
    main._update_job(job["job_id"], status=status, stage=status, progress=100 if status in ("completed", "failed") else 5)
    return main._get_job(job["job_id"])


def test_extract_json_from_plain_payload():
    parsed = main._extract_json_from_model_response('{"ok": true, "value": 10}')
    assert parsed == {"ok": True, "value": 10}


def test_extract_json_from_markdown_payload():
    payload = """```json
{"titulo": "Contrato"}
```"""
    parsed = main._extract_json_from_model_response(payload)
    assert parsed == {"titulo": "Contrato"}


def test_extract_json_from_text_with_wrapper():
    payload = "Resposta:\n{\"status\": \"ok\"}\nFim."
    parsed = main._extract_json_from_model_response(payload)
    assert parsed == {"status": "ok"}


def test_health_check_endpoint():
    client = main.app.test_client()
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "service" in data
    assert "queue" in data
    assert "current_size" in data["queue"]
    assert "max_size" in data["queue"]


def test_analyze_requires_file():
    client = main.app.test_client()
    response = client.post("/api/analyze", data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    data = response.get_json()
    assert data["error_type"] == "invalid_file"
    assert "Nenhum arquivo enviado" in data["error"]


def test_analyze_rejects_non_pdf():
    client = main.app.test_client()
    response = client.post(
        "/api/analyze",
        data={"file": (io.BytesIO(b"abc"), "arquivo.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    data = response.get_json()
    assert data["error_type"] == "invalid_file"
    assert "Apenas arquivos PDF" in data["error"]


def test_analyze_enqueue_success(monkeypatch):
    client = main.app.test_client()

    fake_job = {
        "job_id": "job-123",
        "status": "queued",
        "stage": "queued",
        "progress": 5,
        "file_name": "contrato.pdf",
        "gcs_path": None,
        "error_type": None,
        "error_message": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "started_at": None,
        "finished_at": None,
    }

    monkeypatch.setattr(main, "_enqueue_analysis_job", lambda _f: fake_job)

    response = client.post(
        "/api/analyze",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "contrato.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    data = response.get_json()
    assert data["success"] is True
    assert data["job"]["job_id"] == "job-123"
    assert data["status_url"].endswith("/api/analyze/job-123/status")
    assert data["result_url"].endswith("/api/analyze/job-123/result")


def test_analyze_queue_full_returns_429(monkeypatch):
    client = main.app.test_client()

    def _raise_queue_full(_file):
        raise main.JobQueueFullError("Fila de processamento cheia.")

    monkeypatch.setattr(main, "_enqueue_analysis_job", _raise_queue_full)

    response = client.post(
        "/api/analyze",
        data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "contrato.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 429
    assert response.headers.get("Retry-After") == str(main.QUEUE_RETRY_AFTER_SECONDS)
    data = response.get_json()
    assert data["error_type"] == "queue_full"


def test_status_endpoint_pending_returns_202():
    client = main.app.test_client()
    job = _create_sample_job(status="processing")

    response = client.get(f"/api/analyze/{job['job_id']}/status")

    assert response.status_code == 202
    data = response.get_json()
    assert data["result_ready"] is False
    assert data["job"]["status"] == "processing"


def test_result_endpoint_completed_returns_payload():
    client = main.app.test_client()
    job = _create_sample_job(status="completed")
    main._update_job(
        job["job_id"],
        analysis={"titulo_documento": "Contrato Teste"},
        gcs_path="gs://bucket/teste.pdf",
    )

    response = client.get(f"/api/analyze/{job['job_id']}/result")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["analysis"]["titulo_documento"] == "Contrato Teste"


def test_result_endpoint_failed_returns_error():
    client = main.app.test_client()
    job = _create_sample_job(status="failed")
    main._update_job(job["job_id"], error_type="timeout", error_message="Tempo excedido")

    response = client.get(f"/api/analyze/{job['job_id']}/result")

    assert response.status_code == 500
    data = response.get_json()
    assert data["success"] is False
    assert data["error_type"] == "timeout"


def test_process_analysis_job_success_with_mocks(monkeypatch):
    class FakeBlob:
        def __init__(self):
            self.uploaded = False
            self.content_type = None
            self.payload = b""

        def upload_from_file(self, file_obj, content_type=None):
            self.uploaded = True
            self.content_type = content_type
            self.payload = file_obj.read()

    class FakeBucket:
        def __init__(self):
            self.blob_created = FakeBlob()

        def blob(self, _name):
            return self.blob_created

    class FakeStorageClient:
        def __init__(self):
            self.bucket_instance = FakeBucket()

        def bucket(self, _bucket_name):
            return self.bucket_instance

    class FakeModel:
        def generate_content(self, _prompt_parts, generation_config=None):
            assert generation_config["max_output_tokens"] == 8192
            return SimpleNamespace(
                text='{"titulo_documento":"Contrato Teste","resumo_executivo":"ok","numero_paginas_analisadas":1}'
            )

    temp_pdf = Path(ROOT_DIR / "backend" / "tests" / "temp_test.pdf")
    temp_pdf.write_bytes(b"%PDF-1.4 fake")

    job = main._create_job("contrato.pdf", "contrato.pdf", str(temp_pdf))

    fake_client = FakeStorageClient()
    if main.storage is None:
        monkeypatch.setattr(main, "storage", SimpleNamespace(Client=lambda: fake_client), raising=False)
    else:
        monkeypatch.setattr(main.storage, "Client", lambda: fake_client)

    if main.Part is None:
        monkeypatch.setattr(
            main,
            "Part",
            SimpleNamespace(from_uri=lambda uri, mime_type: {"uri": uri, "mime_type": mime_type}),
            raising=False,
        )
    else:
        monkeypatch.setattr(main.Part, "from_uri", staticmethod(lambda uri, mime_type: {"uri": uri, "mime_type": mime_type}))

    monkeypatch.setattr(main, "_get_model", lambda: FakeModel())

    main._process_analysis_job(job["job_id"])

    processed_job = main._get_job(job["job_id"])
    assert processed_job["status"] == "completed"
    assert processed_job["analysis"]["titulo_documento"] == "Contrato Teste"

    uploaded_blob = fake_client.bucket_instance.blob_created
    assert uploaded_blob.uploaded is True
    assert uploaded_blob.content_type == "application/pdf"

