#!/usr/bin/env bash
# Open a 3D view of the probe in the browser.
#
#   ./start.sh            the CURRENT probe (cad/tools/view.py --scene probe)
#   ./start.sh <scene>    another current scene: bed, head-end, print, ...
#                         (list them with: python3 ../cad/tools/view.py --list)
#   ./start.sh legacy     this directory's React viewer of the SUPERSEDED Rev-A
#                         geometry, on http://localhost:3333/
#
# The current viewer lives in ../cad/viewer and renders its meshes from the
# OpenSCAD model; this React app hard-codes the old dimensions. See README.md.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" != "legacy" ]]; then
  exec python3 ../cad/tools/view.py --scene "${1:-probe}"
fi

# --- legacy React viewer ---------------------------------------------------
# Needs Vite: a plain static server (python -m http.server) serves
# /src/main.tsx uncompiled and the page stays blank.
PORT="${PORT:-3333}"
URL="http://localhost:${PORT}/"

# Already running? Just open it.
if curl -fsS -m 2 -o /dev/null "${URL}src/main.tsx" 2>/dev/null; then
  echo "Legacy viewer already running at ${URL}"
  open "$URL"
  exit 0
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port ${PORT} is taken by something that is not this viewer:" >&2
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >&2
  echo "Stop it, or run with PORT=<other> $0 legacy" >&2
  exit 1
fi

if [[ ! -x node_modules/.bin/vite ]]; then
  echo "Installing dependencies..."
  # --no-package-lock: the tracked lockfile is out of sync with package.json
  # (missing some @rolldown platform bindings), and a plain install rewrites it.
  npm install --no-package-lock
fi

exec node_modules/.bin/vite --host 127.0.0.1 --port "$PORT" --strictPort --open
