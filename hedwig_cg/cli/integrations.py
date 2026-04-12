"""AI agent platform integrations (install/uninstall commands)."""

from __future__ import annotations

from pathlib import Path

import click

from ._helpers import (
    auto_rebuild_command,
    human_choose,
    human_done,
    human_header,
    human_ok,
    human_skip,
    human_warn,
)

# ─── Claude Code ─────────────────────────────────────────────────────────────

@click.group(name="claude")
def claude_group():
    """Manage Claude Code integration (skill + CLAUDE.md + hooks)."""
    pass


@claude_group.command(name="install")
@click.option(
    "--scope",
    type=click.Choice(["user", "project"], case_sensitive=False),
    default=None,
    help="Install scope: 'user' (global ~/.claude/skills/) or 'project' (.claude/skills/). "
         "If omitted, you will be prompted to choose.",
)
def claude_install(scope: str | None):
    """Install Claude Code integration.

    Priority: 1) Skill  2) CLAUDE.md + hooks  3) MCP
    """
    import json
    import shutil

    project_root = Path.cwd()

    # --- Prompt for scope if not specified ---
    if scope is None:
        scope = human_choose(
            "Where should hedwig-cg be installed?",
            ["user", "project"],
            descriptions=[
                "Global (~/.claude/skills/) — available in ALL projects",
                "Local (.claude/skills/) — available only in THIS project",
            ],
            default=1,
        )

    human_header(f"Installing hedwig-cg for Claude Code (scope: {scope})")

    # --- Priority 1: Install Skill ---
    skill_source = Path(__file__).parent.parent / "skill.md"
    if scope == "user":
        skill_dir = Path.home() / ".claude" / "skills" / "hedwig-cg"
    else:
        skill_dir = project_root / ".claude" / "skills" / "hedwig-cg"

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dest = skill_dir / "SKILL.md"

    if skill_source.exists():
        shutil.copy2(skill_source, skill_dest)
        human_ok(f"Skill installed to {skill_dir}/")
    else:
        human_warn("Skill source not found")

    # --- Priority 2: CLAUDE.md + hooks ---
    # 1. Write section to project CLAUDE.md
    claude_md = project_root / "CLAUDE.md"
    marker = "## hedwig-cg"
    section = (
        "\n## hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files with Glob/Grep, run `hedwig-cg search` first. "
        "Only fall back to Grep if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density)\n"
    )

    if claude_md.exists():
        content = claude_md.read_text()
        if marker in content:
            human_skip("CLAUDE.md section already exists")
        else:
            claude_md.write_text(content + section)
            human_ok("CLAUDE.md section added")
    else:
        claude_md.write_text(section.lstrip("\n"))
        human_ok("CLAUDE.md created")

    # 2. Write PreToolUse hook to .claude/settings.json
    settings_dir = project_root / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "settings.json"

    hook_entry = {
        "matcher": "Glob|Grep",
        "hooks": [{
            "type": "command",
            "command": (
                '[ -f .hedwig-cg/knowledge.db ] && echo '
                '\'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
                '"additionalContext":"hedwig-cg: code graph available. '
                "Use `hedwig-cg search \\\"<query>\\\"` (5-signal HybridRAG) "
                "instead of grepping raw files. This single command covers "
                "vector, graph, keyword, and community search with RRF fusion."
                '"}}\' || true'
            ),
        }],
    }

    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    pre_hooks = hooks.setdefault("PreToolUse", [])

    already = any(
        "hedwig-cg" in json.dumps(h)
        for h in pre_hooks
    )
    if already:
        human_skip("PreToolUse hook already exists")
    else:
        pre_hooks.append(hook_entry)
        human_ok("PreToolUse hook added")

    # 3. Write Stop hook for auto-rebuild
    stop_hook_entry = {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": auto_rebuild_command(),
            "timeout": 10,
        }],
    }
    stop_hooks = hooks.setdefault("Stop", [])
    stop_already = any("hedwig-cg" in json.dumps(h) or "auto_rebuild" in json.dumps(h)
                       for h in stop_hooks)
    if stop_already:
        human_skip("Stop hook (auto-rebuild) already exists")
    else:
        stop_hooks.append(stop_hook_entry)
        human_ok("Stop hook (auto-rebuild) added")

    settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    human_done("Done! Run 'hedwig-cg build .' to create your first code graph.")


