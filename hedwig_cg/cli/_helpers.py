"""Shared CLI helpers for hedwig-cg."""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

import click


def suppress_library_logs():
    """Suppress noisy library logs."""
    warnings.filterwarnings("ignore")
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["TQDM_DISABLE"] = "1"
    for name in [
        "sentence_transformers", "transformers", "torch", "huggingface_hub",
        "filelock", "urllib3", "tqdm", "fsspec",
    ]:
        logging.getLogger(name).setLevel(logging.CRITICAL)


# --- JSON output (for agent-facing commands) ---

def json_out(data) -> None:
    """Print JSON to stdout (no Rich formatting)."""
    import json
    click.echo(json.dumps(data, separators=(",", ":"), default=str))


def json_error(message: str) -> None:
    """Print error as JSON and exit with code 1."""
    import json
    click.echo(json.dumps({"error": message}))
    raise SystemExit(1)


# --- Human-friendly output (for install/uninstall/doctor/clean) ---

_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def human_ok(msg: str) -> None:
    """Print a success line for human-facing commands."""
    click.echo(f"  {_GREEN}+{_RESET} {msg}")


def human_skip(msg: str) -> None:
    """Print a skip/already-exists line for human-facing commands."""
    click.echo(f"  {_DIM}-{_RESET} {_DIM}{msg}{_RESET}")


def human_warn(msg: str) -> None:
    """Print a warning line for human-facing commands."""
    click.echo(f"  {_YELLOW}!{_RESET} {msg}")


def human_fail(msg: str) -> None:
    """Print a failure line for human-facing commands."""
    click.echo(f"  {_RED}x{_RESET} {msg}")


def human_header(title: str) -> None:
    """Print a section header."""
    click.echo(f"\n{_BOLD}{title}{_RESET}\n")


def human_done(msg: str = "Done!") -> None:
    """Print a completion message."""
    click.echo(f"\n{_GREEN}{msg}{_RESET}")


def human_choose(prompt: str, choices: list[str], default: int = 1) -> str:
    """Show a numbered menu and return the chosen value.

    Args:
        prompt: Question text.
        choices: List of options.
        default: 1-based default choice.
    """
    click.echo(f"{prompt}\n")
    for i, choice in enumerate(choices, 1):
        marker = f"{_BOLD}>{_RESET}" if i == default else " "
        click.echo(f"  {marker} {i}) {choice}")
    click.echo()
    while True:
        raw = click.prompt(
            f"Choose [1-{len(choices)}]",
            default=str(default),
        )
        try:
            idx = int(raw)
            if 1 <= idx <= len(choices):
                return choices[idx - 1]
        except ValueError:
            pass
        click.echo(f"  Please enter a number between 1 and {len(choices)}.")


# --- Utilities ---

def resolve_db(db: str | None, source_dir: str) -> Path | None:
    """Find the knowledge database."""
    if db:
        p = Path(db)
        return p if p.exists() else None
    default = Path(source_dir).resolve() / ".hedwig-cg" / "knowledge.db"
    if default.exists():
        return default
    return None


def auto_rebuild_command() -> str:
    """Return the shell command for auto-rebuild on session stop."""
    script = Path(__file__).parent.parent / "scripts" / "auto_rebuild.sh"
    return f"sh {script}"
