#!/usr/bin/env bash
# Install the hourly schedule for this checkout (Linux, systemd user units). Run once: bash deploy/install.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
CLAUDE_DIR="$(dirname "$(command -v claude)")"; NODE_DIR="$(dirname "$(command -v node)")"
sed -e "s|%h/yt-shorts|$REPO|g" -e "s|^Environment=PATH=.*|Environment=PATH=$CLAUDE_DIR:$NODE_DIR:/usr/local/bin:/usr/bin:/bin|" \
  "$REPO/deploy/shorts.service" > "$UNIT_DIR/shorts.service"
cp "$REPO/deploy/shorts.timer" "$UNIT_DIR/shorts.timer"
systemctl --user daemon-reload
systemctl --user enable --now shorts.timer
loginctl enable-linger "$USER" 2>/dev/null || sudo loginctl enable-linger "$USER" || true
echo "Hourly timer installed. Next run:"; systemctl --user list-timers shorts.timer --no-pager
echo "Logs: journalctl --user -u shorts -f"