@claude_group.command(name="uninstall")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "all"], case_sensitive=False),
    default="all",
    help="Uninstall scope: 'user', 'project', or 'all' (default).",
)
def claude_uninstall(scope: str):
    """Remove Claude Code integration (skill + CLAUDE.md + hooks)."""
    import json
    import shutil

    human_header("Removing hedwig-cg from Claude Code")
    project_root = Path.cwd()

    # 0. Remove skill
    if scope in ("user", "all"):
        user_skill = Path.home() / ".claude" / "skills" / "hedwig-cg"
        if user_skill.exists():
            shutil.rmtree(user_skill)
            human_ok("User skill removed")
    if scope in ("project", "all"):
        proj_skill = project_root / ".claude" / "skills" / "hedwig-cg"
        if proj_skill.exists():
            shutil.rmtree(proj_skill)
            human_ok("Project skill removed")

    # 1. Remove section from CLAUDE.md
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        lines = claude_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-cg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-cg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        claude_md.write_text(new_content)
        human_ok("hedwig-cg section removed from CLAUDE.md")

    # 2. Remove hooks from .claude/settings.json
    settings_file = project_root / ".claude" / "settings.json"
    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
        hooks = settings.get("hooks", {})
        for event in ("PreToolUse", "Stop"):
            event_hooks = hooks.get(event, [])
            hooks[event] = [
                h for h in event_hooks
                if "hedwig-cg" not in json.dumps(h)
                and "auto_rebuild" not in json.dumps(h)
            ]
            if not hooks[event]:
                hooks.pop(event, None)
        if not hooks:
            settings.pop("hooks", None)
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        human_ok("Hooks removed from .claude/settings.json")

    human_done("hedwig-cg integration removed.")


# ─── Codex CLI ───────────────────────────────────────────────────────────────

@click.group(name="codex")
def codex_group():
    """Manage per-project OpenAI Codex CLI integration."""
    pass


@codex_group.command(name="install")
def codex_install():
    """Install per-project Codex CLI integration (AGENTS.md + hooks.json)."""
    import json

    human_header("Installing hedwig-cg for Codex CLI...")
    project_root = Path.cwd()

    # 1. Write section to project AGENTS.md
    agents_md = project_root / "AGENTS.md"
    marker = "## hedwig-cg"
    section = (
        "\n## hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density)\n"
    )

    if agents_md.exists():
        content = agents_md.read_text()
        if marker in content:
            human_skip("AGENTS.md section already exists")
        else:
            agents_md.write_text(content + section)
            human_ok("hedwig-cg section added to AGENTS.md")
    else:
        agents_md.write_text(section.lstrip("\n"))
        human_ok("AGENTS.md created")

    # 2. Write PreToolUse hook to .codex/hooks.json
    hooks_dir = project_root / ".codex"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hooks_file = hooks_dir / "hooks.json"

    hook_entry = {
        "matcher": "Bash",
        "hooks": [{
            "type": "command",
            "command": (
                '[ -f .hedwig-cg/knowledge.db ] && echo '
                '\'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
                '"additionalContext":"hedwig-cg: code graph available. '
                "Use `hedwig-cg search \\\"<query>\\\"` (5-signal HybridRAG) "
                "instead of grepping raw files. This single command covers "
                "vector, graph, keyword, and community search with RRF fusion."
                '"}}\' || true'
            ),
        }],
    }

    if hooks_file.exists():
        hooks_data = json.loads(hooks_file.read_text())
    else:
        hooks_data = {}

    hooks = hooks_data.setdefault("hooks", {})
    pre_hooks = hooks.setdefault("PreToolUse", [])

    already = any("hedwig-cg" in json.dumps(h) for h in pre_hooks)
    if already:
        human_skip("PreToolUse hook already exists")
    else:
        pre_hooks.append(hook_entry)
        human_ok("PreToolUse hook added to .codex/hooks.json")

    # 3. Write Stop hook for auto-rebuild
    stop_hook_entry = {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": auto_rebuild_command(),
            "timeout": 10,
        }],
    }
    stop_hooks = hooks.setdefault("Stop", [])
    stop_already = any("auto_rebuild" in json.dumps(h) for h in stop_hooks)
    if stop_already:
        human_skip("Stop hook (auto-rebuild) already exists")
    else:
        stop_hooks.append(stop_hook_entry)
        human_ok("Stop hook (auto-rebuild) added")

    hooks_file.write_text(json.dumps(hooks_data, indent=2) + "\n")

    human_done()


