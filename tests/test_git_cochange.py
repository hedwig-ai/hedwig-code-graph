"""Tests for git co-change extraction module."""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import networkx as nx

from hedwig_cg.core.git_cochange import (
    CommitInfo,
    _build_file_to_node_index,
    _file_to_module_id,
    _parse_log_output,
    _resolve_renames,
    compute_cochange_pairs,
    enrich_graph_with_cochange,
    parse_git_log,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_DIR = Path("/repo")


def _make_commits(
    *file_groups: list[str],
    base_time: int = 1700000000,
    interval: int = 86400,
) -> list[CommitInfo]:
    """Create test commits from file groups."""
    commits = []
    for i, files in enumerate(file_groups):
        commits.append(CommitInfo(
            hash=f"abc{i:04d}",
            timestamp=base_time + i * interval,
            message=f"commit {i}: update {', '.join(files)}",
            files=list(files),
        ))
    return commits


def _make_graph_with_modules(*rel_paths: str, source_dir: Path = REPO_DIR) -> nx.DiGraph:
    """Create a graph with module nodes using absolute paths (matching real extraction).

    The file_path attribute uses absolute paths, matching how ts_extract works.
    node IDはfile:0形式（moduleノード）。
    """
    G = nx.DiGraph()
    for rp in rel_paths:
        abs_path = str(source_dir / rp)
        stem = Path(rp).stem
        node_id = f"{abs_path}:0"
        G.add_node(node_id, label=stem, kind="module", file_path=abs_path, language="python")
    return G


# ---------------------------------------------------------------------------
# _file_to_module_id
# ---------------------------------------------------------------------------

class TestFileToModuleId:
    def test_simple_python_file(self):
        assert _file_to_module_id("src/auth.py") == "src/auth.py:0"

    def test_nested_path(self):
        assert _file_to_module_id("a/b/c/main.py") == "a/b/c/main.py:0"

    def test_no_directory(self):
        assert _file_to_module_id("app.py") == "app.py:0"

    def test_js_file(self):
        assert _file_to_module_id("src/index.ts") == "src/index.ts:0"


# ---------------------------------------------------------------------------
# _build_file_to_node_index
# ---------------------------------------------------------------------------

class TestBuildFileToNodeIndex:
    def test_indexes_module_nodes(self):
        G = _make_graph_with_modules("a.py", "b.py")
        index = _build_file_to_node_index(G)
        assert len(index) == 2
        assert "/repo/a.py" in index
        assert "/repo/b.py" in index

    def test_indexes_document_nodes(self):
        G = nx.DiGraph()
        G.add_node("README.md:0", label="README",
                    kind="document", file_path="/repo/README.md")
        index = _build_file_to_node_index(G)
        assert "/repo/README.md" in index

    def test_skips_non_root_nodes(self):
        G = nx.DiGraph()
        G.add_node("a.py:5", label="foo",
                    kind="function", file_path="/repo/a.py")
        index = _build_file_to_node_index(G)
        assert len(index) == 0


# ---------------------------------------------------------------------------
# _parse_log_output
# ---------------------------------------------------------------------------

class TestParseLogOutput:
    def test_basic_parse(self):
        output = """---HEDWIG_COMMIT---
abc1234
1700000000
fix: update auth logic
M\tsrc/auth.py
M\tsrc/session.py
"""
        commits = _parse_log_output(output)
        assert len(commits) == 1
        assert commits[0].hash == "abc1234"
        assert commits[0].timestamp == 1700000000
        assert commits[0].message == "fix: update auth logic"
        assert set(commits[0].files) == {"src/auth.py", "src/session.py"}

    def test_rename_detection(self):
        output = """---HEDWIG_COMMIT---
abc5678
1700000000
refactor: rename module
R100\told/auth.py\tnew/auth.py
M\tsrc/main.py
"""
        commits = _parse_log_output(output)
        assert len(commits) == 1
        assert "new/auth.py" in commits[0].files
        assert "old/auth.py" not in commits[0].files

    def test_multiple_commits(self):
        output = """---HEDWIG_COMMIT---
aaa1111
1700000000
first commit
M\ta.py
M\tb.py
---HEDWIG_COMMIT---
bbb2222
1700086400
second commit
M\tb.py
M\tc.py
"""
        commits = _parse_log_output(output)
        assert len(commits) == 2
        assert commits[0].files == ["a.py", "b.py"]
        assert commits[1].files == ["b.py", "c.py"]

    def test_empty_output(self):
        assert _parse_log_output("") == []
        assert _parse_log_output("   ") == []

    def test_rename_chain_resolution(self):
        output = """---HEDWIG_COMMIT---
aaa0001
1700000000
rename step 1
R100\tv1.py\tv2.py
M\tother.py
---HEDWIG_COMMIT---
aaa0002
1700086400
rename step 2
R100\tv2.py\tv3.py
M\tother.py
---HEDWIG_COMMIT---
aaa0003
1700172800
old reference
M\tv1.py
M\tother.py
"""
        commits = _parse_log_output(output)
        assert len(commits) == 3
        assert "v3.py" in commits[2].files


# ---------------------------------------------------------------------------
# _resolve_renames
# ---------------------------------------------------------------------------

class TestResolveRenames:
    def test_simple_rename(self):
        commits = [CommitInfo("a", 0, "msg", ["old.py", "other.py"])]
        _resolve_renames(commits, {"old.py": "new.py"})
        assert commits[0].files == ["new.py", "other.py"]

    def test_chain_rename(self):
        commits = [CommitInfo("a", 0, "msg", ["v1.py"])]
        _resolve_renames(commits, {"v1.py": "v2.py", "v2.py": "v3.py"})
        assert commits[0].files == ["v3.py"]

    def test_no_renames(self):
        commits = [CommitInfo("a", 0, "msg", ["keep.py"])]
        _resolve_renames(commits, {})
        assert commits[0].files == ["keep.py"]

    def test_circular_rename_safe(self):
        commits = [CommitInfo("a", 0, "msg", ["a.py"])]
        _resolve_renames(commits, {"a.py": "b.py", "b.py": "a.py"})
        assert commits[0].files[0] in ("a.py", "b.py")


# ---------------------------------------------------------------------------
# compute_cochange_pairs
# ---------------------------------------------------------------------------

class TestComputeCochangePairs:
    def test_basic_cochange(self):
        commits = _make_commits(
            ["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "c.py"],
        )
        edges = compute_cochange_pairs(
            commits, REPO_DIR, min_support=3, min_confidence=0.0, decay_half_life_days=365,
        )
        assert len(edges) >= 1
        ab_edge = [e for e in edges if "a" in e.source and "b" in e.target]
        assert len(ab_edge) == 1
        assert ab_edge[0].co_change_count == 3

    def test_below_min_support_filtered(self):
        commits = _make_commits(["a.py", "b.py"], ["a.py", "b.py"])
        edges = compute_cochange_pairs(commits, REPO_DIR, min_support=3, min_confidence=0.0)
        assert len(edges) == 0

    def test_fanout_cap(self):
        many_files = [f"file_{i}.py" for i in range(50)]
        commits = _make_commits(many_files, many_files, many_files)
        edges = compute_cochange_pairs(
            commits, REPO_DIR, max_files_per_commit=30, min_support=1, min_confidence=0.0,
        )
        assert len(edges) == 0

    def test_single_file_commit_skipped(self):
        commits = _make_commits(["a.py"], ["a.py"], ["a.py"])
        edges = compute_cochange_pairs(commits, REPO_DIR, min_support=1)
        assert len(edges) == 0

    def test_strength_normalization(self):
        commits = _make_commits(
            ["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "c.py"],
        )
        edges = compute_cochange_pairs(
            commits, REPO_DIR, min_support=3, min_confidence=0.0, decay_half_life_days=365,
        )
        ab_edge = [e for e in edges if "a" in e.source and "b" in e.target][0]
        expected = 3 / math.sqrt(4 * 3)
        assert abs(ab_edge.strength - round(expected, 4)) < 0.001

    def test_time_decay_weighting(self):
        recent_commits = _make_commits(
            ["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "b.py"],
            base_time=999_000, interval=500,
        )
        old_commits = _make_commits(
            ["c.py", "d.py"], ["c.py", "d.py"], ["c.py", "d.py"],
            base_time=100, interval=1,
        )
        all_commits = recent_commits + old_commits
        edges = compute_cochange_pairs(
            all_commits, REPO_DIR, min_support=3, min_confidence=0.0, decay_half_life_days=1,
        )
        ab_edge = [e for e in edges if "a" in e.source and "b" in e.target]
        cd_edge = [e for e in edges if "c" in e.source and "d" in e.target]
        assert len(ab_edge) == 1 and len(cd_edge) == 1
        assert ab_edge[0].recency > cd_edge[0].recency

    def test_confidence_levels(self):
        commits_high = _make_commits(*([["a.py", "b.py"]] * 6))
        edges = compute_cochange_pairs(
            commits_high, REPO_DIR, min_support=3, min_confidence=0.0, decay_half_life_days=365,
        )
        assert len(edges) == 1
        assert edges[0].confidence == "EXTRACTED"

    def test_commit_messages_captured(self):
        commits = _make_commits(["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "b.py"])
        edges = compute_cochange_pairs(
            commits, REPO_DIR, min_support=3, min_confidence=0.0, max_sample_messages=2,
        )
        assert len(edges) == 1
        assert len(edges[0].sample_messages) <= 2
        assert all(isinstance(m, str) for m in edges[0].sample_messages)

    def test_module_id_format(self):
        commits = _make_commits(
            ["src/auth.py", "src/session.py"],
            ["src/auth.py", "src/session.py"],
            ["src/auth.py", "src/session.py"],
        )
        edges = compute_cochange_pairs(commits, REPO_DIR, min_support=3, min_confidence=0.0)
        assert len(edges) == 1
        assert edges[0].source == "src/auth.py:0"
        assert edges[0].target == "src/session.py:0"


# ---------------------------------------------------------------------------
# enrich_graph_with_cochange
# ---------------------------------------------------------------------------

class TestEnrichGraph:
    @patch("hedwig_cg.core.git_cochange._is_git_repo", return_value=False)
    def test_non_git_repo_returns_zero(self, mock_is_git):
        G = _make_graph_with_modules("a.py", "b.py")
        count = enrich_graph_with_cochange(G, REPO_DIR)
        assert count == 0

    @patch("hedwig_cg.core.git_cochange._is_git_repo", return_value=True)
    @patch("hedwig_cg.core.git_cochange._get_git_root", return_value=REPO_DIR)
    @patch("hedwig_cg.core.git_cochange.parse_git_log")
    def test_edges_added_to_graph(self, mock_log, mock_git_root, mock_is_git):
        """Co-change edges should be added bidirectionally to the graph."""
        mock_log.return_value = _make_commits(
            ["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "b.py"],
        )
        G = _make_graph_with_modules("a.py", "b.py")
        initial_edges = G.number_of_edges()

        count = enrich_graph_with_cochange(
            G, REPO_DIR, min_support=3, min_confidence=0.0,
        )

        assert count > 0
        assert G.number_of_edges() > initial_edges

        # Check bidirectional — nodes use absolute paths
        a_id = f"{REPO_DIR}/a.py:0"
        b_id = f"{REPO_DIR}/b.py:0"
        assert G.has_edge(a_id, b_id)
        assert G.has_edge(b_id, a_id)
        assert G.edges[a_id, b_id]["relation"] == "co_change"

    @patch("hedwig_cg.core.git_cochange._is_git_repo", return_value=True)
    @patch("hedwig_cg.core.git_cochange._get_git_root", return_value=REPO_DIR)
    @patch("hedwig_cg.core.git_cochange.parse_git_log")
    def test_missing_nodes_skipped(self, mock_log, mock_git_root, mock_is_git):
        mock_log.return_value = _make_commits(
            ["a.py", "missing.py"], ["a.py", "missing.py"], ["a.py", "missing.py"],
        )
        G = _make_graph_with_modules("a.py")
        count = enrich_graph_with_cochange(G, REPO_DIR, min_support=3, min_confidence=0.0)
        assert count == 0

    @patch("hedwig_cg.core.git_cochange._is_git_repo", return_value=True)
    @patch("hedwig_cg.core.git_cochange._get_git_root", return_value=REPO_DIR)
    @patch("hedwig_cg.core.git_cochange.parse_git_log")
    def test_edge_attributes(self, mock_log, mock_git_root, mock_is_git):
        mock_log.return_value = _make_commits(
            ["a.py", "b.py"], ["a.py", "b.py"], ["a.py", "b.py"],
        )
        G = _make_graph_with_modules("a.py", "b.py")
        enrich_graph_with_cochange(G, REPO_DIR, min_support=3, min_confidence=0.0)

        a_id = f"{REPO_DIR}/a.py:0"
        b_id = f"{REPO_DIR}/b.py:0"
        edge_data = G.edges[a_id, b_id]
        assert edge_data["relation"] == "co_change"
        assert "co_change_count" in edge_data
        assert "co_change_strength" in edge_data
        assert "co_change_recency" in edge_data
        assert "sample_messages" in edge_data
        assert isinstance(edge_data["sample_messages"], list)

    @patch("hedwig_cg.core.git_cochange._is_git_repo", return_value=True)
    @patch("hedwig_cg.core.git_cochange.parse_git_log", return_value=[])
    def test_empty_history(self, mock_log, mock_is_git):
        G = _make_graph_with_modules("a.py")
        count = enrich_graph_with_cochange(G, REPO_DIR)
        assert count == 0


# ---------------------------------------------------------------------------
# parse_git_log (integration with subprocess mock)
# ---------------------------------------------------------------------------

class TestParseGitLog:
    @patch("subprocess.run")
    def test_subprocess_failure_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="fatal: not a git repo")
        commits = parse_git_log(Path("/tmp"))
        assert commits == []

    @patch("subprocess.run", side_effect=FileNotFoundError("git not found"))
    def test_git_not_installed(self, mock_run):
        commits = parse_git_log(Path("/tmp"))
        assert commits == []
