from __future__ import annotations

import re
from dataclasses import asdict, dataclass

ACTIVE_PATTERNS = [
    re.compile(r"prochaine tranche active est\s+\*{0,2}`?#?(\d+[A-Z]?)", re.IGNORECASE),
    re.compile(r"prochaine tranche(?: produit)?\s+(?:est|:)\s+\*{0,2}`?#?(\d+[A-Z]?)", re.IGNORECASE),
    re.compile(r"#?(\d+[A-Z]?)\s+est\s+maintenant\s+la\s+tranche\s+active", re.IGNORECASE),
    re.compile(r"tranche\s+active\s*[:=]\s*\*{0,2}`?#?(\d+[A-Z]?)", re.IGNORECASE),
]

DONE_WORDS = re.compile(r"\b(?:termin[ée]e?s?|compl[ée]t[ée]e?s?|livr[ée]e?s?)\b", re.IGNORECASE)


@dataclass
class WorkItem:
    key: str
    title: str
    done: bool
    marker: str | None = None
    issue_number: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_key(value: str) -> str:
    value = value.strip().upper()
    return value[1:] if value.startswith("#") else value


def numeric_issue(key: str) -> int | None:
    match = re.match(r"^(\d+)", normalize_key(key))
    return int(match.group(1)) if match else None


def extract_declared_active(body: str) -> str | None:
    for pattern in ACTIVE_PATTERNS:
        match = pattern.search(body)
        if match:
            return normalize_key(match.group(1))
    return None


def _clean_markdown(line: str) -> str:
    return line.replace("**", "").replace("`", "").strip()


def _active_order_section(body: str) -> str:
    marker = re.search(r"Ordre actif\s*: ?", body, re.IGNORECASE)
    if not marker:
        marker = re.search(r"ordre recommandé devient\s*: ?", body, re.IGNORECASE)
    if not marker:
        return body
    section = body[marker.start():]
    stop = re.search(r"\n###\s+", section)
    return section[: stop.start()] if stop else section


def top_level_items(body: str) -> list[WorkItem]:
    section = _active_order_section(body)
    lines = section.splitlines()
    pattern = re.compile(r"^\s*\d+\.\s*(?P<marker>✅|🟡|⏳|⚠️|⬜)?\s*#(?P<key>\d+)\s*[—–-]\s*(?P<title>.+?)\s*$")
    matches: list[tuple[int, re.Match[str]]] = []
    seen: set[str] = set()

    for index, raw in enumerate(lines):
        line = _clean_markdown(raw)
        match = pattern.match(line)
        if not match or match.group("key") in seen:
            continue
        seen.add(match.group("key"))
        matches.append((index, match))

    items: list[WorkItem] = []
    for position, (line_index, match) in enumerate(matches):
        next_index = matches[position + 1][0] if position + 1 < len(matches) else len(lines)
        block = "\n".join(lines[line_index:next_index])
        key = match.group("key")
        marker = match.group("marker") or None
        completed_in_text = bool(
            re.search(r"\bBloc terminé\b", block, re.IGNORECASE)
            or re.search(rf"#{re.escape(key)}\s+est\s+[^\n]*(?:termin|complét)", block, re.IGNORECASE)
        )
        items.append(
            WorkItem(
                key=key,
                title=match.group("title").strip(),
                done=marker == "✅" or completed_in_text,
                marker="✅" if completed_in_text and marker is None else marker,
                issue_number=int(key),
            )
        )
    return items


