#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export JAVA_HOME="${HOME}/defold-tools/jdk-25.0.4.1+1"
export PATH="${JAVA_HOME}/bin:${PATH}"
BOB_JAR="${HOME}/defold-tools/bob.jar"
BUILD_SERVER="https://build.defold.com"
BUNDLE_DIR="dist_linux"

echo "=== [Clean-Boot Gate] Building x86_64-linux debug bundle with extension-spine ==="
rm -rf "$BUNDLE_DIR"
java -jar "$BOB_JAR" \
  --platform x86_64-linux \
  --archive \
  --variant debug \
  --build-server "$BUILD_SERVER" \
  --bundle-output "$BUNDLE_DIR" \
  resolve build bundle

ENGINE_BIN="$(find "$BUNDLE_DIR" -maxdepth 2 -type f -executable | head -n 1)"
if [ -z "$ENGINE_BIN" ]; then
  echo "FAIL: Could not find compiled Linux engine binary in $BUNDLE_DIR"
  exit 1
fi

ENGINE_DIR="$(dirname "$ENGINE_BIN")"
LOG_FILE="/tmp/musou2d_engine_boot.log"
rm -f "$LOG_FILE"

echo "=== Running engine binary ($ENGINE_BIN) to capture boot log ==="
set +e
(cd "$ENGINE_DIR" && timeout 4s "./$(basename "$ENGINE_BIN")" >"$LOG_FILE" 2>&1)
set -e

cat "$LOG_FILE"

if grep -E "Invalid mass|GAMESYS.*ERROR|ERROR:SCRIPT|ERROR:GAMEOBJECT|ERROR:SPINE|ERROR:RESOURCE|Failed to create|Lua error" "$LOG_FILE"; then
  echo "FAIL: Runtime engine boot error detected in log!"
  exit 1
fi

echo "PASS: Linux engine log clean-boot verified!"
