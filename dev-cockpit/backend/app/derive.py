from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

FAILURE_CONCLUSIONS = {"failure", "timed_out", "action_required", "startup_failure", "cancelled"}
RUNNING_STATUSES = {"queued", "in_progress", "waiting", "requested", "pending"}


def matches_work_key(value: dict[str, Any] | str, key: str | None) -> bool:
    if not key:
        return False
    if isinstance(value, str):
        haystack = value
    else:
        haystack = f"{value.get('title', '')}\n{value.get('body', '')}\n{value.get('head', '')}"
    pattern = re.compile(rf"(?<![A-Z0-9])#?{re.escape(key)}(?![A-Z0-9])", re.IGNORECASE)
    return bool(pattern.search(haystack))


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _age_minutes(value: str | None, now: datetime) -> int | None:
    parsed = parse_iso(value)
    if not parsed:
        return None
    return max(0, int((now - parsed).total_seconds() // 60))


def _latest_activity(
    candidates: list[tuple[str, str | None]],
) -> tuple[str | None, str | None]:
    parsed: list[tuple[datetime, str, str]] = []
    for source, value in candidates:
        timestamp = parse_iso(value)
        if timestamp is not None and value is not None:
            parsed.append((timestamp, source, value))
    if not parsed:
        return None, None
    _timestamp, source, value = max(parsed, key=lambda row: row[0])
    return source, value


def commit_summary(commit: dict[str, Any] | None) -> dict[str, Any] | None:
    if not commit:
        return None
    details = commit.get("commit") or {}
    author = details.get("author") or {}
    return {
        "sha": commit.get("sha"),
        "short_sha": (commit.get("sha") or "")[:7],
        "message": (details.get("message") or "").splitlines()[0],
        "date": author.get("date"),
        "url": commit.get("html_url"),
    }


def latest_run(pr: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pr:
        return None
    runs = pr.get("runs") or []
    return runs[0] if runs else None


def _run_failed(run: dict[str, Any]) -> bool:
    return (run.get("conclusion") or "").lower() in FAILURE_CONCLUSIONS or any(
        (job.get("conclusion") or "").lower() in FAILURE_CONCLUSIONS
        for job in (run.get("jobs") or [])
    )


def _run_running(run: dict[str, Any]) -> bool:
    return (run.get("status") or "").lower() in RUNNING_STATUSES or any(
        (job.get("status") or "").lower() in RUNNING_STATUSES
        for job in (run.get("jobs") or [])
    )


def derive_states(
    *,
    block_done: bool,
    primary_pr: dict[str, Any] | None,
    active_branch: dict[str, Any] | None,
    active_commit_date: str | None,
    stalled_after_minutes: int,
    active_runs: list[dict[str, Any]] | None = None,
    explicit_in_progress: bool = False,
    issue_updated_at: str | None = None,
    roadmap_updated_at: str | None = None,
    now: datetime | None = None,
    blocked_by_roadmap: bool = False,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    states: list[str] = []
    runs = active_runs if active_runs is not None else (primary_pr or {}).get("runs") or []
    running_runs = [run for run in runs if _run_running(run)]
    latest = runs[0] if runs else None
    ci_running = bool(running_runs)
    ci_red = bool(latest and _run_failed(latest) and not ci_running)
    failed_jobs = [
        job.get("name", "job")
        for job in ((latest or {}).get("jobs") or [])
        if (job.get("conclusion") or "").lower() in FAILURE_CONCLUSIONS
    ] if ci_red else []

    if block_done:
        states.append("DONE")
    elif primary_pr and primary_pr.get("state") == "open":
        states.append("IN_PROGRESS")
    elif active_branch or explicit_in_progress:
        states.append("IN_PROGRESS")
    else:
        states.append("READY")

    if ci_running:
        states.append("CI_RUNNING")
    if ci_red:
        states.append("CI_RED")

    latest_success = bool(
        latest
        and latest.get("status") == "completed"
        and latest.get("conclusion") == "success"
    )
    if (
        primary_pr
        and primary_pr.get("state") == "open"
        and primary_pr.get("mergeable") is True
        and latest_success
        and not ci_running
    ):
        states.append("MERGEABLE")

    if blocked_by_roadmap or (
        primary_pr
        and primary_pr.get("state") == "open"
        and primary_pr.get("mergeable") is False
        and not ci_red
        and not ci_running
    ):
        states.append("BLOCKED")

    commit_age = _age_minutes(active_commit_date, now)
    failed_at = None
    if latest and ci_red:
        failed_at = latest.get("updated_at") or latest.get("completed_at") or latest.get("created_at")
    failed_age = _age_minutes(failed_at, now)
    commit_dt = parse_iso(active_commit_date)
    failed_dt = parse_iso(failed_at)
    no_new_commit_since_failure = bool(
        commit_dt is None or failed_dt is None or commit_dt <= failed_dt
    )

    activity_candidates: list[tuple[str, str | None]] = [
        ("commit", active_commit_date),
        ("pr", (primary_pr or {}).get("updated_at")),
    ]
    for run in runs:
        activity_candidates.append(
            (
                "workflow",
                run.get("updated_at") or run.get("completed_at") or run.get("created_at"),
            )
        )
    if explicit_in_progress:
        activity_candidates.append(("issue", issue_updated_at))
        if not issue_updated_at:
            activity_candidates.append(("roadmap", roadmap_updated_at))

    last_activity_source, last_activity_at = _latest_activity(activity_candidates)
    last_activity_minutes = _age_minutes(last_activity_at, now)

    branch_present = bool(active_branch)
    pr_present = bool(primary_pr)
    work_started = branch_present or pr_present or explicit_in_progress
    threshold_elapsed = (
        last_activity_minutes is not None
        and last_activity_minutes >= stalled_after_minutes
    )

    stall_level: str | None = None
    if not block_done and not blocked_by_roadmap and not ci_running and work_started:
        confirmed = bool(
            ci_red
            and failed_age is not None
            and failed_age >= stalled_after_minutes
            and no_new_commit_since_failure
        )
        if confirmed:
            stall_level = "confirmed"
            states.append("STALLED_CONFIRMED")
        elif (branch_present or pr_present) and threshold_elapsed:
            stall_level = "stalled"
            states.append("STALLED")
        elif (
            explicit_in_progress
            and not branch_present
            and not pr_present
            and threshold_elapsed
        ):
            stall_level = "possible"
            states.append("POSSIBLE_STALL")

    stalled = stall_level is not None

    return {
        "states": states,
        "stalled": stalled,
        "stall_level": stall_level,
        "failed_jobs": failed_jobs,
        "ci_running": ci_running,
        "ci_red": ci_red,
        "stalled_details": {
            "level": stall_level,
            "threshold_minutes": stalled_after_minutes,
            "ci_failed_at": failed_at,
            "ci_failed_minutes": failed_age,
            "last_commit_at": active_commit_date,
            "last_commit_minutes": commit_age,
            "last_activity_at": last_activity_at,
            "last_activity_minutes": last_activity_minutes,
            "last_activity_source": last_activity_source,
            "no_new_commit": (
                no_new_commit_since_failure
                if ci_red
                else bool(commit_age is not None and commit_age >= stalled_after_minutes)
            ),
            "no_active_workflow": not ci_running,
            "branch_present": branch_present,
            "pr_present": pr_present,
            "explicit_in_progress": explicit_in_progress,
        },
    }


def build_next_action_and_prompt(
    *,
    parent_issue: int,
    active_key: str | None,
    block_done: bool,
    can_chain_block: bool,
    primary_pr: dict[str, Any] | None,
    active_branch: dict[str, Any] | None,
    derived: dict[str, Any],
    roadmap_issue: int,
    merged_but_unmarked_pr: dict[str, Any] | None = None,
    remaining_subitems: list[str] | None = None,
) -> tuple[str, str]:
    if block_done:
        return (
            f"Le bloc #{parent_issue} semble terminé; vérifier GitHub avant de passer au prochain READY.",
            f"Le bloc #{parent_issue} semble terminé.\n"
            f"Vérifie #{parent_issue} et le roadmap maître #{roadmap_issue}, mets leur état à jour si nécessaire\n"
            "et détermine le prochain item READY selon AGENTS.md.",
        )

    slice_key = active_key or str(parent_issue)
    pr_number = primary_pr.get("number") if primary_pr else None
    failed_jobs = derived.get("failed_jobs") or []
    details = derived.get("stalled_details") or {}
    inactive_minutes = details.get("last_activity_minutes")
    inactive_text = (
        f" depuis {inactive_minutes} min"
        if inactive_minutes is not None
        else ""
    )

    if merged_but_unmarked_pr:
        merged_number = merged_but_unmarked_pr.get("number")
        return (
            f"{slice_key} a une PR fusionnée mais n'est pas marquée terminée; aligner GitHub avant la suite.",
            f"La PR #{merged_number} associée à {slice_key} est fusionnée, mais la tranche n'est pas explicitement terminée dans #{parent_issue}/#{roadmap_issue}.\n"
            f"Vérifie et mets à jour l'état GitHub selon AGENTS.md avant de démarrer la tranche suivante.",
        )

    stall_level = derived.get("stall_level")
    if stall_level == "confirmed":
        failed = f" ({', '.join(failed_jobs)})" if failed_jobs else ""
        branch_name = (active_branch or {}).get("name")
        context = (
            f"la PR #{pr_number}"
            if pr_number
            else f"la branche {branch_name}"
            if branch_name
            else "l'état GitHub actuel"
        )
        action = f"Reprendre {slice_key} : CI rouge abandonnée{failed}."
        prompt = (
            f"Reprends {slice_key} depuis {context}.\n"
            f"La CI est rouge et aucune activité de reprise n'est visible{inactive_text} : analyse les jobs en échec{failed},\n"
            f"corrige les causes liées à la tranche et poursuis ensuite #{parent_issue} selon AGENTS.md et #{roadmap_issue}."
        )
        return action, prompt

    if stall_level == "stalled":
        branch_name = (active_branch or {}).get("name")
        if primary_pr:
            context = f"la PR #{pr_number}"
        elif branch_name:
            context = f"la branche {branch_name}"
        else:
            context = "l'état GitHub existant"
        return (
            f"Reprendre {slice_key} : aucune activité GitHub pertinente{inactive_text}.",
            f"Reprends {slice_key} depuis {context}. Aucune activité GitHub pertinente n'est visible{inactive_text}\n"
            f"et aucun workflow n'est actif. Inspecte l'état existant avant de créer une nouvelle branche ou PR,\n"
            f"puis poursuis le bloc #{parent_issue} selon AGENTS.md et le roadmap maître #{roadmap_issue}.",
        )

    if stall_level == "possible":
        return (
            f"Vérifier {slice_key} : travail possiblement interrompu{inactive_text}.",
            f"Reprends {slice_key} depuis l'état GitHub actuel. La tranche est explicitement en cours, mais aucune branche,\n"
            f"PR ou workflow associé n'est visible{inactive_text}. Vérifie d'abord s'il existe du travail non publié;\n"
            f"sinon repars du dernier état GitHub vérifié et poursuis #{parent_issue} selon AGENTS.md et #{roadmap_issue}.",
        )

    if derived.get("ci_red"):
        failed = f" ({', '.join(failed_jobs)})" if failed_jobs else ""
        branch_name = (active_branch or {}).get("name")
        context = (
            f"la PR #{pr_number}"
            if pr_number
            else f"la branche {branch_name}"
            if branch_name
            else "l'état GitHub actuel"
        )
        action = f"Reprendre {slice_key} : CI rouge{failed}."
        prompt = (
            f"Reprends {slice_key} depuis {context}.\n"
            f"La CI est rouge : analyse les jobs en échec{failed}, corrige les causes liées\n"
            f"à la tranche et poursuis ensuite #{parent_issue} selon AGENTS.md et #{roadmap_issue}."
        )
        return action, prompt

    if derived.get("ci_running"):
        source = f"la PR #{pr_number}" if pr_number else "la branche active"
        return (
            f"CI en cours pour {slice_key}.",
            f"Reprends {slice_key} depuis l'état actuel de {source} et poursuis le bloc #{parent_issue}\n"
            f"selon AGENTS.md et #{roadmap_issue}.",
        )

    if "BLOCKED" in derived.get("states", []) and primary_pr:
        return (
            f"PR #{pr_number} bloquée/non mergeable pour {slice_key}.",
            f"Reprends {slice_key} depuis la PR #{pr_number}. Résous le blocage vérifié dans GitHub,\n"
            f"puis poursuis #{parent_issue} selon AGENTS.md et le roadmap maître #{roadmap_issue}.",
        )

    if "MERGEABLE" in derived.get("states", []) and primary_pr:
        return (
            f"PR #{pr_number} verte et mergeable; terminer le workflow AGENTS.md.",
            f"Reprends {slice_key} depuis la PR #{pr_number}. La CI est verte et la PR est mergeable.\n"
            f"Termine le workflow prévu par AGENTS.md, mets à jour #{parent_issue}/#{roadmap_issue} si nécessaire\n"
            f"et poursuis uniquement les tranches READY autorisées du bloc #{parent_issue}.",
        )

    if primary_pr:
        return (
            f"Poursuivre la PR #{pr_number} pour {slice_key}.",
            f"Reprends {slice_key} depuis l'état actuel de la PR #{pr_number} et poursuis le bloc #{parent_issue}\n"
            f"selon AGENTS.md et #{roadmap_issue}.",
        )

    branch_name = (active_branch or {}).get("name")
    first_line = f"Continue #{parent_issue} à partir de {slice_key} selon AGENTS.md et le roadmap maître #{roadmap_issue}."
    if branch_name:
        first_line = f"Reprends #{parent_issue} à partir de {slice_key} sur la branche {branch_name} selon AGENTS.md et #{roadmap_issue}."

    lines = [
        first_line,
        f"Consulte l'issue #{parent_issue} et les ADR applicables dans docs/architecture/.",
    ]
    if can_chain_block:
        remaining = remaining_subitems or []
        chain = " → ".join(remaining)
        if chain:
            lines.append(
                f"Enchaîne autonomement {chain} dans cet ordre tant qu'aucune\n"
                "condition d'arrêt d'AGENTS.md n'est rencontrée."
            )
        else:
            lines.append(
                f"Enchaîne autonomement les tranches restantes du bloc #{parent_issue} tant qu'aucune\n"
                "condition d'arrêt d'AGENTS.md n'est rencontrée."
            )
    return (
        f"Démarrer/reprendre {slice_key} dans le bloc #{parent_issue}.",
        "\n".join(lines),
    )
