"""Tests for TypeScript-specific tree-sitter extraction.

Tests interfaces, type aliases, enums, and generics that are
unique to TypeScript (not shared with JavaScript).
"""

from __future__ import annotations

import pytest

from hedwig_cg.core.ts_extract import _ensure_parser, extract_file_ts


@pytest.fixture(autouse=True)
def _skip_if_no_ts_parser():
    """Skip all tests if tree-sitter-typescript is not available."""
    if not _ensure_parser("typescript"):
        pytest.skip("tree-sitter-typescript not available")
    # Clear tags_extract cache to avoid cross-test pollution
    from hedwig_cg.core.tags_extract import _cache
    _cache.pop("typescript", None)


class TestInterfaceExtraction:
    """Test TypeScript interface extraction."""

    def test_basic_interface(self, tmp_path):
        code = """
interface User {
    name: string;
    age: number;
}
"""
        f = tmp_path / "user.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        kinds = {n.kind for n in result.nodes}
        assert "interface" in kinds
        iface = [n for n in result.nodes if n.kind == "interface"][0]
        assert iface.name == "User"

    def test_interface_with_methods(self, tmp_path):
        code = """
interface Repository {
    findById(id: string): Promise<Entity>;
    save(entity: Entity): void;
    count: number;
}
"""
        f = tmp_path / "repo.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        names = {n.name for n in result.nodes}
        assert "Repository" in names
        # Method signatures should be extracted
        method_nodes = [n for n in result.nodes if n.kind == "method"]
        method_names = {n.name for n in method_nodes}
        assert "Repository.findById" in method_names
        assert "Repository.save" in method_names

    def test_interface_extends(self, tmp_path):
        code = """
interface Animal {
    name: string;
}

interface Dog extends Animal {
    breed: string;
}
"""
        f = tmp_path / "animals.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        ifaces = [n for n in result.nodes if n.kind == "interface"]
        assert len(ifaces) == 2
        # Check extends edge
        extends_edges = [e for e in result.edges if e.relation == "extends"]
        assert len(extends_edges) >= 1
        assert any("Animal" in e.target for e in extends_edges)

    def test_exported_interface(self, tmp_path):
        code = """
export interface Config {
    host: string;
    port: number;
}
"""
        f = tmp_path / "config.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        ifaces = [n for n in result.nodes if n.kind == "interface"]
        assert len(ifaces) == 1
        assert ifaces[0].name == "Config"


class TestTypeAliasExtraction:
    """Test TypeScript type alias extraction."""

    def test_simple_type_alias(self, tmp_path):
        code = """
type ID = string;
"""
        f = tmp_path / "types.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        aliases = [n for n in result.nodes if n.kind == "type_alias"]
        assert len(aliases) == 1
        assert aliases[0].name == "ID"

    def test_union_type_alias(self, tmp_path):
        code = """
type Status = "active" | "inactive" | "pending";
type Result = Success | Error;
"""
        f = tmp_path / "unions.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        aliases = [n for n in result.nodes if n.kind == "type_alias"]
        assert len(aliases) == 2
        names = {a.name for a in aliases}
        assert "Status" in names
        assert "Result" in names

    def test_generic_type_alias(self, tmp_path):
        code = """
type Nullable<T> = T | null;
type Pair<A, B> = { first: A; second: B };
"""
        f = tmp_path / "generics.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        aliases = [n for n in result.nodes if n.kind == "type_alias"]
        assert len(aliases) == 2


class TestEnumExtraction:
    """Test TypeScript enum extraction."""

    def test_basic_enum(self, tmp_path):
        code = """
enum Direction {
    Up,
    Down,
    Left,
    Right
}
"""
        f = tmp_path / "direction.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        enums = [n for n in result.nodes if n.kind == "enum"]
        assert len(enums) == 1
        assert enums[0].name == "Direction"

    def test_string_enum(self, tmp_path):
        code = """
enum Color {
    Red = "RED",
    Green = "GREEN",
    Blue = "BLUE"
}
"""
        f = tmp_path / "color.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        enums = [n for n in result.nodes if n.kind == "enum"]
        assert len(enums) == 1
        assert enums[0].name == "Color"
        # Enum members should have defines edges
        defines = [e for e in result.edges
                   if e.relation == "defines" and "Color" in e.source]
        assert len(defines) >= 1

    def test_exported_enum(self, tmp_path):
        code = """
export enum LogLevel {
    DEBUG = 0,
    INFO = 1,
    WARN = 2,
    ERROR = 3
}
"""
        f = tmp_path / "loglevel.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        enums = [n for n in result.nodes if n.kind == "enum"]
        assert len(enums) == 1
        assert enums[0].name == "LogLevel"


class TestComplexTypeScript:
    """Test complex TypeScript patterns."""

    def test_mixed_declarations(self, tmp_path):
        code = """
interface Service {
    start(): void;
    stop(): void;
}

type ServiceConfig = {
    name: string;
    timeout: number;
};

enum ServiceStatus {
    Running = "running",
    Stopped = "stopped"
}

class MyService implements Service {
    private config: ServiceConfig;

    constructor(config: ServiceConfig) {
        this.config = config;
    }

    start(): void {}
    stop(): void {}
}

function createService(config: ServiceConfig): Service {
    return new MyService(config);
}
"""
        f = tmp_path / "service.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        kinds = {n.kind for n in result.nodes}
        assert "interface" in kinds
        assert "type_alias" in kinds
        assert "enum" in kinds
        assert "class" in kinds
        assert "function" in kinds

        names = {n.name for n in result.nodes}
        assert "Service" in names
        assert "ServiceConfig" in names
        assert "ServiceStatus" in names
        assert "MyService" in names
        assert "createService" in names

    def test_generic_interface(self, tmp_path):
        code = """
interface Repository<T> {
    findById(id: string): T;
    findAll(): T[];
    save(item: T): void;
    delete(id: string): boolean;
}
"""
        f = tmp_path / "repository.ts"
        f.write_text(code)
        result = extract_file_ts(str(f), "typescript", code)
        ifaces = [n for n in result.nodes if n.kind == "interface"]
        assert len(ifaces) == 1
        assert ifaces[0].name == "Repository"
        methods = [n for n in result.nodes if n.kind == "method"]
        assert len(methods) >= 3
