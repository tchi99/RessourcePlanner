from __future__ import annotations

from .excel_repository import ExcelRepository
from .resource_local_preferences import _load_preferences, _save_preferences, _workbook_key


MAIL_CLIENT_OUTLOOK = "outlook"
MAIL_CLIENT_THUNDERBIRD = "thunderbird"
MAIL_CLIENTS = {MAIL_CLIENT_OUTLOOK, MAIL_CLIENT_THUNDERBIRD}


def mail_client_preference(repo: ExcelRepository) -> str:
    data = _load_preferences()
    section = data.get("workbooks", {}).get(_workbook_key(repo), {})
    if not isinstance(section, dict):
        return MAIL_CLIENT_OUTLOOK
    value = str(section.get("communication_mail_client") or "").strip().lower()
    return value if value in MAIL_CLIENTS else MAIL_CLIENT_OUTLOOK


def set_mail_client_preference(repo: ExcelRepository, value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in MAIL_CLIENTS:
        raise ValueError("Client courriel non pris en charge.")
    data = _load_preferences()
    workbooks = data.setdefault("workbooks", {})
    section = workbooks.setdefault(_workbook_key(repo), {})
    if not isinstance(section, dict):
        section = {}
        workbooks[_workbook_key(repo)] = section
    section["communication_mail_client"] = normalized
    _save_preferences(data)
    return normalized
