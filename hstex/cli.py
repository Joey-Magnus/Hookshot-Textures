"""hstex: Hookshot OoT texture packs.

  python -m hstex.cli build [--model upscayl-ultrasharp] --out work/packs/01-HD-Textures [--match REGEX] [--limit N]
  python -m hstex.cli install work/packs/01-HD-Textures [--game ~/Games/OcarinaOfTime]
  python -m hstex.cli rstb [--game ~/Games/OcarinaOfTime]

rstb: mods/99-ResourceSizeTable rebuilt from the game's table and every enabled mod (install runs it too). Run it after
a mod is added, removed or turned on or off.

build: every single-layer Alb texture (or those matching --match) upscaled 2x, BC7, written to <out>/romfs/Tex.
--model: upscayl-* run free on this PC's GPU (Upscayl, downloaded on first use); the others are paid fal.ai models
(key in ~/.config/fal/key). Textures already in <out> are skipped, so a stopped run resumes; upscaled results are cached
by input, so a rebuild costs nothing. --limit: at most N textures this run (a spend cap with fal.ai).
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from . import bntx, encode, fal, rstb, upscayl, zs

GAME = Path.home() / "Games/OcarinaOfTime"


def build(args) -> int:
    romfs = str(Path(args.romfs))
    out = Path(args.out, "romfs/Tex")
    out.mkdir(parents=True, exist_ok=True)
    pat = re.compile(args.match, re.I) if args.match else None
    todo = [p for p in sorted(Path(romfs, "Tex").glob(f"*_{args.kind}*.bntx.zs"))
            if (not pat or pat.search(p.name)) and not (out / p.name).exists()]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(todo)} textures to build with {args.model}", flush=True)
    lock, done, skipped, failed = threading.Lock(), [0], [0], []
    t0 = time.time()

    def one(p: Path, client: httpx.Client):
        t = bntx.parse(zs.decompress(p.read_bytes(), romfs))
        if t.layers != 1 or t.depth != 1 or t.fmt_type not in bntx.FORMATS:
            return False
        up = fal.upscale2x(bntx.decode_mip0(t), args.model, client)
        data = zs.compress(encode.encode_bc7(t, up), level=args.zstd)
        tmp = out / (p.name + ".tmp")
        tmp.write_bytes(data)
        tmp.rename(out / p.name)
        return True

    with httpx.Client() as client, ThreadPoolExecutor(args.jobs) as ex:
        futs = {ex.submit(one, p, client): p for p in todo}
        for f in as_completed(futs):
            with lock:
                try:
                    (done if f.result() else skipped)[0] += 1
                except Exception as e:  # noqa: BLE001
                    failed.append((futs[f].name, str(e)[:160]))
                n = done[0] + skipped[0] + len(failed)
                if n % 25 == 0 or n == len(todo):
                    rate = n / max(1e-6, time.time() - t0)
                    print(f"{n}/{len(todo)} built {done[0]}, skipped {skipped[0]}, failed {len(failed)}; "
                          f"{rate * 60:.0f}/min, {(len(todo) - n) / max(rate, 1e-6) / 60:.0f} min left", flush=True)
    for name, err in failed:
        print("FAILED", name, err)
    grown = rstb.Rstb.load(romfs).fit_mod(args.out)
    print(f"resource size table: {grown} entries grown", flush=True)
    return 1 if failed else 0


def install(args) -> int:
    pack = Path(args.pack)
    dest = Path(args.game, "mods", pack.name)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(pack, dest)
    n = sum(1 for _ in dest.rglob("*.bntx.zs"))
    print(f"{n} textures installed in {dest} (rename it with a leading '_' to turn it off)")
    return rstb_cmd(args)


def rstb_cmd(args) -> int:
    """mods/99-ResourceSizeTable from the game's table and every enabled mod (see rstb.regenerate)"""
    r = rstb.regenerate(args.game, getattr(args, "romfs", None))
    for name, files in r["mods"]:
        print(f"  {name}: {files} files" + ("  (its own size table merged)" if name in r["tables"] else ""))
    print(f"resource size table: {r['grown']} entries grown, written to {r['out']}; restart the game", flush=True)
    return 0


