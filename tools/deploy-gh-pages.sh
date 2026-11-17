#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f "/tmp/.musou2d_github_env" ]; then
  echo "FAIL: /tmp/.musou2d_github_env not found."
  exit 1
fi

source /tmp/.musou2d_github_env
REPO_NAME="defold-musou2d"

INDEX_HTML="$(find dist -name "index.html" | head -n 1)"
if [ -z "$INDEX_HTML" ]; then
  echo "Building HTML5 bundle first..."
  ./tools/smoke-html5.sh
  INDEX_HTML="$(find dist -name "index.html" | head -n 1)"
fi

BUNDLE_DIR="$(dirname "$INDEX_HTML")"
echo "=== Deploying $BUNDLE_DIR to GitHub Pages (gh-pages branch) ==="

TMP_GH_PAGES="$(mktemp -d /tmp/musou2d_gh_pages.XXXXXX)"
trap 'rm -rf "$TMP_GH_PAGES"' EXIT

cp -r "$BUNDLE_DIR"/. "$TMP_GH_PAGES"/
touch "$TMP_GH_PAGES/.nojekyll"

pushd "$TMP_GH_PAGES" >/dev/null
git init -q
git checkout -q -b gh-pages
git config user.name "musou2d-lead"
git config user.email "musou2d-lead@agend.local"
git add -A
git commit -q -m "deploy: Defold HTML5 wasm-web bundle to GitHub Pages"
git push -q -f "https://${GITHUB_USER}:${GITHUB_PAT}@github.com/${GITHUB_USER}/${REPO_NAME}.git" gh-pages
popd >/dev/null

echo "=== Configuring GitHub Pages via REST API ==="
HTTP_CODE=$(curl -s -o /tmp/gh_pages_api.json -w "%{http_code}" \
  -X POST \
  -H "Authorization: token ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GITHUB_USER}/${REPO_NAME}/pages" \
  -d '{"source":{"branch":"gh-pages","path":"/"}}')
rm -f /tmp/gh_pages_api.json
echo "GitHub Pages API response code: ${HTTP_CODE} (201=created, 409=already enabled)"

echo "=== Successfully pushed gh-pages branch! ==="
