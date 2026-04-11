"""Tests for file detection and classification."""


from hedwig_cg.core.detect import EXT_TO_LANG, detect


class TestDetect:
    def test_detects_python_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "util.js").write_text("console.log('hi')")
        result = detect(tmp_path)
        langs = {f.language for f in result.files}
        assert "python" in langs
        assert "javascript" in langs
        assert len(result.files) == 2

    def test_skips_hidden_dirs(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("x")
        (tmp_path / "app.py").write_text("x = 1")
        result = detect(tmp_path)
        assert len(result.files) == 1
        assert result.files[0].language == "python"

    def test_skips_large_files(self, tmp_path):
        big = tmp_path / "big.py"
        big.write_text("x" * 2_000_000)
        result = detect(tmp_path, max_file_size=1_000_000)
        assert len(result.files) == 0
        assert any("too_large" in s for s in result.skipped)

    def test_skips_sensitive_files(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET=x")
        (tmp_path / "app.py").write_text("x = 1")
        result = detect(tmp_path)
        assert len(result.files) == 1
        assert any("sensitive" in s for s in result.skipped)

    def test_respects_ignore_file(self, tmp_path):
        (tmp_path / ".hedwig-cg-ignore").write_text("vendor\n")
        vendor = tmp_path / "vendor"
        vendor.mkdir()
        (vendor / "lib.py").write_text("x")
        (tmp_path / "app.py").write_text("x")
        result = detect(tmp_path)
        assert len(result.files) == 1

    def test_ext_to_lang_coverage(self):
        assert EXT_TO_LANG[".py"] == "python"
        assert EXT_TO_LANG[".ts"] == "typescript"
        assert EXT_TO_LANG[".go"] == "go"
        assert EXT_TO_LANG[".rs"] == "rust"

    def test_empty_directory(self, tmp_path):
        result = detect(tmp_path)
        assert len(result.files) == 0
