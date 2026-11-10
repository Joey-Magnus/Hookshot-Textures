"""A HeapDef mod: the game's TextureHeap (and its parent, ゲームグラフィックス, which holds it) grown by `extra_kb`.

System/HeapSize/Product.Nin_Ounce_NVN2.HeapDef.byml.zs gives each heap's size in KB; the two sizes are patched in
place, every other byte stays as shipped. A texture pack larger than the originals needs room in TextureHeap
(2,457,600 KB as shipped), or the game keeps compacting and re-streaming textures.

The game's heap is 2,915 MB less than the memory Hookshot reports (HOS_MEMORY_MB, 9,809 by default: a 6,894 MB heap).
The heaps in this file leave less of it free than they seem to: +300 MB starts, +500 MB crashes at start (a segfault,
or an indirect call to the string "LocalDep" at +700). So raise HOS_MEMORY_MB (hookshot_env.txt) by extra_kb and some
to spare: with 10809, +700 MB plays (castle road, the lite pack, 90 s headless)."""
from __future__ import annotations

from pathlib import Path

from . import byml, zs

NAME = "System/HeapSize/Product.Nin_Ounce_NVN2.HeapDef.byml.zs"
TEXTURE = "TextureHeap"
GRAPHICS = "ゲームグラフィックス"
MEMORY_MB = 9809   # (Hookshot's default HOS_MEMORY_MB; the game's heap is then 6,894 MB)


def memory_mb(extra_kb: int) -> int:
    """the HOS_MEMORY_MB the mod needs, 300 MB to spare (+700 MB was tested with 10809)"""
    return MEMORY_MB + -(-extra_kb // 1024) + 300


def top_level_mb(heaps: dict) -> float:
    return sum(v["Size"] for v in heaps.values() if "Parent" not in v and v["Size"] > 0) / 1024


def write_mod(romfs: str, mod: Path, extra_kb: int) -> dict:
    data = zs.decompress(Path(romfs, NAME).read_bytes(), romfs)
    heaps = byml.parse(data)[0]["Heaps"]
    before = {k: heaps[k]["Size"] for k in (TEXTURE, GRAPHICS)}
    if heaps[TEXTURE].get("Parent") != GRAPHICS:
        raise ValueError("TextureHeap's parent is not ゲームグラフィックス: the file is not the one this was made for")
    for k in (TEXTURE, GRAPHICS):
        data = byml.patch_int(data, f"Heaps.{k}.Size", before[k] + extra_kb)
    heaps = byml.parse(data)[0]["Heaps"]
    out = mod / "romfs" / NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(zs.compress(data))
    return {"before_kb": before, "after_kb": {k: heaps[k]["Size"] for k in (TEXTURE, GRAPHICS)},
            "top_level_mb": top_level_mb(heaps), "memory_mb": memory_mb(extra_kb), "out": str(out)}
