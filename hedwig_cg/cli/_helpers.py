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


def human_choose(
    prompt: str,
    choices: list[str],
    descriptions: list[str] | None = None,
    default: int = 1,
) -> str:
    """Show an interactive arrow-key menu and return the chosen value.

    Falls back to numbered input if terminal doesn't support raw mode.
    """
    import sys

    selected = default - 1  # 0-based

    def _render(sel: int, clear: bool = False) -> None:
        """Render the menu. If clear=True, move cursor up and overwrite."""
        if clear:
            # Move up len(choices) lines and clear each
            sys.stdout.write(f"\033[{len(choices)}A")
        for i, choice in enumerate(choices):
            desc = f"  {_DIM}{descriptions[i]}{_RESET}" if descriptions else ""
            if i == sel:
                line = f"  {_GREEN}{_BOLD}> {choice}{_RESET}{desc}"
            else:
                line = f"    {_DIM}{choice}{_RESET}{desc}"
            sys.stdout.write(f"\033[2K{line}\n")
        sys.stdout.flush()

    # Try interactive mode (Unix only, needs tty)
    try:
        import termios
        import tty

        if not sys.stdin.isatty():
            raise OSError("not a tty")

        click.echo(f"{prompt}  {_DIM}(↑↓ to select, Enter to confirm){_RESET}\n")
        _render(selected)

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                ch = sys.stdin.read(1)
                if ch == "\r" or ch == "\n":
                    break
                if ch == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt
                if ch == "\x1b":  # Escape sequence
                    seq = sys.stdin.read(2)
                    if seq == "[A":  # Up arrow
                        selected = (selected - 1) % len(choices)
                    elif seq == "[B":  # Down arrow
                        selected = (selected + 1) % len(choices)
                    _render(selected, clear=True)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        click.echo()  # newline after selection
        return choices[selected]

    except (ImportError, OSError):
        # Fallback: numbered input (Windows or non-tty)
        click.echo(f"{prompt}\n")
        for i, choice in enumerate(choices, 1):
            desc = f"  {_DIM}{descriptions[i - 1]}{_RESET}" if descriptions else ""
            marker = f"{_BOLD}>{_RESET}" if i == default else " "
            click.echo(f"  {marker} {i}) {choice}{desc}")
        click.echo()
        valid = [str(i) for i in range(1, len(choices) + 1)] + choices
        while True:
            raw = click.prompt(
                f"Choose [1-{len(choices)}]",
                type=click.Choice(valid, case_sensitive=False),
                default=str(default),
                show_choices=False,
            )
            try:
                idx = int(raw)
                return choices[idx - 1]
            except ValueError:
                return raw.lower()


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
