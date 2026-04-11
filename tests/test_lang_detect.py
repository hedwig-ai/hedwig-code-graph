"""Tests for hedwig_cg.core.lang_detect — Unicode-based language detection."""

from hedwig_cg.core.lang_detect import _count_scripts, detect_language


class TestCountScripts:
    def test_latin_only(self):
        counts = _count_scripts("Hello world function class")
        assert counts["latin"] > 0
        assert counts["cjk"] == 0
        assert counts["cyrillic"] == 0

    def test_korean(self):
        counts = _count_scripts("인증 핸들러 클래스")
        assert counts["cjk"] > 0  # Hangul is in CJK range

    def test_japanese(self):
        counts = _count_scripts("認証ハンドラー")
        assert counts["cjk"] > 0

    def test_cyrillic(self):
        counts = _count_scripts("Авторизация обработчик")
        assert counts["cyrillic"] > 0

    def test_mixed(self):
        counts = _count_scripts("Hello 世界 Мир")
        assert counts["latin"] > 0
        assert counts["cjk"] > 0
        assert counts["cyrillic"] > 0

    def test_empty(self):
        counts = _count_scripts("")
        assert all(v == 0 for v in counts.values())

    def test_digits_ignored(self):
        counts = _count_scripts("12345 67890")
        assert all(v == 0 for v in counts.values())


class TestDetectLanguage:
    def test_english_code(self):
        texts = [
            "def hello(): pass",
            "class AuthHandler:",
            "function to handle HTTP requests",
        ]
        assert detect_language(texts) == "en"

    def test_korean_text(self):
        texts = [
            "인증 핸들러 클래스입니다",
            "데이터베이스 연결 풀 관리",
            "이 함수는 요청을 처리합니다",
        ]
        assert detect_language(texts) == "multilingual"

    def test_japanese_text(self):
        texts = [
            "認証ハンドラークラス",
            "データベース接続プール管理",
            "この関数はリクエストを処理します",
        ]
        assert detect_language(texts) == "multilingual"

    def test_chinese_text(self):
        texts = [
            "认证处理类",
            "数据库连接池管理",
            "此函数处理请求",
        ]
        assert detect_language(texts) == "multilingual"

    def test_russian_text(self):
        texts = [
            "Класс обработки авторизации",
            "Управление пулом соединений",
        ]
        assert detect_language(texts) == "multilingual"

    def test_empty_returns_en(self):
        assert detect_language([]) == "en"

    def test_mostly_code_returns_en(self):
        """Pure code with no natural language should default to English."""
        texts = [
            "def foo(): return 1",
            "class Bar(Baz):",
            "import os, sys",
            "x = [i for i in range(10)]",
        ]
        assert detect_language(texts) == "en"

    def test_mixed_with_threshold(self):
        """When majority is Latin, should return en."""
        texts = ["Hello world " * 50]  # Overwhelmingly Latin
        assert detect_language(texts) == "en"

    def test_custom_threshold(self):
        """Lower threshold makes it harder to trigger multilingual."""
        texts = ["Hello 世界"]  # Some CJK but not a lot
        # With very low threshold, even a little non-Latin triggers multilingual
        # With very high threshold, it should be en
        result_strict = detect_language(texts, threshold=0.99)
        assert result_strict == "multilingual"
