FROM node:24-bookworm-slim AS frontend
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Kathmandu PYTHONPATH=/app
WORKDIR /app
COPY pyproject.toml README.md ./
COPY nepse_trader/ ./nepse_trader/
RUN pip install --no-cache-dir .
COPY config/ ./config/
COPY --from=frontend /build/web/dist ./web/dist
RUN groupadd --system nepse && useradd --system --gid nepse nepse \
    && mkdir -p /app/data /app/logs && chown -R nepse:nepse /app
USER nepse
EXPOSE 8000
VOLUME ["/app/data", "/app/logs"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["python", "-m", "uvicorn", "nepse_trader.web.api:app", "--host", "0.0.0.0", "--port", "8000"]