@codex_group.command(name="uninstall")
def codex_uninstall():
    """Remove per-project Codex CLI integration."""
    import json

    human_header("Removing hedwig-cg from Codex CLI")
    project_root = Path.cwd()

    # 1. Remove section from AGENTS.md
    agents_md = project_root / "AGENTS.md"
    if agents_md.exists():
        lines = agents_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-cg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-cg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        agents_md.write_text(new_content)
        human_ok("hedwig-cg section removed from AGENTS.md")

    # 2. Remove hooks from .codex/hooks.json
    hooks_file = project_root / ".codex" / "hooks.json"
    if hooks_file.exists():
        hooks_data = json.loads(hooks_file.read_text())
        hooks = hooks_data.get("hooks", {})
        for event in ("PreToolUse", "Stop"):
            event_hooks = hooks.get(event, [])
            hooks[event] = [
                h for h in event_hooks
                if "hedwig-cg" not in json.dumps(h)
                and "auto_rebuild" not in json.dumps(h)
            ]
            if not hooks[event]:
                hooks.pop(event, None)
        if not hooks:
            hooks_data.pop("hooks", None)
        hooks_file.write_text(json.dumps(hooks_data, indent=2) + "\n")
        human_ok("Hooks removed from .codex/hooks.json")

    human_done("hedwig-cg integration removed.")


# ─── Gemini CLI ──────────────────────────────────────────────────────────────

@click.group(name="gemini")
def gemini_group():
    """Manage per-project Google Gemini CLI integration."""
    pass


@gemini_group.command(name="install")
def gemini_install():
    """Install per-project Gemini CLI integration (GEMINI.md + BeforeTool hook)."""
    import json

    human_header("Installing hedwig-cg for Gemini CLI...")
    project_root = Path.cwd()

    # 1. Write section to project GEMINI.md
    gemini_md = project_root / "GEMINI.md"
    marker = "## hedwig-cg"
    section = (
        "\n## hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before reading raw files, run `hedwig-cg search` first. "
        "Only fall back to file reads if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density)\n"
    )

    if gemini_md.exists():
        content = gemini_md.read_text()
        if marker in content:
            human_skip("GEMINI.md section already exists")
        else:
            gemini_md.write_text(content + section)
            human_ok("hedwig-cg section added to GEMINI.md")
    else:
        gemini_md.write_text(section.lstrip("\n"))
        human_ok("GEMINI.md created")

    # 2. Write BeforeTool hook to .gemini/settings.json
    settings_dir = project_root / ".gemini"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "settings.json"

    hook_entry = {
        "matcher": "read_file",
        "hooks": [{
            "type": "command",
            "command": (
                '[ -f .hedwig-cg/knowledge.db ] && echo '
                '\'{"hookSpecificOutput":{"additionalContext":'
                '"hedwig-cg: code graph available. '
                "Use `hedwig-cg search \\\"<query>\\\"` (5-signal HybridRAG) "
                "instead of reading raw files. This single command covers "
                "vector, graph, keyword, and community search with RRF fusion."
                '"}}\' || true'
            ),
        }],
    }

    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    before_hooks = hooks.setdefault("BeforeTool", [])

    already = any("hedwig-cg" in json.dumps(h) for h in before_hooks)
    if already:
        human_skip("BeforeTool hook already exists")
    else:
        before_hooks.append(hook_entry)
        human_ok("BeforeTool hook added to .gemini/settings.json")

    # 3. Write SessionEnd hook for auto-rebuild
    session_end_entry = {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": auto_rebuild_command(),
            "timeout": 10,
        }],
    }
    session_hooks = hooks.setdefault("SessionEnd", [])
    session_already = any("auto_rebuild" in json.dumps(h) for h in session_hooks)
    if session_already:
        human_skip("SessionEnd hook (auto-rebuild) already exists")
    else:
        session_hooks.append(session_end_entry)
        human_ok("SessionEnd hook (auto-rebuild) added")

    settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    human_done()


@gemini_group.command(name="uninstall")
def gemini_uninstall():
    """Remove per-project Gemini CLI integration."""
    import json

    human_header("Removing hedwig-cg from Gemini CLI")
    project_root = Path.cwd()

    # 1. Remove section from GEMINI.md
    gemini_md = project_root / "GEMINI.md"
    if gemini_md.exists():
        lines = gemini_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-cg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-cg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        gemini_md.write_text(new_content)
        human_ok("hedwig-cg section removed from GEMINI.md")

    # 2. Remove hooks from .gemini/settings.json
    settings_file = project_root / ".gemini" / "settings.json"
    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
        hooks = settings.get("hooks", {})
        for event in ("BeforeTool", "SessionEnd"):
            event_hooks = hooks.get(event, [])
            hooks[event] = [
                h for h in event_hooks
                if "hedwig-cg" not in json.dumps(h)
                and "auto_rebuild" not in json.dumps(h)
            ]
            if not hooks[event]:
                hooks.pop(event, None)
        if not hooks:
            settings.pop("hooks", None)
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        human_ok("Hooks removed from .gemini/settings.json")

    human_done("hedwig-cg integration removed.")


