"""
modes/dir_mode.py
-----------------
Orchestrates the --mode dir flow:

  1. Scan the current working directory for supported document files
  2. Extract plain text from each file using the ExtractorFactory
  3. Concatenate all extracted texts (with per-file headers)
  4. Send the combined text to the LLM
  5. Write the result to `notas_generadas.md` in the same directory
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from adapters import AdapterFactory, LLMAdapter
from config_manager import AppConfig
from extractors import ExtractorFactory

logger = logging.getLogger(__name__)

# ── Console formatting helpers ────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
DIM    = "\033[2m"


def _print_header(title: str) -> None:
    width = 60
    print(f"\n{BOLD}{CYAN}{'─' * width}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * width}{RESET}")


def _print_file_status(index: int, total: int, path: Path, chars: int, ok: bool) -> None:
    icon = f"{GREEN}✔{RESET}" if ok else f"{RED}✘{RESET}"
    status = f"{chars:>6} chars" if ok else "  FAILED"
    print(
        f"  {icon} [{index:>2}/{total}] {BOLD}{path.name:<40}{RESET} "
        f"{DIM}{status}{RESET}"
    )


def _print_separator() -> None:
    print(f"{DIM}{'·' * 60}{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════════════

class DirMode:
    """
    Encapsulates all business logic for the directory-scanning mode.
    """

    def __init__(self, config: AppConfig, llm: LLMAdapter) -> None:
        self._config = config
        self._llm = llm

    # ── Public entry point ────────────────────────────────────────────────

    def run(self, target_dir: Optional[Path] = None) -> int:
        """
        Executes the full dir-mode flow.
        Returns 0 on success, 1 if no files were found, 2+ on error.
        """
        cwd = target_dir or Path.cwd()
        _print_header(f"clip-obsidian-ai  │  dir mode  │  {cwd}")

        # ── Step 1: Discover files ────────────────────────────────────────
        supported = set(self._config.dir_mode.supported_extensions)
        files = self._discover_files(cwd, supported)

        if not files:
            print(f"\n{YELLOW}⚠  No se encontraron archivos soportados en:{RESET}")
            print(f"   {cwd}")
            print(f"\n   Extensiones soportadas: {', '.join(sorted(supported))}\n")
            return 1

        print(f"\n{BOLD}Archivos encontrados: {len(files)}{RESET}\n")

        # ── Step 2: Extract text from each file ───────────────────────────
        blocks: list[str] = []
        failed: list[Path] = []

        for idx, file_path in enumerate(files, start=1):
            text = ExtractorFactory.extract(str(file_path))
            ok = bool(text.strip())

            _print_file_status(idx, len(files), file_path, len(text), ok)

            if ok:
                header = f"# Fuente: {file_path.name}\n"
                blocks.append(header + text)
            else:
                failed.append(file_path)

        _print_separator()

        if not blocks:
            print(f"\n{RED}✘  No se pudo extraer texto de ningún archivo.{RESET}\n")
            return 2

        if failed:
            print(
                f"\n{YELLOW}⚠  {len(failed)} archivo(s) fallaron y fueron omitidos:{RESET}"
            )
            for f in failed:
                print(f"   - {f.name}")

        # ── Step 3: Concatenate ───────────────────────────────────────────
        separator = self._config.dir_mode.file_separator
        combined = separator.join(blocks)

        # Respect LLM context limit
        combined = self._maybe_truncate(combined)

        print(f"\n{BOLD}Texto total extraído: {len(combined):,} caracteres{RESET}")

        # ── Step 4: Send to LLM ──────────────────────────────────────────
        print(f"\n{BOLD}⏳ Enviando al LLM ({self._config.llm.model})…{RESET}")
        sys.stdout.flush()

        try:
            result = self._llm.generate(user_prompt=combined)
        except Exception as exc:  # noqa: BLE001
            print(f"\n{RED}✘ Error al contactar el LLM:{RESET}\n   {exc}\n")
            logger.error("LLM request failed: %s", exc)
            return 2

        if not result.strip():
            print(f"\n{RED}✘ El LLM devolvió una respuesta vacía.{RESET}\n")
            return 2

        # ── Step 5: Write output file ─────────────────────────────────────
        output_path = cwd / self._config.dir_mode.output_filename
        self._write_output(output_path, result, files)

        print(f"\n{GREEN}{BOLD}✅ Notas generadas:{RESET}")
        print(f"   {output_path}\n")
        return 0

    # ── Helpers ───────────────────────────────────────────────────────────

    def _discover_files(self, directory: Path, extensions: set[str]) -> list[Path]:
        """
        Returns a sorted list of files in *directory* matching *extensions*.
        If config.dir_mode.recursive is True, searches subdirectories too.
        Excludes the output file itself to avoid circular processing.
        """
        output_name = self._config.dir_mode.output_filename
        glob_fn = directory.rglob if self._config.dir_mode.recursive else directory.glob

        found: list[Path] = []
        for ext in extensions:
            pattern = f"**/*{ext}" if self._config.dir_mode.recursive else f"*{ext}"
            for p in glob_fn(pattern):
                if p.is_file() and p.name != output_name:
                    found.append(p)

        # De-duplicate (rglob can return duplicates) and sort
        return sorted(set(found))

    def _maybe_truncate(self, text: str) -> str:
        limit = self._config.llm.max_input_chars
        if len(text) > limit:
            logger.warning(
                "Combined text truncated from %d to %d chars (LLM context limit).",
                len(text),
                limit,
            )
            print(
                f"\n{YELLOW}⚠  Texto truncado a {limit:,} chars para respetar el "
                f"límite de contexto del LLM.{RESET}"
            )
            return text[:limit]
        return text

    @staticmethod
    def _write_output(output_path: Path, content: str, source_files: list[Path]) -> None:
        """Writes the LLM result with a metadata header to *output_path*."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sources_list = "\n".join(f"- [[{f.name}]]" for f in source_files)

        header = (
            f"---\n"
            f"generado: {timestamp}\n"
            f"herramienta: clip-obsidian-ai\n"
            f"fuentes:\n"
            + "\n".join(f"  - {f.name}" for f in source_files)
            + f"\n---\n\n"
            f"# Notas Generadas\n\n"
            f"> Generado automáticamente por **clip-obsidian-ai** el {timestamp}.\n\n"
            f"## Archivos Procesados\n\n"
            f"{sources_list}\n\n"
            f"---\n\n"
        )

        output_path.write_text(header + content, encoding="utf-8")


# ── Factory function ──────────────────────────────────────────────────────────

def run_dir_mode(config: AppConfig, target_dir: Optional[Path] = None) -> int:
    """
    Convenience function: builds all adapters from config and runs dir mode.
    Called directly from main.py.
    """
    llm = AdapterFactory.build_resilient_llm(config)
    orchestrator = DirMode(config=config, llm=llm)
    return orchestrator.run(target_dir=target_dir)
