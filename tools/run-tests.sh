#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== [Gate 1] Static Guard: Forbid dofile / loadfile / io.open / dynamic require in runtime Lua ==="
if find main shared player enemy hud -type f \( -name "*.lua" -o -name "*.script" -o -name "*.gui_script" \) 2>/dev/null | xargs -r grep -nE '\b(dofile|loadfile)\s*\(|io\.open\s*\('; then
  echo "FAIL: Forbidden filesystem call (dofile/loadfile/io.open) detected in runtime scripts!"
  exit 1
fi
if find main shared player enemy hud -type f \( -name "*.lua" -o -name "*.script" -o -name "*.gui_script" \) 2>/dev/null | xargs -r grep -nE 'require\s*\(\s*[^"'\'']'; then
  echo "FAIL: Dynamic require(variable) detected in runtime scripts! Use string literals only."
  exit 1
fi
echo "PASS: Static guard clean."

echo "=== [Gate 2] Spine Auto-Rigging Pipeline Verification ==="
if [ -f "test/test_spine_pipeline.py" ]; then
  python3 test/test_spine_pipeline.py
else
  echo "WARN: test/test_spine_pipeline.py not yet present."
fi

echo "=== [Gate 3] Pure-Lua Headless Unit & Action Smoke Tests ==="
LUA_BIN="${HOME}/defold-tools/lua"
if [ ! -x "$LUA_BIN" ]; then
  LUA_BIN="lua"
fi
if [ -f "test/runner.lua" ]; then
  "$LUA_BIN" test/runner.lua
else
  echo "WARN: test/runner.lua not yet present."
fi

echo "=== ALL HEADLESS TESTS PASSED ==="
