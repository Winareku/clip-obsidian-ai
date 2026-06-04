#!/usr/bin/env python3
"""
main.py
-------
clip-obsidian-ai — Entry point.

Usage:
  python main.py --mode clip          # Process clipboard text with AI
  python main.py --mode dir           # Process all docs in current directory
  python main.py --mode dir --dir /path/to/docs   # Process specific directory
  python main.py --mode clip --model mistral       # Override model from config
  python main.py --check              # Check system dependencies

Run `python main.py --help` for full usage.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


# ── Logging setup (must happen before importing local modules) ───────────────

def _configure_logging(level_str: str, show_timestamps: bool) -> None:
    level = getattr(logging, level_str.upper(), logging.INFO)
    fmt = (
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        if show_timestamps
        else "[%(levelname)s] %(name)s: %(message)s"
    )
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)


# ── Argument parser ──────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clip-obsidian-ai",
        description=(
            "AI-powered note assistant for Obsidian.\n"
            "Processes clipboard text or directory documents through a local LLM."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --mode clip                   # Process current clipboard
  %(prog)s --mode dir                    # Process docs in current directory
  %(prog)s --mode dir --dir ~/Documents  # Process a specific directory
  %(prog)s --mode clip --model gemma2    # Use a specific Ollama model
  %(prog)s --check                       # Verify system dependencies
  %(prog)s --edit-config                 # Open config in $EDITOR
  %(prog)s --edit-format                 # Open format template in $EDITOR
        """,
    )

    # ── Primary mode ──────────────────────────────────────────────────────
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--mode",
        choices=["clip", "dir"],
        metavar="MODE",
        help="Execution mode: 'clip' (clipboard) or 'dir' (directory scan).",
    )
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Check system dependencies and exit.",
    )
    mode_group.add_argument(
        "--edit-config",
        action="store_true",
        help="Open config.yaml in $EDITOR and exit.",
    )
    mode_group.add_argument(
        "--edit-format",
        action="store_true",
        help="Open format.md in $EDITOR and exit.",
    )

    # ── Dir mode options ──────────────────────────────────────────────────
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        metavar="PATH",
        help="Directory to scan (--mode dir only). Defaults to current directory.",
    )

    # ── Config overrides ──────────────────────────────────────────────────
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="MODEL",
        help="Override the Ollama model from config (e.g. mistral, gemma2).",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        metavar="LEVEL",
        help="Override log level from config.",
    )

    return parser


# ── Sub-commands ─────────────────────────────────────────────────────────────

def _cmd_check() -> int:
    """Prints a dependency report and returns 0 if all critical deps are met."""
    import shutil

    print("\n🔍 clip-obsidian-ai — System Dependency Check\n")

    checks: list[tuple[str, str, bool, bool]] = [
        # (name, command, required, found)
        ("Ollama",        "ollama",         True,  bool(shutil.which("ollama"))),
        ("wl-copy",       "wl-copy",        False, bool(shutil.which("wl-copy"))),
        ("xclip",         "xclip",          False, bool(shutil.which("xclip"))),
        ("xsel",          "xsel",           False, bool(shutil.which("xsel"))),
        ("wofi",          "wofi",           False, bool(shutil.which("wofi"))),
        ("rofi",          "rofi",           False, bool(shutil.which("rofi"))),
        ("zenity",        "zenity",         False, bool(shutil.which("zenity"))),
        ("notify-send",   "notify-send",    False, bool(shutil.which("notify-send"))),
    ]

    all_ok = True
    for name, cmd, required, found in checks:
        tag = "✅" if found else ("❌ (required)" if required else "⚠  (optional)")
        print(f"  {tag}  {name:<20} [{cmd}]")
        if required and not found:
            all_ok = False

    # Python packages
    print()
    py_deps = [
        ("pdfplumber",   "pdfplumber",   False),
        ("pypdf",        "pypdf",        False),
        ("python-pptx",  "pptx",         False),
        ("python-docx",  "docx",         False),
        ("PyYAML",       "yaml",         True),
    ]
    for pkg_name, import_name, required in py_deps:
        try:
            __import__(import_name)
            print(f"  ✅  {pkg_name:<20} [pip]")
        except ImportError:
            tag = "❌ (required)" if required else "⚠  (optional)"
            print(f"  {tag}  {pkg_name:<20} [pip install {pkg_name}]")
            if required:
                all_ok = False

    print()
    if all_ok:
        print("  ✅  All required dependencies satisfied.\n")
    else:
        print("  ❌  Some required dependencies are missing. See above.\n")

    return 0 if all_ok else 1


def _cmd_edit_file(file_path: Path) -> int:
    """Opens *file_path* in $EDITOR (or nano as fallback)."""
    import os
    import subprocess

    editor = os.environ.get("EDITOR", "nano")
    try:
        subprocess.run([editor, str(file_path)], check=True)
        return 0
    except FileNotFoundError:
        print(f"Editor '{editor}' not found. Edit manually: {file_path}")
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Editor exited with error: {exc}")
        return exc.returncode


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # Load config first (needed for logging config)
    from config_manager import load_config
    config = load_config()

    # Apply log-level override
    log_level = args.log_level or config.logging.level
    _configure_logging(log_level, config.logging.show_timestamps)

    logger = logging.getLogger(__name__)
    logger.debug("clip-obsidian-ai starting up.  Args: %s", vars(args))

    # ── Apply CLI overrides to config ────────────────────────────────────
    if args.model:
        config.llm.model = args.model
        logger.info("Model overridden via CLI: %s", args.model)

    # ── Route to sub-commands ────────────────────────────────────────────

    if args.check:
        return _cmd_check()

    if args.edit_config:
        from config_manager import USER_CONFIG_FILE
        print(f"Opening: {USER_CONFIG_FILE}")
        return _cmd_edit_file(USER_CONFIG_FILE)

    if args.edit_format:
        from config_manager import USER_FORMAT_FILE
        print(f"Opening: {USER_FORMAT_FILE}")
        return _cmd_edit_file(USER_FORMAT_FILE)

    # ── Mode routing ──────────────────────────────────────────────────────

    if args.mode is None:
        parser.print_help()
        print("\nError: --mode is required. Use --mode clip or --mode dir.\n")
        return 1

    if args.mode == "clip":
        from modes.clip_mode import run_clip_mode
        return run_clip_mode(config)

    if args.mode == "dir":
        target = args.dir
        if target is not None and not target.is_dir():
            print(f"Error: '{target}' is not a valid directory.")
            return 1
        from modes.dir_mode import run_dir_mode
        return run_dir_mode(config, target_dir=target)

    # Should never reach here (argparse catches invalid choices)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
