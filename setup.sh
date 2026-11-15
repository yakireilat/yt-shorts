#!/usr/bin/env bash
# One-time setup on the machine that will run the factory (Linux/macOS; on Windows use WSL2).
set -euo pipefail
cd "$(dirname "$0")"

need() { command -v "$1" >/dev/null || { echo "missing: $1 — $2"; exit 1; }; }
need python3 "install Python 3.11+"
need node    "install Node 20+ (https://nodejs.org)"
need ffmpeg  "sudo apt install ffmpeg  |  brew install ffmpeg"
need claude  "npm i -g @anthropic-ai/claude-code && claude   (log in with your Claude subscription once)"

python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

npm install --silent
npx playwright install chromium

mkdir -p models data out secrets assets/music
base=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
[ -f models/kokoro-v1.0.onnx ] || curl -L -o models/kokoro-v1.0.onnx $base/kokoro-v1.0.onnx
[ -f models/voices-v1.0.bin ]  || curl -L -o models/voices-v1.0.bin  $base/voices-v1.0.bin

echo
echo "Setup done. Next:"
echo "  1) .venv/bin/python -m shorts produce        # make your first short (no upload)"
echo "  2) put Google OAuth client JSON at secrets/client_secret.json, then: .venv/bin/python -m shorts auth"
echo "  3) set publish.enabled = true in config.toml"
echo "  4) install the hourly timer: see deploy/README.md"
