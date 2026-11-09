#!/usr/bin/env bash
# Headless run into gameplay from the latest save: [GAME=<game folder>] ./headless_run.sh <mods dir> [extra env...]
# Presses A (Continue, the newest save, Load) until a frame has gameplay's draw count, then waits 30 s more.
# Frames every 2 s in /tmp/oot-shots, console in /tmp/oot-run.out, the last frame at /tmp/oot-s.png.
# Leaves the game running; kill -9 $(cat /tmp/oot-headless.pid) to stop.
set -euo pipefail
mods=$1; shift
# (the game does not exit on SIGTERM, so a run left behind is killed: only this script's own, by its PID file.
# Other tools (tests/p2_run.py) run the game too and wait while one runs: wait for theirs to finish likewise)
PIDFILE=/tmp/oot-headless.pid
if [ -f $PIDFILE ]; then kill -9 "$(cat $PIDFILE)" 2>/dev/null || true; rm -f $PIDFILE; fi
while pgrep -x hookshot >/dev/null; do sleep 2; done
rm -rf /tmp/oot-shots && mkdir -p /tmp/oot-shots && : > /tmp/oot-live.txt
cd "${GAME:-$HOME/Games/OcarinaOfTime}"
env HOS_HEADLESS=1 HOS_MODS="$mods" RX_VK_SHOTS=/tmp/oot-shots RX_VK_SHOT_EVERY=120 HOS_INPUT_LIVE=/tmp/oot-live.txt \
    HOS_INPUT_SCRIPT_BACKGROUND=1 RX_VK_ANISO=16 "$@" setsid ./hookshot </dev/null >/tmp/oot-run.out 2>&1 &
echo $! > $PIDFILE
draws() { rg -o 'presents, [0-9.]+ fps; a frame: ([0-9]+) draws' -r '$1' /tmp/oot-run.out | tail -1 || true; }
sleep 35
for i in $(seq 1 30); do
    d=$(draws); [ "${d:-0}" -gt 1000 ] && break
    echo "0:A/400" >> /tmp/oot-live.txt
    sleep 8
done
echo "gameplay after $((35 + i * 8)) s ($(draws) draws a frame)"
sleep 30
cd /tmp
python3 - <<'EOF'
from PIL import Image
import os
d = '/tmp/oot-shots'
f = sorted(os.listdir(d))[-1]
Image.open(os.path.join(d, f)).convert('RGB').resize((960, 540)).save('/tmp/oot-s.png')
print('last shot', f)
EOF