# ─── Cursor IDE ──────────────────────────────────────────────────────────────

@click.group(name="cursor")
def cursor_group():
    """Manage per-project Cursor IDE integration."""
    pass


@cursor_group.command(name="install")
def cursor_install():
    """Install per-project Cursor integration (.cursor/rules/hedwig-cg.mdc)."""
    human_header("Installing hedwig-cg for Cursor IDE...")
    project_root = Path.cwd()

    rules_dir = project_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "hedwig-cg.mdc"

    rule_content = (
        "---\n"
        "description: hedwig-cg code graph search rules\n"
        "globs: **/*\n"
        "alwaysApply: true\n"
        "---\n\n"
        "# hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep/find if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-cg" in content:
            human_skip(".cursor/rules/hedwig-cg.mdc already exists")
        else:
            rules_file.write_text(rule_content)
            human_ok(".cursor/rules/hedwig-cg.mdc updated")
    else:
        rules_file.write_text(rule_content)
        human_ok(".cursor/rules/hedwig-cg.mdc created")

    human_done()


@cursor_group.command(name="uninstall")
def cursor_uninstall():
    """Remove per-project Cursor integration."""
    human_header("Removing hedwig-cg from Cursor IDE")
    project_root = Path.cwd()

    rules_file = project_root / ".cursor" / "rules" / "hedwig-cg.mdc"
    if rules_file.exists():
        rules_file.unlink()
        human_ok(".cursor/rules/hedwig-cg.mdc removed")
    else:
        human_skip(".cursor/rules/hedwig-cg.mdc not found")

    human_done("hedwig-cg integration removed.")


# ─── Windsurf IDE ────────────────────────────────────────────────────────────

@click.group(name="windsurf")
def windsurf_group():
    """Manage per-project Windsurf IDE integration."""
    pass


@windsurf_group.command(name="install")
def windsurf_install():
    """Install per-project Windsurf integration (.windsurf/rules/hedwig-cg.md)."""
    human_header("Installing hedwig-cg for Windsurf IDE...")
    project_root = Path.cwd()

    rules_dir = project_root / ".windsurf" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "hedwig-cg.md"

    rule_content = (
        "# hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep/find if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-cg" in content:
            human_skip(".windsurf/rules/hedwig-cg.md already exists")
        else:
            rules_file.write_text(rule_content)
            human_ok(".windsurf/rules/hedwig-cg.md updated")
    else:
        rules_file.write_text(rule_content)
        human_ok(".windsurf/rules/hedwig-cg.md created")

    human_done()


@windsurf_group.command(name="uninstall")
def windsurf_uninstall():
    """Remove per-project Windsurf integration."""
    human_header("Removing hedwig-cg from Windsurf IDE")
    project_root = Path.cwd()

    rules_file = project_root / ".windsurf" / "rules" / "hedwig-cg.md"
    if rules_file.exists():
        rules_file.unlink()
        human_ok(".windsurf/rules/hedwig-cg.md removed")
    else:
        human_skip(".windsurf/rules/hedwig-cg.md not found")

    human_done("hedwig-cg integration removed.")


# ─── Cline ───────────────────────────────────────────────────────────────────

@click.group(name="cline")
def cline_group():
    """Manage per-project Cline (VS Code extension) integration."""
    pass


@cline_group.command(name="install")
def cline_install():
    """Install per-project Cline integration (.clinerules)."""
    human_header("Installing hedwig-cg for Cline...")
    project_root = Path.cwd()

    rules_file = project_root / ".clinerules"

    rule_content = (
        "# hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep/find if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-cg" in content:
            human_skip(".clinerules section already exists")
        else:
            # Append to existing rules
            with open(rules_file, "a") as f:
                f.write("\n\n" + rule_content)
            human_ok("hedwig-cg section appended to .clinerules")
    else:
        rules_file.write_text(rule_content)
        human_ok(".clinerules created")

    human_done()


@cline_group.command(name="uninstall")
def cline_uninstall():
    """Remove per-project Cline integration."""
    human_header("Removing hedwig-cg from Cline")
    project_root = Path.cwd()

    rules_file = project_root / ".clinerules"
    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-cg" in content:
            # Remove hedwig-cg section
            lines = content.split("\n")
            filtered = []
            skip = False
            for line in lines:
                if line.strip() == "# hedwig-cg":
                    skip = True
                    continue
                if skip and line.startswith("# ") and "hedwig-cg" not in line:
                    skip = False
                if not skip:
                    filtered.append(line)
            new_content = "\n".join(filtered).strip()
            if new_content:
                rules_file.write_text(new_content + "\n")
                human_ok("hedwig-cg section removed from .clinerules")
            else:
                rules_file.unlink()
                human_ok(".clinerules removed (was only hedwig-cg content)")
        else:
            human_skip("No hedwig-cg section found in .clinerules")
    else:
        human_skip(".clinerules not found")

    human_done("hedwig-cg integration removed.")


# ─── Aider CLI ───────────────────────────────────────────────────────────────

@click.group(name="aider")
def aider_group():
    """Manage per-project Aider CLI integration."""
    pass


@aider_group.command(name="install")
def aider_install():
    """Install per-project Aider integration (CONVENTIONS.md + .aider.conf.yml)."""
    import yaml

    human_header("Installing hedwig-cg for Aider CLI...")
    project_root = Path.cwd()

    # 1. Write CONVENTIONS.md with hedwig-cg rules
    conventions_md = project_root / "CONVENTIONS.md"
    marker = "## hedwig-cg"
    section = (
        "\n## hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep/find if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    if conventions_md.exists():
        content = conventions_md.read_text()
        if marker in content:
            human_skip("CONVENTIONS.md section already exists")
        else:
            conventions_md.write_text(content + section)
            human_ok("hedwig-cg section added to CONVENTIONS.md")
    else:
        conventions_md.write_text(section.lstrip("\n"))
        human_ok("CONVENTIONS.md created")

    # 2. Ensure .aider.conf.yml loads CONVENTIONS.md via read:
    conf_file = project_root / ".aider.conf.yml"
    if conf_file.exists():
        conf = yaml.safe_load(conf_file.read_text()) or {}
    else:
        conf = {}

    read_list = conf.get("read", [])
    if isinstance(read_list, str):
        read_list = [read_list]
    if "CONVENTIONS.md" not in read_list:
        read_list.append("CONVENTIONS.md")
        conf["read"] = read_list
        conf_file.write_text(yaml.dump(conf, default_flow_style=False))
        human_ok("CONVENTIONS.md added to .aider.conf.yml read list")
    else:
        human_skip("CONVENTIONS.md already in .aider.conf.yml read list")

    human_done()


@aider_group.command(name="uninstall")
def aider_uninstall():
    """Remove per-project Aider integration."""
    import yaml

    human_header("Removing hedwig-cg from Aider CLI")
    project_root = Path.cwd()

    # 1. Remove section from CONVENTIONS.md
    conventions_md = project_root / "CONVENTIONS.md"
    if conventions_md.exists():
        lines = conventions_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-cg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-cg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        conventions_md.write_text(new_content)
        human_ok("hedwig-cg section removed from CONVENTIONS.md")

    # 2. Remove CONVENTIONS.md from .aider.conf.yml read list
    conf_file = project_root / ".aider.conf.yml"
    if conf_file.exists():
        conf = yaml.safe_load(conf_file.read_text()) or {}
        read_list = conf.get("read", [])
        if isinstance(read_list, str):
            read_list = [read_list]
        if "CONVENTIONS.md" in read_list:
            read_list.remove("CONVENTIONS.md")
            if read_list:
                conf["read"] = read_list
            else:
                conf.pop("read", None)
            if conf:
                conf_file.write_text(yaml.dump(conf, default_flow_style=False))
            else:
                conf_file.unlink()
            human_ok("CONVENTIONS.md removed from .aider.conf.yml read list")

    human_done("hedwig-cg integration removed.")


# ─── Register all groups ─────────────────────────────────────────────────────

def register_integration_commands(cli_group):
    """Register all integration subcommands on the given CLI group."""
    cli_group.add_command(claude_group)
    cli_group.add_command(codex_group)
    cli_group.add_command(gemini_group)
    cli_group.add_command(cursor_group)
    cli_group.add_command(windsurf_group)
    cli_group.add_command(cline_group)
    cli_group.add_command(aider_group)
