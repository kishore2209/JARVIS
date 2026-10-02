FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /build/frontend/dist ./frontend/dist

RUN useradd --create-home --uid 10001 jarvis \
    && mkdir -p /var/data /app/data \
    && chown jarvis:jarvis /var/data /app/data
USER jarvis
EXPOSE 10000
CMD ["python", "-m", "jarvis_cloud"]
