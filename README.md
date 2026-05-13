# analise-contratos

Aplicacao full-stack para analise de contratos em PDF com React no frontend e Flask + Vertex AI no backend.

## Arquitetura

- Frontend: React compilado para arquivos estaticos.
- Backend: Flask servido por Gunicorn.
- Processamento: upload assincrono com fila em memoria (worker thread no mesmo container).
- IA: Vertex AI Gemini.
- Armazenamento temporario de arquivos: Cloud Storage.

## Variaveis de ambiente

Obrigatorias:

- `VERTEX_PROJECT_ID`: projeto GCP para Vertex AI.
- `VERTEX_LOCATION`: regiao do Vertex (ex: `us-central1`).
- `GCS_BUCKET_NAME`: bucket para upload temporario dos PDFs.

Opcionais (com defaults no codigo):

- `GEMINI_MODEL_NAME` (default: `gemini-2.5-flash`)
- `GCS_UPLOAD_PREFIX` (default: `uploads`)
- `MAX_UPLOAD_SIZE_MB` (default: `25`)
- `MAX_QUEUE_SIZE` (default: `20`)
- `MAX_STORED_JOBS` (default: `300`)
- `JOB_RETENTION_SECONDS` (default: `3600`)

Referencia pronta para deploy: `cloudrun.env.example`.

## Build local da imagem

```bash
docker build -t analise-contratos:local .
```

## Rodar local com Docker

```bash
docker run --rm -p 8080:8080 \
  -e VERTEX_PROJECT_ID=<seu-projeto> \
  -e VERTEX_LOCATION=us-central1 \
  -e GCS_BUCKET_NAME=<seu-bucket> \
  analise-contratos:local
```

Health check:

```bash
curl http://localhost:8080/api/health
```

## Deploy recomendado no Cloud Run (imagem)

### 1) Build e push da imagem com Cloud Build

```bash
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/<PROJECT_ID>/<REPO>/analise-contratos:latest
```

### 2) Deploy do servico

```bash
gcloud run deploy analise-contratos \
  --image us-central1-docker.pkg.dev/<PROJECT_ID>/<REPO>/analise-contratos:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --cpu 2 \
  --memory 2Gi \
  --concurrency 20 \
  --min-instances 1 \
  --max-instances 1 \
  --no-cpu-throttling \
  --timeout 3600 \
  --set-env-vars VERTEX_PROJECT_ID=<PROJECT_ID>,VERTEX_LOCATION=us-central1,GCS_BUCKET_NAME=<BUCKET_NAME>,GEMINI_MODEL_NAME=gemini-2.5-flash,MAX_UPLOAD_SIZE_MB=25,MAX_QUEUE_SIZE=20
```

## Observacao importante sobre escalabilidade

Hoje os status de job ficam em memoria no container.
Por isso, para comportamento previsivel no Cloud Run, mantenha `--max-instances=1`.

Se quiser escalar horizontalmente (mais de 1 instancia), o proximo passo e mover estado/fila para um backend externo (ex: Firestore + Pub/Sub + Cloud Run Jobs/Workers).
