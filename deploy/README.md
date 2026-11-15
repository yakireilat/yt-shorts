# Running it every hour

## Linux (systemd user timer) — recommended
```bash
mkdir -p ~/.config/systemd/user
cp deploy/shorts.service deploy/shorts.timer ~/.config/systemd/user/
# edit WorkingDirectory/ExecStart if the repo is not at ~/yt-shorts, and PATH so `claude` and `node` resolve
systemctl --user daemon-reload
systemctl --user enable --now shorts.timer
loginctl enable-linger "$USER"        # keep running when you are logged out
journalctl --user -u shorts -f        # watch logs
```
Laptop: set lid-close to "do nothing" (`HandleLidSwitch=ignore` in /etc/systemd/logind.conf) and disable sleep.

## macOS / anything with cron
```cron
7 * * * * cd ~/yt-shorts && .venv/bin/python -m shorts run >> data/cron.log 2>&1
```
(cron has a minimal PATH: add `PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin` at the top of the crontab.)

## Windows
Use WSL2 (Ubuntu) and the systemd instructions above, or Task Scheduler running
`wsl -d Ubuntu -- bash -lc "cd ~/yt-shorts && .venv/bin/python -m shorts run"` hourly.

## No scheduler at all
```bash
.venv/bin/python -m shorts loop --every 3600
```
