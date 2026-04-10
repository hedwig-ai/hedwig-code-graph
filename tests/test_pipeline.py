"""Integration tests for the full pipeline."""

from __future__ import annotations

from pathlib import Path

from hedwig_kg.core.pipeline import PipelineResult, run_pipeline
from hedwig_kg.storage.store import KnowledgeStore


def _create_mini_project(tmp_path: Path) -> Path:
    """Create a realistic mini project for pipeline testing."""
    src = tmp_path / "src"
    src.mkdir()

    (src / "models.py").write_text(
        "class User:\n"
        '    """A user account."""\n'
        "    def __init__(self, name: str):\n"
        "        self.name = name\n"
        "\n"
        "class Admin(User):\n"
        '    """Admin user with extra privileges."""\n'
        "    def promote(self):\n"
        "        pass\n"
    )

    (src / "service.py").write_text(
        "from models import User, Admin\n"
        "\n"
        "def create_user(name: str) -> User:\n"
        '    """Create a new user."""\n'
        "    return User(name)\n"
        "\n"
        "def get_admin(name: str) -> Admin:\n"
        "    return Admin(name)\n"
    )

    (src / "config.yaml").write_text(
        "database:\n"
        "  host: localhost\n"
        "  port: 5432\n"
    )

    (src / "README.md").write_text(
        "# Test Project\n"
        "A simple test project for pipeline testing.\n"
    )

    return src


class TestPipelineNoEmbed:
    """Test the full pipeline without embeddings (fast, no model download)."""

    def test_pipeline_runs_successfully(self, tmp_path):
        src = _create_mini_project(tmp_path)
        out = tmp_path / "output"

        result = run_pipeline(
            source_dir=src,
            output_dir=out,
            embed=False,
        )

        assert isinstance(result, PipelineResult)
        assert result.detect_result is not None
        assert result.graph is not None
        assert result.graph.number_of_nodes() > 0
        assert result.graph.number_of_edges() > 0
        assert result.db_path == str(out / "knowledge.db")

    def test_pipeline_detects_file_types(self, tmp_path):
        src = _create_mini_project(tmp_path)
        result = run_pipeline(src, output_dir=tmp_path / "out", embed=False)

        detected_types = {f.file_type for f in result.detect_result.files}
        assert "code" in detected_types
        # config/doc files are also detected
        detected_langs = {f.language for f in result.detect_result.files}
        assert "python" in detected_langs

    def test_pipeline_extracts_classes_and_functions(self, tmp_path):
        src = _create_mini_project(tmp_path)
        result = run_pipeline(src, output_dir=tmp_path / "out", embed=False)

        kinds = {
            data.get("kind")
            for _, data in result.graph.nodes(data=True)
        }
        assert "module" in kinds
        # Should extract at least classes or functions
        assert "class" in kinds or "function" in kinds

    def test_pipeline_builds_relationships(self, tmp_path):
        src = _create_mini_project(tmp_path)
        result = run_pipeline(src, output_dir=tmp_path / "out", embed=False)

        relations = {
            data.get("relation")
            for _, _, data in result.graph.edges(data=True)
        }
        assert "defines" in relations

    def test_pipeline_computes_pagerank(self, tmp_path):
        src = _create_mini_project(tmp_path)
        result = run_pipeline(src, output_dir=tmp_path / "out", embed=False)

        assert len(result.pagerank) > 0
        assert all(v > 0 for v in result.pagerank.values())

    def test_pipeline_runs_clustering(self, tmp_path):
        src = _create_mini_project(tmp_path)
        result = run_pipeline(src, output_dir=tmp_path / "out", embed=False)

        assert result.cluster_result is not None

    def test_pipeline_runs_analysis(self, tmp_path):
        src = _create_mini_project(tmp_path)
        result = run_pipeline(src, output_dir=tmp_path / "out", embed=False)

        assert result.analysis is not None
        assert result.analysis.quality_metrics.get("nodes", 0) > 0

    def test_pipeline_persists_to_db(self, tmp_path):
        src = _create_mini_project(tmp_path)
        out = tmp_path / "out"
        result = run_pipeline(src, output_dir=out, embed=False)

        db_path = out / "knowledge.db"
        assert db_path.exists()

        store = KnowledgeStore(db_path)
        loaded = store.load_graph()
        assert loaded.number_of_nodes() == result.graph.number_of_nodes()
        assert loaded.number_of_edges() == result.graph.number_of_edges()
        assert store.get_meta("status") == "complete"
        store.close()

    def test_pipeline_with_empty_dir(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = run_pipeline(empty, output_dir=tmp_path / "out", embed=False)

        assert result.detect_result is not None
        assert len(result.detect_result.files) == 0

    def test_pipeline_progress_callback(self, tmp_path):
        src = _create_mini_project(tmp_path)
        stages_seen = []

        def on_progress(stage, detail):
            stages_seen.append(stage)

        run_pipeline(
            src, output_dir=tmp_path / "out", embed=False,
            on_progress=on_progress,
        )

        assert "detect" in stages_seen
        assert "extract" in stages_seen
        assert "build" in stages_seen
        assert "done" in stages_seen

    def test_pipeline_respects_max_file_size(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "small.py").write_text("x = 1")
        (src / "big.py").write_text("y = 2\n" * 10000)

        result = run_pipeline(
            src, output_dir=tmp_path / "out",
            embed=False, max_file_size=100,
        )

        files = {f.path.name for f in result.detect_result.files}
        assert "small.py" in files
        assert "big.py" not in files
