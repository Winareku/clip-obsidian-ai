"""
adapters/__init__.py
--------------------
Adapter layer.  Each adapter wraps an external tool or service behind a
stable Python interface, so the rest of the application never depends on
concrete system commands.

Exports:
  - ClipboardAdapter   (ABC) + WlClipboardAdapter, XClipAdapter
  - UIAdapter          (ABC) + WofiAdapter, RofiAdapter, ZenityAdapter, NullUIAdapter
  - NotifierAdapter    (ABC) + NotifySendAdapter, NullNotifierAdapter
  - LLMAdapter         (ABC) + OllamaAdapter
  - AdapterFactory     (auto-detects and instantiates the right adapters)
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _run(cmd: list[str], input_text: Optional[str] = None, timeout: int = 10) -> subprocess.CompletedProcess:
    """Thin wrapper around subprocess.run with consistent defaults."""
    return subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _has_cmd(*commands: str) -> Optional[str]:
    """Returns the first command that exists on PATH, or None."""
    for cmd in commands:
        if shutil.which(cmd):
            return cmd
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Clipboard Adapters
# ══════════════════════════════════════════════════════════════════════════════

class ClipboardAdapter(ABC):
    """Interface for reading from and writing to the system clipboard."""

    @abstractmethod
    def read(self) -> str:
        """Returns the current clipboard contents as a string."""
        ...

    @abstractmethod
    def write(self, text: str) -> None:
        """Writes *text* to the clipboard."""
        ...


class WlClipboardAdapter(ClipboardAdapter):
    """Wayland clipboard via wl-clipboard (wl-paste / wl-copy)."""

    def read(self) -> str:
        result = _run(["wl-paste", "--no-newline"])
        if result.returncode != 0:
            logger.debug("wl-paste stderr: %s", result.stderr.strip())
        return result.stdout

    def write(self, text: str) -> None:
        result = _run(["wl-copy"], input_text=text)
        if result.returncode != 0:
            logger.error("wl-copy failed: %s", result.stderr.strip())


class XClipAdapter(ClipboardAdapter):
    """X11 clipboard via xclip."""

    def read(self) -> str:
        result = _run(["xclip", "-selection", "clipboard", "-o"])
        return result.stdout

    def write(self, text: str) -> None:
        result = _run(["xclip", "-selection", "clipboard"], input_text=text)
        if result.returncode != 0:
            logger.error("xclip write failed: %s", result.stderr.strip())


class XdoToolClipboardAdapter(ClipboardAdapter):
    """Fallback using xdotool / xsel for X11."""

    def read(self) -> str:
        result = _run(["xsel", "--clipboard", "--output"])
        return result.stdout

    def write(self, text: str) -> None:
        _run(["xsel", "--clipboard", "--input"], input_text=text)


# ══════════════════════════════════════════════════════════════════════════════
# UI / Confirmation Adapters
# ══════════════════════════════════════════════════════════════════════════════

class UIAdapter(ABC):
    """Interface for displaying a confirmation dialog to the user."""

    @abstractmethod
    def confirm(self, message: str, confirm_label: str, cancel_label: str) -> bool:
        """
        Shows a dialog with the given *message*.
        Returns True if the user confirmed, False if cancelled or dismissed.
        """
        ...


class WofiAdapter(UIAdapter):
    """Confirmation via wofi (Wayland application launcher)."""

    def confirm(self, message: str, confirm_label: str, cancel_label: str) -> bool:
        choices = f"{confirm_label}\n{cancel_label}"
        result = _run(
            ["wofi", "--dmenu", "--prompt", message, "--lines", "2"],
            input_text=choices,
        )
        return result.stdout.strip() == confirm_label


class RofiAdapter(UIAdapter):
    """Confirmation via rofi (X11/Wayland application launcher)."""

    def confirm(self, message: str, confirm_label: str, cancel_label: str) -> bool:
        choices = f"{confirm_label}\n{cancel_label}"
        result = _run(
            ["rofi", "-dmenu", "-p", message, "-lines", "2"],
            input_text=choices,
        )
        return result.stdout.strip() == confirm_label


class ZenityAdapter(UIAdapter):
    """Confirmation via zenity (GTK dialog)."""

    def confirm(self, message: str, confirm_label: str, cancel_label: str) -> bool:
        result = _run(
            [
                "zenity", "--question",
                "--text", message,
                "--ok-label", confirm_label,
                "--cancel-label", cancel_label,
                "--title", "clip-obsidian-ai",
            ]
        )
        return result.returncode == 0


class NullUIAdapter(UIAdapter):
    """No-op UI adapter — always confirms (useful for headless / scripted use)."""

    def confirm(self, message: str, confirm_label: str, cancel_label: str) -> bool:
        logger.info("NullUIAdapter: auto-confirming (no UI backend available).")
        return True


# ══════════════════════════════════════════════════════════════════════════════
# Notification Adapters
# ══════════════════════════════════════════════════════════════════════════════

class NotifierAdapter(ABC):
    """Interface for sending desktop notifications."""

    @abstractmethod
    def notify(self, title: str, body: str, urgency: str = "normal") -> None:
        """Sends a desktop notification."""
        ...


class NotifySendAdapter(NotifierAdapter):
    """Desktop notifications via notify-send (libnotify)."""

    def __init__(self, app_name: str = "clip-obsidian-ai", timeout_ms: int = 4000) -> None:
        self._app_name = app_name
        self._timeout_ms = timeout_ms

    def notify(self, title: str, body: str, urgency: str = "normal") -> None:
        _run(
            [
                "notify-send",
                "--app-name", self._app_name,
                "--urgency", urgency,
                "--expire-time", str(self._timeout_ms),
                title,
                body,
            ]
        )


class NullNotifierAdapter(NotifierAdapter):
    """No-op notifier — logs to console instead of sending notifications."""

    def notify(self, title: str, body: str, urgency: str = "normal") -> None:
        logger.info("[Notification] %s: %s", title, body)


# ══════════════════════════════════════════════════════════════════════════════
# LLM Adapters
# ══════════════════════════════════════════════════════════════════════════════

class LLMAdapter(ABC):
    """Interface for querying a language model."""

    @abstractmethod
    def generate(self, user_prompt: str, system_prompt: str = "") -> str:
        """
        Sends *user_prompt* to the LLM with an optional *system_prompt*.
        Returns the generated text as a string.
        """
        ...


class OllamaAdapter(LLMAdapter):
    """
    LLM adapter for Ollama (local inference server).

    Reads the format template dynamically on every call so users can
    hot-edit format.md without restarting the application.
    """

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        timeout: int = 120,
        format_file: Optional[Path] = None,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._timeout = timeout
        self._format_file = format_file

    # ── Public ────────────────────────────────────────────────────────────

    def generate(self, user_prompt: str, system_prompt: str = "") -> str:
        """
        Calls Ollama's /api/chat endpoint.
        If a format_file is configured, its contents override *system_prompt*.
        """
        effective_system = self._load_system_prompt(system_prompt)
        payload = self._build_payload(user_prompt, effective_system)

        logger.debug(
            "OllamaAdapter: POST %s/api/chat  model=%s  system=%d chars  user=%d chars",
            self._host,
            self._model,
            len(effective_system),
            len(user_prompt),
        )

        try:
            response_text = self._post_json(
                f"{self._host}/api/chat",
                payload,
                timeout=self._timeout,
            )
            return self._parse_response(response_text)

        except urllib.error.URLError as exc:
            raise ConnectionError(
                f"Cannot reach Ollama at {self._host}.  "
                f"Is 'ollama serve' running?  Details: {exc}"
            ) from exc

    def is_reachable(self) -> bool:
        """Quick health check against the Ollama root endpoint."""
        try:
            with urllib.request.urlopen(f"{self._host}/api/tags", timeout=3) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    # ── Private ───────────────────────────────────────────────────────────

    def _load_system_prompt(self, fallback: str) -> str:
        """
        Loads format.md from disk each time, enabling hot-reload.
        Falls back to the passed-in *fallback* string if file is unavailable.
        """
        if self._format_file and self._format_file.exists():
            try:
                return self._format_file.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read format.md: %s", exc)
        return fallback

    @staticmethod
    def _build_payload(user_prompt: str, system_prompt: str) -> dict:
        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        return {
            "model": "placeholder",  # overwritten below
            "messages": messages,
            "stream": False,
        }

    def _post_json(self, url: str, payload: dict, timeout: int) -> str:
        payload["model"] = self._model
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    @staticmethod
    def _parse_response(raw: str) -> str:
        try:
            obj = json.loads(raw)
            # /api/chat response shape: {"message": {"role": "assistant", "content": "..."}}
            return obj["message"]["content"].strip()
        except (json.JSONDecodeError, KeyError) as exc:
            raise ValueError(f"Unexpected Ollama response format: {exc}") from exc


# ══════════════════════════════════════════════════════════════════════════════
# Adapter Factory
# ══════════════════════════════════════════════════════════════════════════════

class AdapterFactory:
    """
    Auto-detects available system tools and returns the correct adapter
    instances based on the loaded AppConfig.
    """

    @staticmethod
    def build_clipboard(backend: str) -> ClipboardAdapter:
        if backend == "wl-clipboard" or (backend == "auto" and _has_cmd("wl-copy")):
            logger.debug("Clipboard backend: wl-clipboard")
            return WlClipboardAdapter()
        if backend == "xclip" or (backend == "auto" and _has_cmd("xclip")):
            logger.debug("Clipboard backend: xclip")
            return XClipAdapter()
        if _has_cmd("xsel"):
            logger.debug("Clipboard backend: xsel")
            return XdoToolClipboardAdapter()
        raise EnvironmentError(
            "No clipboard backend found. Install wl-clipboard (Wayland) or xclip (X11)."
        )

    @staticmethod
    def build_ui(backend: str, *, prompt: str, confirm: str, cancel: str) -> UIAdapter:
        if backend == "wofi" or (backend == "auto" and _has_cmd("wofi")):
            logger.debug("UI backend: wofi")
            return WofiAdapter()
        if backend == "rofi" or (backend == "auto" and _has_cmd("rofi")):
            logger.debug("UI backend: rofi")
            return RofiAdapter()
        if backend == "zenity" or (backend == "auto" and _has_cmd("zenity")):
            logger.debug("UI backend: zenity")
            return ZenityAdapter()
        logger.warning(
            "No UI backend found (wofi/rofi/zenity). Running in headless mode."
        )
        return NullUIAdapter()

    @staticmethod
    def build_notifier(
        enabled: bool, backend: str, app_name: str, timeout_ms: int
    ) -> NotifierAdapter:
        if not enabled:
            return NullNotifierAdapter()
        if backend == "notify-send" and _has_cmd("notify-send"):
            logger.debug("Notifier backend: notify-send")
            return NotifySendAdapter(app_name=app_name, timeout_ms=timeout_ms)
        logger.debug("Notifier backend: null (notify-send not found)")
        return NullNotifierAdapter()

    @staticmethod
    def build_llm(
        provider: str,
        model: str,
        host: str,
        timeout: int,
        format_file: Optional[Path] = None,
    ) -> LLMAdapter:
        if provider == "ollama":
            logger.debug("LLM backend: Ollama  model=%s  host=%s", model, host)
            return OllamaAdapter(
                model=model,
                host=host,
                timeout=timeout,
                format_file=format_file,
            )
        raise ValueError(f"Unknown LLM provider: '{provider}'. Only 'ollama' is supported.")
