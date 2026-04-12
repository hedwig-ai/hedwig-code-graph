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

def human_ok(msg: str) -> None:
    """Print a success line for human-facing commands."""
    click.echo(f"  + {msg}")


def human_skip(msg: str) -> None:
    """Print a skip/already-exists line for human-facing commands."""
    click.echo(f"  - {msg}")


def human_warn(msg: str) -> None:
    """Print a warning line for human-facing commands."""
    click.echo(f"  ! {msg}")


def human_fail(msg: str) -> None:
    """Print a failure line for human-facing commands."""
    click.echo(f"  x {msg}")


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
