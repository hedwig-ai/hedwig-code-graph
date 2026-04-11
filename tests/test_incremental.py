"""Tests for incremental build support."""

from pathlib import Path

from hedwig_cg.core.pipeline import run_pipeline


def _create_project(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        "class App:\n"
        '    """Main application."""\n'
        "    def run(self):\n"
        "        pass\n"
    )
    (src / "utils.py").write_text(
        "def helper():\n"
        '    """A helper function."""\n'
        "    return 42\n"
    )
    return src


class TestIncrementalBuild:
    def test_first_build_extracts_all(self, tmp_path):
        src = _create_project(tmp_path)
        out = tmp_path / "out"
        result = run_pipeline(src, output_dir=out, embed=False, incremental=True)
        assert len(result.extractions) > 0
        assert result.graph.number_of_nodes() > 0

    def test_second_build_skips_unchanged(self, tmp_path):
        src = _create_project(tmp_path)
        out = tmp_path / "out"

        # First build
        run_pipeline(src, output_dir=out, embed=False, incremental=True)

        # Second build — no changes
        r2 = run_pipeline(src, output_dir=out, embed=False, incremental=True)
        # All files should be skipped
        assert len(r2.extractions) == 0

    def test_modified_file_re_extracted(self, tmp_path):
        src = _create_project(tmp_path)
        out = tmp_path / "out"

        # First build
        run_pipeline(src, output_dir=out, embed=False, incremental=True)

        # Modify one file
        (src / "app.py").write_text(
            "class App:\n"
            '    """Modified application."""\n'
            "    def run(self):\n"
            "        return True\n"
        )

        # Second build — only modified file should be re-extracted
        r2 = run_pipeline(src, output_dir=out, embed=False, incremental=True)
        assert len(r2.extractions) == 1
        # The extraction should be from app.py
        extracted_files = {
            n.file_path for ext in r2.extractions for n in ext.nodes
        }
        assert any("app.py" in f for f in extracted_files)

    def test_non_incremental_extracts_all(self, tmp_path):
        src = _create_project(tmp_path)
        out = tmp_path / "out"

        # First build with incremental
        run_pipeline(src, output_dir=out, embed=False, incremental=True)

        # Second build WITHOUT incremental — should extract all
        r2 = run_pipeline(src, output_dir=out, embed=False, incremental=False)
        assert len(r2.extractions) > 0
