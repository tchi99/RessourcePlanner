FROM node:22-alpine AS frontend-build

WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/backend

RUN groupadd --gid 10002 devcockpit \
    && useradd --create-home --uid 10002 --gid devcockpit devcockpit

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN python -m pip install --no-cache-dir -r backend/requirements.txt

COPY --chown=devcockpit:devcockpit backend/app ./backend/app
COPY --from=frontend-build --chown=devcockpit:devcockpit /src/frontend/dist ./frontend/dist

USER devcockpit

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "from urllib.request import urlopen; r=urlopen('http://127.0.0.1:8000/api/health', timeout=3); raise SystemExit(0 if r.status == 200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
