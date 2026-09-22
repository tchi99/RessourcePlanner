from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .github import GitHubClient, GitHubError
from .service import build_dashboard

PROJECT_DIR = Path(__file__).resolve().parents[2]


def create_app(app_settings: Settings | None = None) -> FastAPI:
    settings = app_settings or Settings.from_env()
    app = FastAPI(title="RessourcePlanner Dev Cockpit", version="0.2.0")

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
