"""A headless game run for parameter A/B tests (P2/P3): the player's save copied, its own mods folder, env file and log.

  python3 tests/p2_run.py <name> [--overrides file.yaml] [--seconds 300] [--env KEY=VALUE ...]

Writes work/params/runs/<name>/: shots/*.png (every RX_VK_SHOT_EVERY presents), run.log, mod/ (the built mod, if any).
The save (a copy in work/params/user) loads in Kokiri Forest with A presses from 20 s on. Waits while any game is running
(another test, or the player): the shader caches beside the game are shared.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hstex import params  # noqa: E402

GAME = Path.home() / "Games/OcarinaOfTime"
WORK = Path(__file__).resolve().parents[1] / "work/params"
SAVE = Path.home() / ".local/share/hookshot/save"

BASE_ENV = {
    "HOS_HEADLESS": "1",
    "RX_VK_SHOT_EVERY": "300",
    "RX_VK_ANISO": "16",
    "HOS_AUDIO_MUTE": "1",
    "HOS_FIXED_TIME": "1786000000",
    "RX_VK_PASS_TIMING": "1",
    "RX_VK_LOG_CASCADE_BIAS": "1",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--overrides")
    ap.add_argument("--seconds", type=int, default=300)
    ap.add_argument("--env", action="append", default=[])
    a = ap.parse_args()

    waited = 0
    while subprocess.run(["pgrep", "-x", "hookshot"], capture_output=True).returncode == 0:   # (another run: wait)
        if waited % 300 == 0:
            print("the game is running (another test?): waiting", flush=True)
        time.sleep(15)
        waited += 15
    time.sleep(5 if waited else 0)
    run = WORK / "runs" / a.name
    if run.exists():
        shutil.rmtree(run)
    (run / "shots").mkdir(parents=True)
    mods = run / "mods"
    mods.mkdir()
    if a.overrides:
        import yaml
        report = params.build(yaml.safe_load(Path(a.overrides).read_text()), str(mods / "02-Shadows-test"))
        (run / "overrides.txt").write_text("\n".join(report) + "\n")
        shutil.copy(a.overrides, run / "overrides.yaml")

    user = run / "user"   # (a fresh copy each run: the game may save)
    shutil.copytree(SAVE, user / "save")

    env = dict(BASE_ENV, RX_VK_SHOTS=str(run / "shots"), HOS_MODS=str(mods))
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    (run / "run.env").write_text("".join("%s=%s\n" % kv for kv in env.items()))
    script = ",".join("%d:A" % t for t in range(20, 170, 6))
    proc_env = dict(os.environ, HOS_ENV_FILE=str(run / "run.env"), HOS_INPUT_SCRIPT=script)
    with open(run / "run.log", "w") as log:
        try:
            subprocess.run(["./hookshot", "--user", str(user)], cwd=GAME, env=proc_env, stdout=log, stderr=log,
                           timeout=a.seconds)
        except subprocess.TimeoutExpired:
            pass
    shutil.rmtree(user, ignore_errors=True)
    print(run, len(list((run / "shots").glob("*.png"))), "shots")


if __name__ == "__main__":
    main()
