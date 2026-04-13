"""Git co-change extraction — mines evolutionary coupling from VCS history.

Analyzes git log to find files that are frequently changed together (co-committed),
producing co_change edges that complement static analysis relationships.

Based on: Zimmermann et al. (2005) "Mining version histories to guide software changes"
and Tornhill (2015) "Your Code as a Crime Scene".
"""

from __future__ import annotations

import logging
import math
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import networkx as nx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CommitInfo:
    """Parsed commit from git log."""

    hash: str
    timestamp: int  # Unix epoch
    message: str
    files: list[str] = field(default_factory=list)


@dataclass
class CoChangeEdge:
    """A co-change relationship between two files."""

    source: str  # module node ID
    target: str  # module node ID
    co_change_count: int  # raw co-commit count
    strength: float  # normalized [0, 1]
    recency: float  # time-decayed score [0, 1]
    confidence: str  # EXTRACTED | INFERRED
    sample_messages: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Git log parsing
# ---------------------------------------------------------------------------

_COMMIT_SEP = "---HEDWIG_COMMIT---"
_LOG_FORMAT = f"{_COMMIT_SEP}%n%H%n%at%n%s"


def _is_git_repo(source_dir: Path) -> bool:
    """Check if directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(source_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _get_git_root(source_dir: Path) -> Path | None:
    """Get the git repository root directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(source_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def parse_git_log(
    source_dir: Path,
    *,
    max_commits: int = 0,
    since: str | None = None,
) -> list[CommitInfo]:
    """Parse git log into structured commit data with rename tracking.

    Args:
        source_dir: Directory inside the git repo.
        max_commits: Maximum number of commits to process (0 = all history).
        since: Git date filter (e.g. "2 years ago"). Defaults to None (all history).

    Returns:
        List of CommitInfo with resolved file paths.
    """
    cmd = [
        "git", "log",
        f"--pretty=format:{_LOG_FORMAT}",
        "--name-status",
        "--no-merges",
        "--diff-filter=ACMR",
        "-M50%",  # detect renames with 50% similarity
    ]
    if max_commits > 0:
        cmd.append(f"-n{max_commits}")
    if since:
        cmd.append(f"--since={since}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(source_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning("git log failed: %s", result.stderr.strip())
            return []
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning("git log error: %s", e)
        return []

    return _parse_log_output(result.stdout)


def _parse_log_output(output: str) -> list[CommitInfo]:
    """Parse raw git log output into CommitInfo objects."""
    commits: list[CommitInfo] = []
    # rename map: old_path -> current_path
    rename_map: dict[str, str] = {}

    blocks = output.split(_COMMIT_SEP)
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.splitlines()
        if len(lines) < 3:
            continue

        commit_hash = lines[0].strip()
        try:
            timestamp = int(lines[1].strip())
        except ValueError:
            continue
        message = lines[2].strip()

        files: list[str] = []
        for line in lines[3:]:
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) >= 2:
                status = parts[0]
                if status.startswith("R"):
                    # Rename: R100\told_path\tnew_path
                    if len(parts) >= 3:
                        old_path = parts[1]
                        new_path = parts[2]
                        rename_map[old_path] = new_path
                        files.append(new_path)
                else:
                    # A, C, M — regular file change
                    files.append(parts[1])

        if files:
            commits.append(CommitInfo(
                hash=commit_hash,
                timestamp=timestamp,
                message=message,
                files=files,
            ))

    # Resolve rename chains: apply all renames to normalize paths
    _resolve_renames(commits, rename_map)
    return commits


def _resolve_renames(
    commits: list[CommitInfo], rename_map: dict[str, str],
) -> None:
    """Canonicalize file paths using rename history.

    Applies rename chains so all paths refer to their current name.
    """
    if not rename_map:
        return

    # Build transitive rename chain: old1 -> old2 -> current => old1 -> current
    resolved: dict[str, str] = {}
    for old, new in rename_map.items():
        current = new
        visited: set[str] = {old, new}
        while current in rename_map and rename_map[current] not in visited:
            current = rename_map[current]
            visited.add(current)
        resolved[old] = current

    # Apply resolved renames to all commits
    for commit in commits:
        commit.files = [resolved.get(f, f) for f in commit.files]


# ---------------------------------------------------------------------------
# Co-change computation
# ---------------------------------------------------------------------------


def compute_cochange_pairs(
    commits: list[CommitInfo],
    source_dir: Path,
    *,
    max_files_per_commit: int = 30,
    min_support: int = 3,
    min_confidence: float = 0.3,
    decay_half_life_days: int = 180,
    max_sample_messages: int = 10,
) -> list[CoChangeEdge]:
    """Compute co-change relationships from commit history.

    Args:
        commits: Parsed commit data.
        source_dir: Root directory for relativizing paths.
        max_files_per_commit: Skip commits touching more files (bulk refactors).
        min_support: Minimum co-commit count to keep an edge.
        min_confidence: Minimum confidence score to keep an edge.
        decay_half_life_days: Half-life for time-decay weighting (days).
        max_sample_messages: Max commit messages to store per edge.

    Returns:
        List of CoChangeEdge with computed metrics.
    """
    if not commits:
        return []

    now = max(c.timestamp for c in commits)
    decay_lambda = math.log(2) / (decay_half_life_days * 86400)  # per-second

    # Count per-file commits and per-pair co-commits
    file_commits: defaultdict[str, int] = defaultdict(int)
    pair_count: defaultdict[tuple[str, str], int] = defaultdict(int)
    pair_decay_sum: defaultdict[tuple[str, str], float] = defaultdict(float)
    pair_messages: defaultdict[tuple[str, str], list[str]] = defaultdict(list)

    git_root = _get_git_root(source_dir)
    source_resolved = source_dir.resolve()

    for commit in commits:
        # Filter to files within source_dir and apply fanout cap
        relevant_files: list[str] = []
        for f in commit.files:
            # Relativize to source_dir
            if git_root:
                abs_path = git_root / f
            else:
                abs_path = source_resolved / f
            try:
                rel_path = abs_path.relative_to(source_resolved)
                relevant_files.append(str(rel_path))
            except ValueError:
                continue  # file is outside source_dir

        if len(relevant_files) > max_files_per_commit or len(relevant_files) < 2:
            continue

        # Time-decay weight for this commit
        age_seconds = max(0, now - commit.timestamp)
        decay_weight = math.exp(-decay_lambda * age_seconds)

        # Count file appearances
        for f in relevant_files:
            file_commits[f] += 1

        # Count co-change pairs (sorted tuple for consistency)
        for a, b in combinations(sorted(relevant_files), 2):
            pair = (a, b)
            pair_count[pair] += 1
            pair_decay_sum[pair] += decay_weight
            if len(pair_messages[pair]) < max_sample_messages:
                pair_messages[pair].append(commit.message)

    # Compute metrics and filter
    edges: list[CoChangeEdge] = []
    for (file_a, file_b), count in pair_count.items():
        if count < min_support:
            continue

        # Normalized strength: Jaccard-like (Zimmermann et al.)
        denom = math.sqrt(file_commits[file_a] * file_commits[file_b])
        strength = count / denom if denom > 0 else 0.0

        # Time-decayed recency score (normalize by count)
        recency = pair_decay_sum[(file_a, file_b)] / count if count > 0 else 0.0

        # Confidence level
        if count >= 5 and strength >= 0.5:
            confidence = "EXTRACTED"
        elif count >= min_support and strength >= min_confidence:
            confidence = "INFERRED"
        else:
            continue  # below threshold

        # Build module node IDs (matching _make_node_id convention)
        src_id = _file_to_module_id(file_a)
        tgt_id = _file_to_module_id(file_b)

        edges.append(CoChangeEdge(
            source=src_id,
            target=tgt_id,
            co_change_count=count,
            strength=round(strength, 4),
            recency=round(recency, 4),
            confidence=confidence,
            sample_messages=pair_messages[(file_a, file_b)],
        ))

    edges.sort(key=lambda e: e.strength, reverse=True)
    return edges


def _file_to_module_id(rel_path: str) -> str:
    """Convert a relative file path to a module node ID.

    Used internally by compute_cochange_pairs to create identifiers.
    These IDs use relative paths and are resolved to actual graph node IDs
    by enrich_graph_with_cochange via _build_file_to_node_index.
    """
    p = Path(rel_path)
    return f"{rel_path}::module::{p.stem}"


def _build_file_to_node_index(G: nx.DiGraph) -> dict[str, str]:
    """Build an index mapping file paths to their module/document node IDs.

    Handles both absolute and relative paths in node IDs by indexing on
    the file_path attribute stored in each node.
    """
    index: dict[str, str] = {}
    for node_id, data in G.nodes(data=True):
        if data.get("kind") in ("module", "document"):
            fp = data.get("file_path", "")
            if fp:
                index[fp] = node_id
    return index


# ---------------------------------------------------------------------------
# Graph enrichment
# ---------------------------------------------------------------------------


def enrich_graph_with_cochange(
    G: nx.DiGraph,
    source_dir: Path,
    *,
    max_commits: int = 0,
    since: str | None = None,
    max_files_per_commit: int = 30,
    min_support: int = 3,
    min_confidence: float = 0.3,
    decay_half_life_days: int = 180,
    max_sample_messages: int = 10,
    on_progress: callable | None = None,
) -> int:
    """Extract co-change relationships from git history and add to graph.

    This is the main entry point, designed to be called from the pipeline
    after build_graph() and before compute_edge_weights().

    Args:
        G: The code graph to enrich (modified in-place).
        source_dir: Source directory (must be in a git repo).
        max_commits: Max commits to analyze (0 = all history).
        since: Git date filter (e.g. "2 years ago").
        max_files_per_commit: Skip bulk-change commits.
        min_support: Minimum co-commit count.
        min_confidence: Minimum strength threshold.
        decay_half_life_days: Half-life for time decay.
        max_sample_messages: Max commit messages per edge.
        on_progress: Optional progress callback(stage, detail).

    Returns:
        Number of co-change edges added.
    """
    source_path = Path(source_dir).resolve()

    if not _is_git_repo(source_path):
        logger.info("Not a git repository, skipping co-change extraction")
        return 0

    def _progress(detail: str) -> None:
        if on_progress:
            on_progress("git_cochange", detail)

    # Build file_path → node_id index from the graph
    # This handles absolute paths in node IDs vs relative paths from git log
    file_index = _build_file_to_node_index(G)

    # Step 1: Parse git log
    _progress("Parsing git history")
    t0 = time.perf_counter()
    commits = parse_git_log(source_path, max_commits=max_commits, since=since)
    _progress(f"Parsed {len(commits)} commits in {time.perf_counter() - t0:.1f}s")

    if not commits:
        _progress("No commits found")
        return 0

    # Step 2: Compute co-change pairs (uses relative paths internally)
    _progress("Computing co-change relationships")
    cochange_pairs = compute_cochange_pairs(
        commits,
        source_path,
        max_files_per_commit=max_files_per_commit,
        min_support=min_support,
        min_confidence=min_confidence,
        decay_half_life_days=decay_half_life_days,
        max_sample_messages=max_sample_messages,
    )

    # Build a reverse lookup: relative path → node_id
    # Git log gives relative paths, graph uses absolute paths
    rel_to_node: dict[str, str] = {}
    for abs_path, node_id in file_index.items():
        try:
            rel = str(Path(abs_path).relative_to(source_path))
            rel_to_node[rel] = node_id
        except ValueError:
            # Already relative or outside source_dir
            rel_to_node[abs_path] = node_id

    # Step 3: Add edges to graph using the lookup
    added = 0
    for edge in cochange_pairs:
        # Resolve relative paths from co-change pairs to actual node IDs
        src_rel = edge.source.split("::")[0]  # extract file path from module ID
        tgt_rel = edge.target.split("::")[0]

        src_node = rel_to_node.get(src_rel)
        tgt_node = rel_to_node.get(tgt_rel)

        if src_node and tgt_node and G.has_node(src_node) and G.has_node(tgt_node):
            # Add both directions (co-change is symmetric)
            for src, tgt in [(src_node, tgt_node), (tgt_node, src_node)]:
                if not G.has_edge(src, tgt) or G.edges[src, tgt].get("relation") != "co_change":
                    G.add_edge(
                        src, tgt,
                        relation="co_change",
                        confidence=edge.confidence,
                        co_change_count=edge.co_change_count,
                        co_change_strength=edge.strength,
                        co_change_recency=edge.recency,
                        sample_messages=edge.sample_messages,
                    )
                    added += 1

    _progress(f"Added {added} co-change edges from {len(cochange_pairs)} pairs")
    return added
