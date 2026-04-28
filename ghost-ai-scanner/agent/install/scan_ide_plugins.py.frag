# =============================================================
# FRAGMENT: scan_ide_plugins.py.frag
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Walk IDE extension/plugin directories and match against
#          AI plugin IDs (Copilot, Codeium, Tabnine, Continue, etc).
#          VS Code, Cursor, JetBrains (all subdirs).
#          macOS + Linux paths. (Windows handled by .ps1.frag.)
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Group 2.C — IDE plugin enumeration.
# =============================================================

_AI_IDE_PLUGINS_RE = re.compile(
    r"\b(github\.copilot|github\.copilot-chat|codeium\.codeium|"
    r"tabnine\.tabnine-vscode|continue\.continue|aws\.amazon-q-vscode|"
    r"com\.github\.copilot|com\.codeium\.intellij|com\.tabnine\.intellij)\b",
    re.IGNORECASE,
)


def _vscode_dirs() -> list:
    """Candidate VS Code-like extension roots across macOS / Linux / Windows."""
    h = Path.home()
    base = [
        h / ".vscode/extensions",
        h / ".vscode-insiders/extensions",
        h / ".cursor/extensions",
        h / ".vscode-server/extensions",
    ]
    if OS_NAME == "windows":
        userprofile = Path(os.environ.get("USERPROFILE", h))
        base += [userprofile / ".vscode/extensions",
                 userprofile / ".cursor/extensions"]
    return base


def _jetbrains_roots() -> list:
    """Candidate JetBrains config roots; we walk plugin/ subdirs across every IDE."""
    h = Path.home()
    if OS_NAME == "darwin":
        return [h / "Library/Application Support/JetBrains"]
    if OS_NAME == "windows":
        ad = Path(os.environ.get("APPDATA", h / "AppData/Roaming"))
        return [ad / "JetBrains"]
    return [h / ".config/JetBrains", h / ".local/share/JetBrains"]


def scan_ide_plugins() -> list:
    """Walk extensions and JetBrains plugins; emit a finding per AI plugin found."""
    findings: list = []

    # VS Code / Cursor — directory entries are <publisher>.<name>-<version>
    for root in _vscode_dirs():
        if not root.exists():
            continue
        for child in root.iterdir():
            if not child.is_dir():
                continue
            base = child.name.rsplit("-", 1)[0].lower()
            if _AI_IDE_PLUGINS_RE.search(base) and not _is_authorized(base):
                findings.append({"type": "ide_plugin", "ide": "vscode_family", "plugin_id": base})

    # JetBrains — all subdirs (IntelliJ, PyCharm, GoLand, WebStorm, etc.)
    for root in _jetbrains_roots():
        if not root.exists():
            continue
        for ide_dir in root.iterdir():
            plugins_dir = ide_dir / "plugins"
            if not plugins_dir.exists():
                continue
            for plugin in plugins_dir.iterdir():
                pid = plugin.name.lower()
                if _AI_IDE_PLUGINS_RE.search(pid) and not _is_authorized(pid):
                    findings.append({"type": "ide_plugin", "ide": ide_dir.name, "plugin_id": pid})
    return findings
