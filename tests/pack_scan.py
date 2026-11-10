"""Scan a built pack: each texture's size, mip count, format, and whether its alpha is ever below 250 (cut-out or blended).
python -m tests.pack_scan <pack romfs/Tex> <out.json> [--jobs N]"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import etcpak
import numpy as np

from hstex import bntx, zs


def scan(path: str):
    f = Path(path)
    raw = zs.decompress(f.read_bytes(), "")
    t = bntx.parse(raw)
    out = {"name": f.name, "w": t.width, "h": t.height, "mips": t.mips, "fmt": t.fmt_name, "bytes": len(raw)}
    try:
        rgba = bntx.decode_mip0(t)
        a = rgba[..., 3]
        out["alpha_min"] = int(a.min())
        out["alpha_cut"] = float((a < 250).mean())
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)[:120]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tex")
    ap.add_argument("out")
    ap.add_argument("--jobs", type=int, default=12)
    a = ap.parse_args()
    files = sorted(str(p) for p in Path(a.tex).glob("*.bntx.zs"))
    with ProcessPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(scan, files, chunksize=16))
    json.dump(rows, open(a.out, "w"))
    print(len(rows), "scanned;", sum(1 for r in rows if "error" in r), "errors")


if __name__ == "__main__":
    main()