def lite_cmd(args) -> int:
    """A pack sized to the texture heap, from a full 2x pack (hstex/lite.py)"""
    from concurrent.futures import ProcessPoolExecutor
    from . import lite
    full_tex = Path(args.full, "romfs/Tex")
    out_tex = Path(args.out, "romfs/Tex")
    out_tex.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in full_tex.glob("*.bntx.zs"))
    counts: dict[str, int] = {}
    grow = 0
    t0 = time.time()
    with ProcessPoolExecutor(args.jobs) as ex:
        futs = [ex.submit(lite.build_one, n, args.romfs, full_tex, out_tex, args.max_orig, args.zstd) for n in names]
        for i, f in enumerate(futs, 1):
            r = f.result()
            counts[r.action] = counts.get(r.action, 0) + 1
            grow += r.new_bytes - r.orig_bytes
            if i % 250 == 0 or i == len(futs):
                print(f"{i}/{len(futs)} {counts} growth {grow / 2**20:.0f} MB, {time.time() - t0:.0f} s", flush=True)
    return 0


def heap_cmd(args) -> int:
    from . import heap
    r = heap.write_mod(args.romfs, Path(args.game, "mods", args.name), args.extra_mb * 1024)
    print(f"TextureHeap {r['before_kb']['TextureHeap']} -> {r['after_kb']['TextureHeap']} KB; top-level heaps "
          f"{r['top_level_mb']:.0f} MB; {r['out']}")
    print(f"needs HOS_MEMORY_MB={r['memory_mb']} (or more) in the game's hookshot_env.txt: without it the game crashes "
          f"at start past about +300 MB")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="hstex")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--model", default="upscayl-ultrasharp", choices=sorted(upscayl.MODELS) + sorted(fal.MODELS))
    b.add_argument("--out", required=True)
    b.add_argument("--romfs", default=str(GAME / "romfs"))
    b.add_argument("--kind", default="Alb")
    b.add_argument("--match")
    b.add_argument("--limit", type=int)
    b.add_argument("--jobs", type=int, default=8)
    b.add_argument("--zstd", type=int, default=12)
    i = sub.add_parser("install")
    i.add_argument("pack")
    i.add_argument("--game", default=str(GAME))
    r = sub.add_parser("rstb", help="rebuild mods/99-ResourceSizeTable from every enabled mod (after a mod is added, "
                                    "removed or turned on or off)")
    r.add_argument("--game", default=str(GAME))
    r.add_argument("--romfs", help="the game's own romfs (default: <game>/romfs)")
    lt = sub.add_parser("lite", help="a pack sized to the game's texture heap, from a full 2x pack")
    lt.add_argument("--full", required=True, help="the full 2x pack (its folder, with romfs/Tex)")
    lt.add_argument("--out", required=True)
    lt.add_argument("--romfs", default=str(GAME / "romfs"))
    lt.add_argument("--max-orig", type=int, default=512, help="2x only for originals up to this many pixels a side")
    lt.add_argument("--jobs", type=int, default=12)
    lt.add_argument("--zstd", type=int, default=12)
    hp = sub.add_parser("heap", help="a HeapDef mod giving TextureHeap more of the game's heap")
    hp.add_argument("--game", default=str(GAME))
    hp.add_argument("--romfs", default=str(GAME / "romfs"))
    hp.add_argument("--name", default="05-HeapSize")
    hp.add_argument("--extra-mb", type=int, default=700)
    args = ap.parse_args()
    return {"build": build, "install": install, "rstb": rstb_cmd, "lite": lite_cmd, "heap": heap_cmd}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
