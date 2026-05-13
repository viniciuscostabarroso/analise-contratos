# =============================================
# STAGE 1: Build do Frontend React
# =============================================
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend

# Copia dependencias e instala
COPY frontend/package.json ./
RUN npm install

# Copia o codigo e gera o build de producao
COPY frontend/ .
RUN npm run build

# =============================================
# STAGE 2: Backend Python (Flask + Gunicorn)
# =============================================
FROM python:3.11-slim
WORKDIR /app

# Instala dependencias Python
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o codigo do backend
COPY backend/ .

# Copia o build do React para a pasta static
COPY --from=frontend-builder /app/frontend/build ./static

# Expoe a porta
EXPOSE 8080
ENV PORT=8080

# Inicia com Gunicorn (compativel com WSGI)
CMD exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --timeout 600 main:app

