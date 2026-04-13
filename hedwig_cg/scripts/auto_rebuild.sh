#!/bin/sh
# hedwig-cg auto-rebuild: runs incremental build if source files changed.
# Called by Stop/SessionEnd hooks from AI coding agents.
# Runs in background to avoid blocking the agent.

[ -f .hedwig-cg/knowledge.db ] || exit 0

# Check if any tracked source files changed (unstaged or staged)
CHANGED=$(git diff --name-only HEAD 2>/dev/null | grep -E '\.(py|js|jsx|ts|tsx|java|go|rs|c|h|cpp|hpp|rb|md|html|csv|pdf)$' | head -1)

if [ -n "$CHANGED" ]; then
    hedwig-cg build . --incremental >/dev/null 2>&1 &
fi
