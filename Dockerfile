# =============================================
# STAGE 1: Build do Frontend React
# =============================================
FROM node:18-alpine AS frontend-builder
WORKDIR /app/Frontend

# Copia dependências e instala
COPY Frontend/package.json ./
RUN npm install

# Copia o código e gera o build de produção
COPY Frontend/ .
RUN npm run build

# =============================================
# STAGE 2: Backend Python (Flask + Gunicorn)
# =============================================
FROM python:3.11-slim
WORKDIR /app

# Instala dependências Python
COPY Backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código do backend
COPY Backend/ .

# Copia o build do React para a pasta static
COPY --from=frontend-builder /app/Frontend/build ./static

# Expõe a porta
EXPOSE 8080

# Inicia com Gunicorn (compatível com WSGI)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "600", "main:app"]
