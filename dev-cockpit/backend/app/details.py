from __future__ import annotations

import asyncio
import re
from typing import Any

from .config import Settings
from .derive import commit_summary
from .github import GitHubClient
from .roadmap import top_level_items

HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
WORK_KEY_RE = re.compile(r"(?<!\d)#?(?P<key>\d+[A-Z])\b", re.IGNORECASE)
ADR_RE = re.compile(r"\bADR-\d{3}\b", re.IGNORECASE)
DOC_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.-])(?P<path>docs/[A-Za-z0-9_./-]+\.md)\b")


def _issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "url": issue.get("html_url"),
        "updated_at": issue.get("updated_at"),
    }


def markdown_sections(body: str) -> list[dict[str, Any]]:
    lines = body.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        headings.append((index, len(match.group("marks")), match.group("title").strip()))

    sections: list[dict[str, Any]] = []
    for position, (start, level, title) in enumerate(headings):
        end = len(lines)
        for next_start, next_level, _ in headings[position + 1 :]:
            if next_level <= level:
                end = next_start
                break
        content = "\n".join(lines[start + 1 : end]).strip()
        key_match = WORK_KEY_RE.search(title)
        sections.append(
            {
                "title": title,
                "level": level,
                "work_key": key_match.group("key").upper() if key_match else None,
                "content": content,
            }
        )
    return sections


def _document_paths(text: str) -> list[str]:
    values: list[str] = []
    for match in DOC_PATH_RE.finditer(text):
        path = match.group("path")
        if path not in values:
            values.append(path)
    return values[:12]


def _adr_refs(text: str) -> list[str]:
    values: list[str] = []
    for match in ADR_RE.finditer(text):
        ref = match.group(0).upper()
        if ref not in values:
            values.append(ref)
    return values[:12]


def _doc_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line.strip())
        if match:
            return match.group(1)
    return fallback


def _doc_status(content: str) -> str | None:
    for line in content.splitlines()[:40]:
        match = re.match(
            r"^\s*(?:\*\*)?Status(?:ut)?(?:\*\*)?\s*[:—-]\s*(.+?)\s*$",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip(" *\x60")
    return None


async def _read_document(
    client: GitHubClient,
    repo: str,
    *,
    path: str,
    url: str | None = None,
    ref: str | None = None,
) -> dict[str, Any] | None:
    try:
        content = await client.get_text_file(repo, path, ref=ref)
    except Exception:
        return None
    return {
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "url": url or f"https://github.com/{repo}/blob/{ref or 'main'}/{path}",
        "title": _doc_title(content, path.rsplit("/", 1)[-1]),
        "status": _doc_status(content),
        "content": content,
    }


async def _issue_documents(
    client: GitHubClient,
    repo: str,
    body: str,
) -> list[dict[str, Any]]:
    explicit_paths = _document_paths(body)
    adr_refs = _adr_refs(body)

    architecture_entries: list[dict[str, Any]] = []
    if adr_refs:
        try:
            architecture_entries = await client.list_directory(repo, "docs/architecture")
        except Exception:
            architecture_entries = []

    by_path: dict[str, str | None] = {path: None for path in explicit_paths}
    for entry in architecture_entries:
        name = str(entry.get("name") or "")
        if not name.endswith(".md"):
            continue
        upper = name.upper()
        if any(upper.startswith(ref) for ref in adr_refs):
            path = str(entry.get("path") or f"docs/architecture/{name}")
            by_path.setdefault(path, entry.get("html_url"))

    jobs = [
        _read_document(client, repo, path=path, url=url)
        for path, url in list(by_path.items())[:12]
    ]
    results = await asyncio.gather(*jobs) if jobs else []
    return [result for result in results if result is not None]


async def build_issue_detail(
    client: GitHubClient,
    repo: str,
    number: int,
) -> dict[str, Any]:
    repo = client.validate_repo(repo)
    issue = await client.get_issue(repo, number)
    body = str(issue.get("body") or "")
    documents = await _issue_documents(client, repo, body)
    referenced_issues: list[int] = []
    for match in re.finditer(r"#(\d+)\b", body):
        value = int(match.group(1))
        if value == number or value in referenced_issues:
            continue
        referenced_issues.append(value)
        if len(referenced_issues) >= 20:
            break
    return {
        **_issue_summary(issue),
        "body": body,
        "sections": markdown_sections(body),
        "referenced_issues": referenced_issues,
        "documents": documents,
    }


async def build_roadmap_detail(
    client: GitHubClient,
    settings: Settings,
    repo: str,
) -> dict[str, Any]:
    repo = client.validate_repo(repo)
    issue = await client.get_issue(repo, settings.roadmap_issue)
    body = str(issue.get("body") or "")
    return {
        **_issue_summary(issue),
        "body": body,
        "items": [item.to_dict() for item in top_level_items(body)],
    }


async def build_commit_detail(
    client: GitHubClient,
    repo: str,
    sha: str,
) -> dict[str, Any]:
    repo = client.validate_repo(repo)
    commit = await client.get_commit(repo, sha)
    base = commit_summary(commit) or {}
    files = []
    documentation_jobs = []
    for row in commit.get("files") or []:
        filename = str(row.get("filename") or "")
        files.append(
            {
                "filename": filename,
                "status": row.get("status"),
                "additions": row.get("additions"),
                "deletions": row.get("deletions"),
                "changes": row.get("changes"),
                "url": row.get("blob_url"),
            }
        )
        if filename.startswith("docs/") and filename.endswith(".md") and row.get("status") != "removed":
            documentation_jobs.append(
                _read_document(
                    client,
                    repo,
                    path=filename,
                    url=row.get("blob_url"),
                    ref=sha,
                )
            )

    docs = await asyncio.gather(*documentation_jobs[:10]) if documentation_jobs else []
    stats = commit.get("stats") or {}
    return {
        **base,
        "sha": commit.get("sha") or sha,
        "author": (commit.get("commit") or {}).get("author", {}).get("name"),
        "stats": {
            "additions": stats.get("additions"),
            "deletions": stats.get("deletions"),
            "total": stats.get("total"),
        },
        "files": files,
        "documentation": [doc for doc in docs if doc is not None],
    }


async def build_architecture_detail(
    client: GitHubClient,
    repo: str,
) -> dict[str, Any]:
    repo = client.validate_repo(repo)
    entries = await client.list_directory(repo, "docs/architecture")
    markdown_entries = [
        entry
        for entry in entries
        if entry.get("type") == "file" and str(entry.get("name") or "").endswith(".md")
    ]

    def sort_key(entry: dict[str, Any]) -> tuple[int, str]:
        name = str(entry.get("name") or "")
        return (0 if name == "README.md" else 1, name)

    markdown_entries.sort(key=sort_key)
    jobs = [
        _read_document(
            client,
            repo,
            path=str(entry.get("path") or f"docs/architecture/{entry.get('name')}"),
            url=entry.get("html_url"),
        )
        for entry in markdown_entries
    ]
    documents = await asyncio.gather(*jobs) if jobs else []
    return {
        "path": "docs/architecture/",
        "url": f"https://github.com/{repo}/tree/main/docs/architecture",
        "documents": [doc for doc in documents if doc is not None],
    }
