from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


OUTLOOK_MESSAGE_PROPERTY = "RessourcePlannerMessageID"


class OutlookDraftTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutlookDraftRequest:
    message_id: str
    batch_id: str
    to_address: str
    subject: str
    body: str


@dataclass(frozen=True)
class OutlookDraftFailure:
    message_id: str
    error: str


@dataclass(frozen=True)
class OutlookDraftResult:
    created_message_ids: tuple[str, ...] = ()
    existing_message_ids: tuple[str, ...] = ()
    failures: tuple[OutlookDraftFailure, ...] = ()

    @property
    def completed_message_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.created_message_ids + self.existing_message_ids))


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _powershell_script() -> str:
    # Safety invariant: the script saves messages to Drafts and contains no Send call.
    return r'''param(
    [Parameter(Mandatory=$true)]
    [string]$InputPath
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$data = Get-Content -Raw -Encoding UTF8 -LiteralPath $InputPath | ConvertFrom-Json
$requested = @{}
foreach ($message in @($data.messages)) {
    $requested[[string]$message.message_id] = $true
}

$existingMap = @{}
try {
    $outlook = New-Object -ComObject Outlook.Application
    $namespace = $outlook.GetNamespace("MAPI")
    $draftFolder = $namespace.GetDefaultFolder(16)
    $items = $draftFolder.Items

    for ($i = 1; $i -le $items.Count; $i++) {
        try {
            $item = $items.Item($i)
            $property = $item.UserProperties.Find("RessourcePlannerMessageID")
            if ($null -ne $property) {
                $value = [string]$property.Value
                if ($requested.ContainsKey($value)) {
                    $existingMap[$value] = $true
                }
            }
        }
        catch {
            # Ignore unrelated Drafts items that do not expose custom properties cleanly.
        }
    }
}
catch {
    [Console]::Error.WriteLine("OUTLOOK_COM_UNAVAILABLE")
    exit 20
}

$created = New-Object System.Collections.Generic.List[string]
$existing = New-Object System.Collections.Generic.List[string]
$failed = New-Object System.Collections.Generic.List[object]

foreach ($message in @($data.messages)) {
    $messageId = [string]$message.message_id
    if ($existingMap.ContainsKey($messageId)) {
        $existing.Add($messageId)
        continue
    }

    try {
        $mail = $outlook.CreateItem(0)
        $mail.To = [string]$message.to_address
        $mail.Subject = [string]$message.subject
        $mail.Body = [string]$message.body
        $property = $mail.UserProperties.Find("RessourcePlannerMessageID")
        if ($null -eq $property) {
            $property = $mail.UserProperties.Add("RessourcePlannerMessageID", 1, $false)
        }
        $property.Value = $messageId
        $mail.Save()
        $created.Add($messageId)
        $existingMap[$messageId] = $true
    }
    catch {
        $failed.Add([pscustomobject]@{
            message_id = $messageId
            error = $_.Exception.GetType().Name
        })
    }
}

[pscustomobject]@{
    created = @($created)
    existing = @($existing)
    failed = @($failed)
} | ConvertTo-Json -Depth 5 -Compress
'''


def _powershell_executable() -> str:
    for candidate in ("powershell.exe", "pwsh.exe"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise OutlookDraftTransportError(
        "PowerShell est requis pour créer les brouillons Outlook sur ce poste."
    )


def _normalize_string_list(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value if str(item or "").strip())
    return (str(value),)


def _parse_result(stdout: str) -> OutlookDraftResult:
    try:
        payload = json.loads(str(stdout or "").strip() or "{}")
    except json.JSONDecodeError as exc:
        raise OutlookDraftTransportError(
            "Outlook a répondu avec un résultat de création de brouillons invalide."
        ) from exc

    failures_raw = payload.get("failed") or []
    if isinstance(failures_raw, dict):
        failures_raw = [failures_raw]
    failures = tuple(
        OutlookDraftFailure(
            message_id=str(row.get("message_id") or ""),
            error=str(row.get("error") or "Erreur Outlook"),
        )
        for row in failures_raw
        if isinstance(row, dict) and str(row.get("message_id") or "").strip()
    )
    return OutlookDraftResult(
        created_message_ids=_normalize_string_list(payload.get("created")),
        existing_message_ids=_normalize_string_list(payload.get("existing")),
        failures=failures,
    )


def create_outlook_drafts(
    requests: Sequence[OutlookDraftRequest],
    *,
    runner: Runner | None = None,
    platform_name: str | None = None,
) -> OutlookDraftResult:
    """Create classic Outlook drafts only; this function never sends mail.

    A stable custom Outlook property is attached to every draft. Retrying after an
    interrupted application run therefore reuses an already-created draft instead of
    creating a duplicate whenever Outlook still contains that draft.
    """
    rows = tuple(requests)
    if not rows:
        return OutlookDraftResult()

    for row in rows:
        if not str(row.message_id or "").strip():
            raise ValueError("Chaque message Outlook doit avoir un identifiant stable.")
        if not str(row.to_address or "").strip():
            raise ValueError("Chaque brouillon Outlook doit avoir un destinataire.")

    effective_platform = platform_name or os.name
    if runner is None and effective_platform != "nt":
        raise OutlookDraftTransportError(
            "La création de brouillons Outlook est disponible uniquement sous Windows."
        )

    execute = runner or subprocess.run
    with tempfile.TemporaryDirectory(prefix="ressourceplanner-outlook-") as temp_dir:
        root = Path(temp_dir)
        payload_path = root / "messages.json"
        script_path = root / "create_drafts.ps1"
        payload_path.write_text(
            json.dumps(
                {
                    "messages": [
                        {
                            "message_id": row.message_id,
                            "batch_id": row.batch_id,
                            "to_address": row.to_address,
                            "subject": row.subject,
                            "body": row.body,
                        }
                        for row in rows
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        script_path.write_text(_powershell_script(), encoding="utf-8")

        executable = _powershell_executable() if runner is None else "powershell.exe"
        command = [
            executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-InputPath",
            str(payload_path),
        ]
        completed = execute(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    if completed.returncode != 0:
        if "OUTLOOK_COM_UNAVAILABLE" in str(completed.stderr or ""):
            raise OutlookDraftTransportError(
                "Impossible d'ouvrir une session Outlook compatible avec l'automatisation. "
                "Cette fonction nécessite Outlook classique pour Windows ou une installation Outlook offrant l'interface COM."
            )
        raise OutlookDraftTransportError(
            f"La création des brouillons Outlook a échoué (code {completed.returncode})."
        )

    return _parse_result(completed.stdout)
