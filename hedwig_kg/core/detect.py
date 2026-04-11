"""File detection and classification module.

Scans directories, classifies files by type, and respects ignore patterns.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

# Supported languages mapped to file extensions
LANGUAGE_MAP: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".mjs"],
    "typescript": [".ts", ".tsx"],
    "java": [".java"],
    "go": [".go"],
    "rust": [".rs"],
    "c": [".c", ".h"],
    "cpp": [".cpp", ".hpp", ".cc", ".cxx"],
    "ruby": [".rb"],
    "php": [".php"],
    "swift": [".swift"],
    "kotlin": [".kt", ".kts"],
    "scala": [".scala"],
    "shell": [".sh", ".bash", ".zsh"],
    "lua": [".lua"],
    "r": [".r", ".R"],
    "markdown": [".md", ".mdx"],
    "yaml": [".yml", ".yaml"],
    "json": [".json"],
    "toml": [".toml"],
    "pdf": [".pdf"],
    "html": [".html", ".htm"],
    "csv": [".csv", ".tsv"],
}

EXT_TO_LANG: dict[str, str] = {}
for lang, exts in LANGUAGE_MAP.items():
    for ext in exts:
        EXT_TO_LANG[ext] = lang

DEFAULT_IGNORE = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".eggs", "*.egg-info", ".DS_Store",
}

SENSITIVE_PATTERNS = {
    "*.env", "*.pem", "*.key", "*.secret", "*credentials*",
    "*password*", "*.p12", "*.pfx",
}


@dataclass
class DetectedFile:
    path: Path
    language: str
    file_type: str  # "code", "config", "doc"
    size_bytes: int = 0


@dataclass
class DetectResult:
    files: list[DetectedFile] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    root: Path = field(default_factory=lambda: Path("."))


def _is_ignored(path: Path, ignore_patterns: set[str]) -> bool:
    name = path.name
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    for pattern in SENSITIVE_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _classify_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in EXT_TO_LANG:
        return "code"
    if ext in {".md", ".mdx", ".rst", ".txt"}:
        return "doc"
    if ext in {".pdf", ".html", ".htm", ".csv", ".tsv"}:
        return "doc"
    if ext in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}:
        return "config"
    return "other"


def detect(
    root: Path,
    ignore_patterns: set[str] | None = None,
    max_file_size: int = 1_000_000,  # 1MB default
) -> DetectResult:
    """Scan directory tree and classify files.

    Args:
        root: Root directory to scan.
        ignore_patterns: Additional glob patterns to ignore.
        max_file_size: Skip files larger than this (bytes).

    Returns:
        DetectResult with classified files and skip reasons.
    """
    root = Path(root).resolve()
    patterns = DEFAULT_IGNORE | (ignore_patterns or set())
    result = DetectResult(root=root)

    # Load ignore file if present
    ignore_file = root / ".hedwig-kg-ignore"
    if ignore_file.exists():
        for line in ignore_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.add(line)

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        # Check ignore patterns against all parent dirs
        if any(_is_ignored(p, patterns) for p in [path] + list(path.relative_to(root).parents)):
            result.skipped.append(f"ignored: {path}")
            continue

        if _is_sensitive(path):
            result.skipped.append(f"sensitive: {path}")
            continue

        try:
            size = path.stat().st_size
        except OSError:
            result.skipped.append(f"unreadable: {path}")
            continue

        if size > max_file_size:
            result.skipped.append(f"too_large ({size}B): {path}")
            continue

        if size == 0:
            result.skipped.append(f"empty: {path}")
            continue

        ext = path.suffix.lower()
        lang = EXT_TO_LANG.get(ext, "unknown")
        file_type = _classify_file(path)

        if file_type == "other":
            result.skipped.append(f"unsupported: {path}")
            continue

        result.files.append(DetectedFile(
            path=path,
            language=lang,
            file_type=file_type,
            size_bytes=size,
        ))

    return result
