"""The fal.ai pilot: ~30 Kokiri Forest Alb textures through each model; a comparison sheet per texture (the same crop
from Lanczos 2x and each model, nearest-neighbour enlarged) in work/pilot."""
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hstex import bntx, fal, zs  # noqa: E402

ROMFS = "/home/voidm/Games/OcarinaOfTime/romfs"
OUT = Path(__file__).resolve().parents[1] / "work/pilot"
MODELS = sys.argv[1].split(",") if len(sys.argv) > 1 else list(fal.MODELS)
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 30


def pick() -> list[Path]:
    files = sorted(p for p in Path(ROMFS, "Tex").glob("*Kokiri*_Alb.bntx.zs"))
    random.seed(7)
    random.shuffle(files)
    out = []
    for p in files:
        t = bntx.parse(zs.decompress(p.read_bytes(), ROMFS))
        if t.layers == 1 and 256 <= max(t.width, t.height) <= 1024:
            out.append(p)
        if len(out) == COUNT:
            break
    return out


def sheet(name: str, src: np.ndarray, results: dict[str, np.ndarray]) -> None:
    h, w = src.shape[:2]
    c = min(128, w // 2, h // 2)
    y, x = (2 * h - 2 * c) // 2, (2 * w - 2 * c) // 2
    lanczos = np.asarray(Image.fromarray(src).resize((2 * w, 2 * h), Image.LANCZOS))
    tiles = [("lanczos", lanczos)] + list(results.items())
    size = 384
    im = Image.new("RGB", (size * len(tiles), size + 24), "black")
    d = ImageDraw.Draw(im)
    for i, (label, a) in enumerate(tiles):
        crop = Image.fromarray(a[y:y + 2 * c, x:x + 2 * c, :3]).resize((size, size), Image.NEAREST)
        im.paste(crop, (i * size, 24))
        d.text((i * size + 6, 5), label, fill="white")
    im.save(OUT / f"{name}.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = pick()
    print(len(files), "textures:", ", ".join(p.name.split(".")[0] for p in files))
    srcs = {p.name.split(".")[0]: bntx.decode_mip0(bntx.parse(zs.decompress(p.read_bytes(), ROMFS))) for p in files}
    jobs = [(n, m) for n in srcs for m in MODELS]
    results: dict[str, dict[str, np.ndarray]] = {n: {} for n in srcs}
    failures = []
    with httpx.Client() as client, ThreadPoolExecutor(8) as ex:
        def run(job):
            n, m = job
            try:
                return n, m, fal.upscale2x(srcs[n], m, client)
            except Exception as e:  # noqa: BLE001
                return n, m, e
        for n, m, r in ex.map(run, jobs):
            if isinstance(r, Exception):
                failures.append((n, m, str(r)[:160]))
            else:
                results[n][m] = r
    for n, src in srcs.items():
        sheet(n, src, results[n])
    print("sheets in", OUT)
    for f in failures:
        print("FAILED", *f)


if __name__ == "__main__":
    main()
