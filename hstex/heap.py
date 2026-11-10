"""A HeapDef mod: the game's TextureHeap (and its parent, ゲームグラフィックス, which holds it) grown by `extra_kb`.

System/HeapSize/Product.Nin_Ounce_NVN2.HeapDef.byml.zs gives each heap's size in KB. The top-level heaps add up to
6,026 MB of the 6,894 MB Hookshot gives the game's heap, so ~870 MB is free; a texture pack larger than the originals
needs some of it in TextureHeap (2,457,600 KB as shipped), or the game keeps compacting and re-streaming textures."""
from __future__ import annotations

from pathlib import Path

from . import byml, zs

NAME = "System/HeapSize/Product.Nin_Ounce_NVN2.HeapDef.byml.zs"
TEXTURE = "TextureHeap"
GRAPHICS = "ゲームグラフィックス"
GAME_HEAP_MB = 6894   # (what Hookshot gives: its log's "heap: 6894 MB")


def _load(blob: bytes):
    """(root, version), as byml.parse gives them"""
    return byml.parse(blob)


def _dump(doc) -> bytes:
    root, version = doc
    return byml.write(root, version)


def top_level_mb(heaps: dict) -> float:
    return sum(v["Size"] for v in heaps.values() if "Parent" not in v and v["Size"] > 0) / 1024


def write_mod(romfs: str, mod: Path, extra_kb: int) -> dict:
    doc = _load(zs.decompress(Path(romfs, NAME).read_bytes(), romfs))
    heaps = doc[0]["Heaps"]
    before = {k: heaps[k]["Size"] for k in (TEXTURE, GRAPHICS)}
    if heaps[TEXTURE].get("Parent") != GRAPHICS:
        raise ValueError("TextureHeap's parent is not ゲームグラフィックス: the file is not the one this was made for")
    heaps[TEXTURE]["Size"] += extra_kb
    heaps[GRAPHICS]["Size"] += extra_kb
    total = top_level_mb(heaps)
    if total > GAME_HEAP_MB - 64:
        raise ValueError(f"the top-level heaps would be {total:.0f} MB of the game's {GAME_HEAP_MB} MB")
    out = mod / "romfs" / NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(zs.compress(_dump(doc)))
    return {"before_kb": before, "after_kb": {k: heaps[k]["Size"] for k in (TEXTURE, GRAPHICS)}, "top_level_mb": total,
            "out": str(out)}
