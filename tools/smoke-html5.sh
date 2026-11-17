#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export JAVA_HOME="${HOME}/defold-tools/jdk-25.0.4.1+1"
export PATH="${JAVA_HOME}/bin:${PATH}"
BOB_JAR="${HOME}/defold-tools/bob.jar"
BUILD_SERVER="https://build.defold.com"

echo "=== [HTML5 Gate] Building wasm-web bundle via Cloud Extender ==="
rm -rf dist
java -jar "$BOB_JAR" \
  --platform wasm-web \
  --archive \
  --variant release \
  --build-server "$BUILD_SERVER" \
  --bundle-output dist \
  resolve distclean build bundle

INDEX_HTML="$(find dist -name "index.html" | head -n 1)"
WASM_FILE="$(find dist -name "*.wasm" | head -n 1)"
LOADER_JS="$(find dist -name "dmloader.js" | head -n 1)"

if [ -z "$INDEX_HTML" ] || [ -z "$WASM_FILE" ] || [ -z "$LOADER_JS" ]; then
  echo "FAIL: Missing HTML5 bundle artifacts in dist/!"
  ls -laR dist || true
  exit 1
fi

echo "PASS: HTML5 wasm-web bundle verified:"
ls -lh "$(dirname "$INDEX_HTML")"
