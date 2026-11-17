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
# Local (rootless) fallback for libGLU/libOpenGL: extract via `apt-get download` + `dpkg -x` into $LOCAL_GL_LIBS
LOCAL_GL_LIBS="${LOCAL_GL_LIBS:-${HOME}/defold-tools/libs/root/usr/lib/x86_64-linux-gnu}"
if [ -d "$LOCAL_GL_LIBS" ]; then
  export LD_LIBRARY_PATH="${LOCAL_GL_LIBS}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
(cd "$ENGINE_DIR" && timeout 6s "./$(basename "$ENGINE_BIN")" >"$LOG_FILE" 2>&1)
ENGINE_EXIT=$?
set -e

cat "$LOG_FILE"

# Engine must still be running when timeout kills it (exit 124); anything else = crash / failed to launch
if [ "$ENGINE_EXIT" -ne 124 ]; then
  echo "FAIL: Engine exited early with code $ENGINE_EXIT (expected 124 = still running at timeout)"
  exit 1
fi

for marker in "Defold Engine" "Loading data from" "Registered spine extension"; do
  if ! grep -q "$marker" "$LOG_FILE"; then
    echo "FAIL: Expected boot marker not found in log: '$marker'"
    exit 1
  fi
done

if grep -E "error while loading shared libraries|Segmentation fault|Invalid mass|GAMESYS.*ERROR|ERROR:SCRIPT|ERROR:GAMEOBJECT|ERROR:SPINE|ERROR:RESOURCE|Failed to create|Lua error" "$LOG_FILE"; then
  echo "FAIL: Runtime engine boot error detected in log!"
  exit 1
fi

echo "PASS: Linux engine log clean-boot verified!"
