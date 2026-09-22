from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .chat_status import ChatHeartbeat, ChatStatusStore
from .config import Settings
from .github import GitHubClient, GitHubError
from .roles import RoleStore, RolesConfig
from .service import build_dashboard

PROJECT_DIR = Path(__file__).resolve().parents[2]


def create_app(app_settings: Settings | None = None) -> FastAPI:
    settings = app_settings or Settings.from_env()
    app = FastAPI(title="RessourcePlanner Dev Cockpit", version="0.4.0")
    role_store = RoleStore(settings.data_dir)
    chat_status_store = ChatStatusStore()

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok" if settings.github_token else "configuration_error",
            "token_configured": bool(settings.github_token),
        }

    @app.get("/api/config")
    async def config() -> dict[str, object]:
        return {
            "repository": settings.repository,
            "roadmap_issue": settings.roadmap_issue,
            "stalled_after_minutes": settings.stalled_after_minutes,
            "token_configured": bool(settings.github_token),
        }

    @app.get("/api/roles", response_model=RolesConfig)
    async def get_roles() -> RolesConfig:
        try:
            return role_store.load()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.put("/api/roles", response_model=RolesConfig)
    async def put_roles(payload: RolesConfig) -> RolesConfig:
        try:
            return role_store.save(payload)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Impossible d'enregistrer la configuration locale des rôles.",
            ) from exc

    @app.post("/api/chat-status/heartbeat")
    async def chat_status_heartbeat(payload: ChatHeartbeat) -> dict[str, object]:
        return chat_status_store.heartbeat(payload)

    @app.get("/api/chat-status")
    async def chat_status() -> dict[str, object]:
        return chat_status_store.snapshot()

    @app.get("/api/dashboard")
    async def dashboard(repo: str | None = Query(default=None)) -> dict:
        if not settings.github_token:
            raise HTTPException(
                status_code=503,
                detail=(
                    "DEV_COCKPIT_GITHUB_TOKEN n'est pas configuré. "
                    "Ajoute un token GitHub en lecture seule dans le .env racine puis redémarre le service dev-cockpit."
                ),
            )
        target_repo = repo or settings.repository
        try:
            async with GitHubClient(settings) as client:
                return await build_dashboard(client, settings, target_repo)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except GitHubError as exc:
            status = 502 if exc.status_code >= 500 else exc.status_code
            raise HTTPException(status_code=status, detail=f"GitHub: {exc.message}") from exc

    dist_dir = PROJECT_DIR / "frontend" / "dist"
    if dist_dir.exists():
        assets = dist_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            candidate = dist_dir / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist_dir / "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
