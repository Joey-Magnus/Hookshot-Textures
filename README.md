# Hookshot-Textures

An HD texture pack builder for *The Legend of Zelda: Ocarina of Time* (Nintendo Switch 2) running on
[Hookshot](https://github.com/NotRexed/Hookshot). It reads the colour textures from **your own** game files, upscales them
2x with an AI model on [fal.ai](https://fal.ai), and writes them back as a Hookshot RomFS mod.

**No game data is in this repository, and none should leave your PC.** The pack you build is made from Nintendo's
textures: keep it to yourself, as Hookshot's
[CONTRIBUTING.md](https://github.com/NotRexed/Hookshot/blob/main/CONTRIBUTING.md) asks for anything made from the game.

## What it does

1. Reads `romfs/Tex/*_Alb.bntx.zs` (zstd with the game's `ZsDic` dictionaries), parses BNTX/BRTI, unswizzles the Switch 2
   block-linear layout and decodes ASTC / BC1-7.
2. Upscales each colour (Alb) texture 2x on fal.ai. Tiling textures are wrap-padded first so no seams appear; alpha is
   resized apart (Lanczos) so the model never sees it. Results are cached by input hash, so a rebuild costs nothing.
3. Builds a linear-light mip chain, encodes BC7 (sRGB kept: desktop GPUs sample it natively), swizzles, rewrites the
   BNTX header and compresses with zstd.
4. Grows the game's **resource size table** so the bigger files load (see below), and installs the pack as
   `mods/01-HD-Textures`.

Normal, roughness, AO and metal maps are data, not pictures, and stay at their size.

## Requirements

- Python 3.11+ and `pip install -r requirements.txt`
- A Hookshot game folder (`hookshot`, `romfs/`), built from your own copy of the game
- A fal.ai API key in `~/.config/fal/key` (`chmod 600` it)

## Use

```sh
# a small area first: Kokiri Forest, 325 textures (about $8 and 10 minutes with topaz-std)
python -m hstex.cli build --model topaz-std --match kokiri --out work/packs/01-HD-Textures \
    --romfs ~/Games/OcarinaOfTime/romfs
python -m hstex.cli install work/packs/01-HD-Textures --game ~/Games/OcarinaOfTime

# then the rest into the same pack: what is already built is skipped
python -m hstex.cli build --model topaz-std --out work/packs/01-HD-Textures --romfs ~/Games/OcarinaOfTime/romfs
```

`--model`: `topaz-std` (Topaz Standard V2: the most faithful detail, the default to use), `seedvr` (cheaper, invents
patterns), `topaz-cgi` (over-paints), `esrgan` (close to plain resizing). `--jobs` sets parallel calls, `--limit` caps
how many textures one run builds. The full set is about 4,900 textures, roughly 2.5 hours at `--jobs 12`.

Restart the game after installing (Hookshot indexes mods at start). `hookshot_log.txt` lists the mod and its files. Rename
the folder with a leading `_` to turn it off.

## The resource size table

`romfs/System/Resource/ResourceSizeTable.Product.111.Nin_Ounce_NVN2.rsizetable.zs` ("RESTBL") gives each file's memory
size by CRC32 of its path (without `.zs`); for textures it is the decompressed size + 280. A file larger than its entry
**silently does not load**: the game keeps the original, or a loading screen waits forever. The builder writes a grown
copy of the table into the pack (`hstex/rstb.py`).

Hookshot replaces whole files, and the mod whose folder sorts last wins, so only one mod's table is used. If you combine
this pack with other mods that grow files, their entries must be merged into one table in the last mod.

## Switch 2 texture layout

The Switch 2 GOB (512-byte block-linear tile) swaps two bits against the Switch 1 layout (row bit 1 and column bit 4):
see `hstex/bntx.py`. With the Switch 1 order, about 0.5% of ASTC blocks decode as invalid and textures smear.

## Also here

`hstex/byml.py` and `hstex/params.py`: BYML v7 read/write (loose, `.zs`, inside `.pack.zs` SARCs) and a parameter mod
builder, for shadow and draw-distance mods. `tests/` holds round-trip checks and headless Hookshot run helpers (their
paths are this author's; adjust them).
