from __future__ import annotations

import base64
import re
from typing import Any

import httpx

from .config import Settings

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class GitHubClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ressourceplanner-dev-cockpit",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self._client = httpx.AsyncClient(
            base_url=settings.github_api_url,
            headers=headers,
            timeout=20.0,
            transport=transport,
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def validate_repo(repo: str) -> str:
        value = repo.strip()
        if not REPO_RE.fullmatch(value):
            raise ValueError("Le dépôt doit être au format owner/repo.")
        return value

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = await self._client.get(path, params=params)
        if response.is_error:
            message = "Erreur GitHub"
            try:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("message"):
                    message = str(payload["message"])
            except ValueError:
                pass
            raise GitHubError(response.status_code, message)
        return response.json()

    async def get_issue(self, repo: str, number: int) -> dict[str, Any]:
        return await self._get(f"/repos/{repo}/issues/{number}")

    async def list_pulls(self, repo: str, state: str = "open", per_page: int = 20) -> list[dict[str, Any]]:
        return await self._get(
            f"/repos/{repo}/pulls",
            {"state": state, "sort": "updated", "direction": "desc", "per_page": per_page},
        )

    async def get_pull(self, repo: str, number: int) -> dict[str, Any]:
        return await self._get(f"/repos/{repo}/pulls/{number}")

    async def list_pull_files(
        self,
        repo: str,
        number: int,
        *,
        per_page: int = 100,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            batch = await self._get(
                f"/repos/{repo}/pulls/{number}/files",
                {"per_page": per_page, "page": page},
            )
            files.extend(batch)
            if len(batch) < per_page:
                break
        return files

    async def workflow_runs_for_sha(self, repo: str, sha: str, per_page: int = 10) -> list[dict[str, Any]]:
        payload = await self._get(
            f"/repos/{repo}/actions/runs",
            {"head_sha": sha, "per_page": per_page},
        )
        return payload.get("workflow_runs", [])

    async def run_jobs(self, repo: str, run_id: int) -> list[dict[str, Any]]:
        payload = await self._get(f"/repos/{repo}/actions/runs/{run_id}/jobs", {"per_page": 100})
        return payload.get("jobs", [])

    async def latest_commit(self, repo: str) -> dict[str, Any] | None:
        commits = await self._get(f"/repos/{repo}/commits", {"per_page": 1})
        return commits[0] if commits else None

    async def get_commit(self, repo: str, sha: str) -> dict[str, Any]:
        return await self._get(f"/repos/{repo}/commits/{sha}")

    async def list_branches(
        self,
        repo: str,
        per_page: int = 100,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        return await self._get(
            f"/repos/{repo}/branches",
            {"per_page": per_page, "page": page},
        )

    async def list_all_branches(
        self,
        repo: str,
        *,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        branches: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            batch = await self.list_branches(repo, per_page=per_page, page=page)
            branches.extend(batch)
            if len(batch) < per_page:
                break
        return branches

    async def get_text_file(self, repo: str, path: str, ref: str | None = None) -> str:
        params = {"ref": ref} if ref else None
        payload = await self._get(f"/repos/{repo}/contents/{path}", params)
        encoded = payload.get("content") or ""
        if payload.get("encoding") != "base64":
            raise GitHubError(502, f"Encodage inattendu pour {path}.")
        return base64.b64decode(encoded).decode("utf-8")

    async def list_directory(
        self,
        repo: str,
        path: str,
        ref: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {"ref": ref} if ref else None
        payload = await self._get(f"/repos/{repo}/contents/{path}", params)
        if not isinstance(payload, list):
            raise GitHubError(502, f"{path} n'est pas un répertoire GitHub.")
        return payload
