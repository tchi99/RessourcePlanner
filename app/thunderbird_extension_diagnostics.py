from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path


DIAGNOSTIC_EXTENSION_VERSION = "1.1.0"

_DIAGNOSTIC_HTML = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\">
  <title>RessourcePlanner Bridge</title>
  <style>
    body { font-family: sans-serif; min-width: 360px; margin: 16px; }
    .ok { color: #137333; }
    .bad { color: #b3261e; }
    .muted { color: #666; font-size: 0.9em; }
    button { margin-top: 12px; }
    pre { white-space: pre-wrap; word-break: break-word; }
  </style>
</head>
<body>
  <h3>RessourcePlanner Draft Bridge</h3>
  <div id=\"extension\">Extension chargée…</div>
  <div id=\"native\">Test du pont natif…</div>
  <pre id=\"detail\"></pre>
  <button id=\"retry\" type=\"button\">Retester</button>
  <p class=\"muted\">Ce test n'envoie aucun courriel. Il vérifie seulement la communication entre Thunderbird et le pont local.</p>
  <script src=\"diagnostic.js\"></script>
</body>
</html>
"""

_DIAGNOSTIC_JS = r'''const HOST = "com.ressourceplanner.bridge";

function text(id, value, cssClass = "") {
  const node = document.getElementById(id);
  node.textContent = value;
  node.className = cssClass;
}

async function runDiagnostic() {
  text("extension", `Extension chargée · ID: ${browser.runtime.id}`, "ok");
  text("native", "Test du pont natif…");
  text("detail", "");
  try {
    const response = await browser.runtime.sendNativeMessage(HOST, {action: "status"});
    if (response && response.ok) {
      text("native", "Pont natif Thunderbird ↔ Windows : OK", "ok");
      text("detail", "La communication native fonctionne. RessourcePlanner devrait détecter le pont dans quelques secondes.");
      try {
        await browser.storage.local.set({
          rpLastNativeOk: new Date().toISOString(),
          rpLastNativeError: ""
        });
      } catch (_) {}
      return;
    }
    throw new Error(`Réponse invalide du pont: ${JSON.stringify(response)}`);
  } catch (error) {
    const detail = error && error.message ? String(error.message) : String(error);
    text("native", "Pont natif Thunderbird ↔ Windows : ÉCHEC", "bad");
    text("detail", detail, "bad");
    try {
      await browser.storage.local.set({
        rpLastNativeError: detail,
        rpLastNativeErrorAt: new Date().toISOString()
      });
    } catch (_) {}
  }
}

document.getElementById("retry").addEventListener("click", runDiagnostic);
runDiagnostic();
'''


def _enhanced_background(existing: str) -> str:
    marker = "// RessourcePlanner extension diagnostics v1.1.0"
    if marker in existing:
        return existing
    diagnostic = r'''

// RessourcePlanner extension diagnostics v1.1.0
async function recordNativeBridgeState(ok, detail = "") {
  try {
    await browser.storage.local.set({
      rpLastNativeOk: ok ? new Date().toISOString() : "",
      rpLastNativeError: ok ? "" : String(detail || "nativeMessaging failure"),
      rpLastNativeErrorAt: ok ? "" : new Date().toISOString()
    });
  } catch (_) {}
}

async function heartbeatNativeBridge() {
  try {
    const response = await browser.runtime.sendNativeMessage(HOST, {action: "status"});
    await recordNativeBridgeState(Boolean(response && response.ok), response && response.error ? response.error : "");
  } catch (error) {
    const detail = error && error.message ? String(error.message) : String(error);
    console.error("RessourcePlanner native bridge:", detail);
    await recordNativeBridgeState(false, detail);
  }
}

heartbeatNativeBridge();
setInterval(heartbeatNativeBridge, 10000);
'''
    return existing.rstrip() + diagnostic + "\n"


def enhance_thunderbird_extension(package_path: Path) -> Path:
    """Upgrade the generated XPI with a visible native-messaging diagnostic popup.

    The original bridge remains unchanged; this only adds observability and bumps the
    extension version so Thunderbird can install it over older 1.0.0 builds.
    """
    package_path = Path(package_path)
    with zipfile.ZipFile(package_path, "r") as source:
        entries = {name: source.read(name) for name in source.namelist()}

    manifest = json.loads(entries["manifest.json"].decode("utf-8"))
    manifest["version"] = DIAGNOSTIC_EXTENSION_VERSION
    permissions = list(manifest.get("permissions") or [])
    if "storage" not in permissions:
        permissions.append("storage")
    manifest["permissions"] = permissions
    manifest["browser_action"] = {
        "default_title": "RessourcePlanner Bridge",
        "default_popup": "diagnostic.html",
    }

    background = entries.get("background.js", b"").decode("utf-8")
    entries["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    entries["background.js"] = _enhanced_background(background).encode("utf-8")
    entries["diagnostic.html"] = _DIAGNOSTIC_HTML.encode("utf-8")
    entries["diagnostic.js"] = _DIAGNOSTIC_JS.encode("utf-8")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xpi", dir=str(package_path.parent)) as tmp:
        temporary = Path(tmp.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, payload in entries.items():
                target.writestr(name, payload)
        temporary.replace(package_path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return package_path
