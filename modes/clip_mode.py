"""
modes/clip_mode.py
------------------
Orchestrates the --mode clip flow:

  1. Read text from clipboard
  2. Show a preview / confirmation dialog (wofi / rofi / zenity)
  3. Send the text to the LLM
  4. Write the formatted result back to the clipboard
  5. Notify the user
"""

from __future__ import annotations

import logging

from adapters import (
    AdapterFactory,
    ClipboardAdapter,
    LLMAdapter,
    NotifierAdapter,
    UIAdapter,
)
from config_manager import AppConfig

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class ClipMode:
    """
    Encapsulates all business logic for the clipboard-processing mode.
    Dependencies are injected so they can be swapped / mocked in tests.
    """

    def __init__(
        self,
        config: AppConfig,
        clipboard: ClipboardAdapter,
        ui: UIAdapter,
        llm: LLMAdapter,
        notifier: NotifierAdapter,
    ) -> None:
        self._config = config
        self._clipboard = clipboard
        self._ui = ui
        self._llm = llm
        self._notifier = notifier

    # ── Public entry point ────────────────────────────────────────────────

    def run(self) -> int:
        """
        Executes the full clip flow.
        Returns 0 on success, 1 on user cancellation, 2+ on error.
        """
        # ── Step 1: Read clipboard ────────────────────────────────────────
        raw_text = self._clipboard.read()
        if not raw_text.strip():
            logger.warning("Clipboard is empty. Nothing to process.")
            self._notifier.notify(
                "clip-obsidian-ai",
                "El portapapeles está vacío.",
                urgency="low",
            )
            return 1

        logger.info("Clipboard content read: %d characters.", len(raw_text))

        # ── Step 2: Build preview & ask for confirmation ──────────────────
        preview = self._build_preview(raw_text)
        confirmed = self._ui.confirm(
            message=f"{self._config.ui.prompt_message}\n\n{preview}",
            confirm_label=self._config.ui.confirm_label,
            cancel_label=self._config.ui.cancel_label,
        )

        if not confirmed:
            logger.info("User cancelled the operation.")
            return 1

        # ── Step 3: Truncate input if needed ─────────────────────────────
        truncated = self._maybe_truncate(raw_text)

        # ── Step 4: Send to LLM ──────────────────────────────────────────
        logger.info("Sending text to LLM (%s)…", self._config.llm.model)
        self._notifier.notify(
            "clip-obsidian-ai ⏳",
            f"Procesando con {self._config.llm.model}…",
            urgency="low",
        )

        try:
            formatted = self._llm.generate(user_prompt=truncated)
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM request failed: %s", exc)
            self._notifier.notify(
                "clip-obsidian-ai ❌",
                f"Error al contactar el LLM:\n{exc}",
                urgency="critical",
            )
            return 2

        if not formatted.strip():
            logger.error("LLM returned an empty response.")
            self._notifier.notify(
                "clip-obsidian-ai ❌",
                "El LLM devolvió una respuesta vacía.",
                urgency="critical",
            )
            return 2

        # ── Step 5: Write result to clipboard ────────────────────────────
        self._clipboard.write(formatted)
        logger.info("Formatted text written to clipboard (%d chars).", len(formatted))

        # ── Step 6: Notify success ───────────────────────────────────────
        self._notifier.notify(
            "clip-obsidian-ai ✅",
            "¡Texto formateado en el portapapeles!",
            urgency="normal",
        )
        return 0

    # ── Helpers ───────────────────────────────────────────────────────────

    def _build_preview(self, text: str) -> str:
        """Returns a short excerpt of the clipboard text for the UI dialog."""
        max_chars = self._config.ui.preview_chars
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + f"… [{len(text) - max_chars} chars more]"

    def _maybe_truncate(self, text: str) -> str:
        """Truncates the input to max_input_chars to respect context limits."""
        limit = self._config.llm.max_input_chars
        if len(text) > limit:
            logger.warning(
                "Input text truncated from %d to %d chars (LLM context limit).",
                len(text),
                limit,
            )
            return text[:limit]
        return text


# ── Factory function ──────────────────────────────────────────────────────────

def run_clip_mode(config: AppConfig) -> int:
    """
    Convenience function: builds all adapters from config and runs clip mode.
    Called directly from main.py.
    """
    clipboard = AdapterFactory.build_clipboard(config.clipboard.backend)
    ui = AdapterFactory.build_ui(
        config.ui.backend,
        prompt=config.ui.prompt_message,
        confirm=config.ui.confirm_label,
        cancel=config.ui.cancel_label,
    )
    llm = AdapterFactory.build_resilient_llm(config)
    notifier = AdapterFactory.build_notifier(
        enabled=config.notifications.enabled,
        backend=config.notifications.backend,
        app_name=config.notifications.app_name,
        timeout_ms=config.notifications.timeout_ms,
    )

    orchestrator = ClipMode(
        config=config,
        clipboard=clipboard,
        ui=ui,
        llm=llm,
        notifier=notifier,
    )
    return orchestrator.run()
