"""
config_manager.py
-----------------
Responsible for bootstrapping user configuration on first run and
loading it on subsequent runs.

Strategy:
  - Config lives at ~/.config/clip-obsidian-ai/{config.yaml, format.md}
  - If missing, files are copied from the package's bundled defaults.
  - Exposes a typed AppConfig dataclass for the rest of the application.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
# Defaults shipped with the package (same directory as this file when installed,
# or the repo's config/ folder during development).
_PACKAGE_DIR = Path(__file__).parent
_DEFAULTS_DIR = _PACKAGE_DIR / "config"

# User-facing config directory (XDG-compliant)
USER_CONFIG_DIR = Path.home() / ".config" / "clip-obsidian-ai"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.yaml"
USER_FORMAT_FILE = USER_CONFIG_DIR / "format.md"


# ── Dataclasses ────────────────────────────────────────────────────────────

@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = "llama3.2"
    host: str = "http://localhost:11434"
    timeout: int = 120
    max_input_chars: int = 12000
    api_key: str = ""


@dataclass
class ClipboardConfig:
    backend: str = "auto"


@dataclass
class UIConfig:
    backend: str = "auto"
    prompt_message: str = "¿Procesar este texto con IA?"
    confirm_label: str = "✅ Sí, procesar"
    cancel_label: str = "❌ Cancelar"
    preview_chars: int = 300


@dataclass
class NotificationsConfig:
    enabled: bool = True
    backend: str = "notify-send"
    app_name: str = "clip-obsidian-ai"
    timeout_ms: int = 4000


@dataclass
class DirModeConfig:
    output_filename: str = "notas_generadas.md"
    supported_extensions: list[str] = field(
        default_factory=lambda: [".pdf", ".pptx", ".docx", ".txt", ".md"]
    )
    recursive: bool = False
    file_separator: str = "\n\n---\n\n"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    show_timestamps: bool = False


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    clipboard: ClipboardConfig = field(default_factory=ClipboardConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    dir_mode: DirModeConfig = field(default_factory=DirModeConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    # Path to the format template (resolved at load time)
    format_file: Path = field(default_factory=lambda: USER_FORMAT_FILE)


# ── Bootstrap ──────────────────────────────────────────────────────────────

def _ensure_user_config() -> None:
    """
    Creates ~/.config/clip-obsidian-ai/ and copies default files into it
    if they do not already exist.
    """
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    for src, dst in [
        (_DEFAULTS_DIR / "config.yaml", USER_CONFIG_FILE),
        (_DEFAULTS_DIR / "format.md", USER_FORMAT_FILE),
    ]:
        if not dst.exists():
            if src.exists():
                shutil.copy2(src, dst)
                logger.info("Created default config file: %s", dst)
            else:
                logger.warning(
                    "Default file not found at %s — skipping copy.", src
                )


# ── Loaders ────────────────────────────────────────────────────────────────

def _deep_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dicts without KeyError."""
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


def load_config() -> AppConfig:
    """
    Public entry point.  Bootstraps user config on first run, then
    loads and parses config.yaml into an AppConfig dataclass.
    """
    _ensure_user_config()

    raw: dict[str, Any] = {}
    if USER_CONFIG_FILE.exists():
        with USER_CONFIG_FILE.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    else:
        logger.warning("config.yaml not found – using built-in defaults.")

    import os
    llm_raw = raw.get("llm", {})
    clip_raw = raw.get("clipboard", {})
    ui_raw = raw.get("ui", {})
    notif_raw = raw.get("notifications", {})
    dir_raw = raw.get("dir_mode", {})
    log_raw = raw.get("logging", {})

    env_key = os.environ.get("GEMINI_API_KEY")
    api_key_val = env_key if env_key is not None else llm_raw.get("api_key", "")

    config = AppConfig(
        llm=LLMConfig(
            provider=llm_raw.get("provider", "ollama"),
            model=llm_raw.get("model", "llama3.2"),
            host=llm_raw.get("host", "http://localhost:11434"),
            timeout=int(llm_raw.get("timeout", 120)),
            max_input_chars=int(llm_raw.get("max_input_chars", 12000)),
            api_key=api_key_val,
        ),
        clipboard=ClipboardConfig(
            backend=clip_raw.get("backend", "auto"),
        ),
        ui=UIConfig(
            backend=ui_raw.get("backend", "auto"),
            prompt_message=ui_raw.get("prompt_message", "¿Procesar este texto con IA?"),
            confirm_label=ui_raw.get("confirm_label", "✅ Sí, procesar"),
            cancel_label=ui_raw.get("cancel_label", "❌ Cancelar"),
            preview_chars=int(ui_raw.get("preview_chars", 300)),
        ),
        notifications=NotificationsConfig(
            enabled=bool(notif_raw.get("enabled", True)),
            backend=notif_raw.get("backend", "notify-send"),
            app_name=notif_raw.get("app_name", "clip-obsidian-ai"),
            timeout_ms=int(notif_raw.get("timeout_ms", 4000)),
        ),
        dir_mode=DirModeConfig(
            output_filename=dir_raw.get("output_filename", "notas_generadas.md"),
            supported_extensions=dir_raw.get(
                "supported_extensions", [".pdf", ".pptx", ".docx", ".txt", ".md"]
            ),
            recursive=bool(dir_raw.get("recursive", False)),
            file_separator=dir_raw.get("file_separator", "\n\n---\n\n"),
        ),
        logging=LoggingConfig(
            level=log_raw.get("level", "INFO"),
            show_timestamps=bool(log_raw.get("show_timestamps", False)),
        ),
        format_file=USER_FORMAT_FILE,
    )

    return config


def load_format_template(config: AppConfig) -> str:
    """
    Reads format.md at call time (not at startup) so users can edit it
    without restarting anything.
    """
    path = config.format_file
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("format.md not found at %s – using empty system prompt.", path)
    return ""