def subitems_from_text(body: str, parent: int | str) -> list[WorkItem]:
    parent_text = str(parent)
    patterns = [
        re.compile(
            rf"^\s*#{{2,6}}\s*(?P<marker>✅|🟡|⏳|⚠️|⬜)?\s*#?(?P<key>{re.escape(parent_text)}[A-Z])\s*[—–-]\s*(?P<title>.+?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^\s*-\s*(?P<marker>✅|🟡|⏳|⚠️|⬜)?\s*#?(?P<key>{re.escape(parent_text)}[A-Z])\s*[—–-]\s*(?P<title>.+?)\s*$",
            re.IGNORECASE,
        ),
        re.compile(
            rf"^\s*-\s*\[(?P<checked>[xX ])\]\s*#?(?P<key>{re.escape(parent_text)}[A-Z])\s*[—–-]\s*(?P<title>.+?)\s*$",
            re.IGNORECASE,
        ),
    ]
    items: dict[str, WorkItem] = {}
    order: list[str] = []

    for raw in body.splitlines():
        line = _clean_markdown(raw)
        for pattern in patterns:
            match = pattern.match(line)
            if not match:
                continue
            key = normalize_key(match.group("key"))
            marker = match.groupdict().get("marker") or None
            checked = match.groupdict().get("checked")
            done = marker == "✅" or checked in {"x", "X"}
            title = match.group("title").strip()
            if DONE_WORDS.search(title) and re.search(r"\b(?:PR\s*#?\d+|CI\s*#?\d+|termin|complét|livr)", title, re.IGNORECASE):
                done = True
            if key not in items:
                items[key] = WorkItem(key=key, title=title, done=done, marker="✅" if done else marker, issue_number=int(parent_text))
                order.append(key)
            else:
                current = items[key]
                current.done = current.done or done
                if done:
                    current.marker = "✅"
                if len(title) > len(current.title):
                    current.title = title
            break
    return [items[key] for key in order]


def merge_subitems(primary: list[WorkItem], secondary: list[WorkItem]) -> list[WorkItem]:
    merged: dict[str, WorkItem] = {item.key: WorkItem(**item.to_dict()) for item in primary}
    order = [item.key for item in primary]
    for item in secondary:
        if item.key not in merged:
            merged[item.key] = WorkItem(**item.to_dict())
            order.append(item.key)
            continue
        current = merged[item.key]
        current.done = current.done or item.done
        if item.done:
            current.marker = "✅"
        if not current.title and item.title:
            current.title = item.title
    return [merged[key] for key in order]


def first_unfinished(items: list[WorkItem]) -> WorkItem | None:
    return next((item for item in items if not item.done), None)


def focus_items(top: list[WorkItem], subitems: list[WorkItem], parent: int) -> list[WorkItem]:
    parent_index = next((index for index, item in enumerate(top) if item.key == str(parent)), None)
    following = top[parent_index + 1 : parent_index + 4] if parent_index is not None else []
    return subitems + following if subitems else top


def active_block(body: str, parent: int | str) -> str:
    parent_text = str(parent)
    section = _active_order_section(body)
    lines = section.splitlines()
    start = None
    for idx, raw in enumerate(lines):
        line = _clean_markdown(raw)
        if re.match(rf"^\s*\d+\.\s*(?:✅|🟡|⏳|⚠️|⬜)?\s*#{re.escape(parent_text)}\b", line):
            start = idx
            break
    if start is None:
        return ""

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        line = _clean_markdown(lines[idx])
        if re.match(r"^\s*\d+\.\s*(?:✅|🟡|⏳|⚠️|⬜)?\s*#\d+\b", line):
            end = idx
            break
    return "\n".join(lines[start:end])


def referenced_issue_numbers(body: str, parent: int | str, limit: int = 12) -> list[int]:
    block = active_block(body, parent)
    if not block:
        return [int(parent)] if str(parent).isdigit() else []
    values: list[int] = []
    for match in re.finditer(r"#(\d+)\b", block):
        number = int(match.group(1))
        if number not in values:
            values.append(number)
        if len(values) >= limit:
            break
    return values


def has_explicit_block_order(issue_body: str, roadmap_block: str, subitems: list[WorkItem]) -> bool:
    if len(subitems) < 2:
        return False
    combined = f"{issue_body}\n{roadmap_block}"
    return bool(
        re.search(r"Ordre\s+obligatoire\s*:", combined, re.IGNORECASE)
        or re.search(r"Ordre\s*:\s*\*{0,2}\d+[A-Z]\s*(?:→|->)", combined, re.IGNORECASE)
    )


def agents_allow_chaining(agents_text: str) -> bool:
    lowered = agents_text.lower()
    return "chained execution" in lowered and "same approved work block" in lowered


def referenced_adrs(text: str, available_names: list[str]) -> list[str]:
    references = {match.upper() for match in re.findall(r"ADR-\d{3}", text, re.IGNORECASE)}
    return [name for name in available_names if any(name.upper().startswith(ref) for ref in references)]
