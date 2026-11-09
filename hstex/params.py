"""Parameter mods: the game's BYML settings changed by key path and written into a mod folder.

  python3 -m hstex.params show <file> [key.path]      the file (RomFS-relative) as JSON, or one value in it
  python3 -m hstex.params build <overrides.yaml> <mod dir> [--romfs DIR]

overrides.yaml maps RomFS-relative files to {key path: value}:

  gsys/ModelSceneConfigParam/Main.gsys__ModelSceneConfigParam.bgyml:
    DepthShadowTexWidth: 2048
    SomeList[2].Value: 1.5

A value takes the BYML type of the one it replaces (2048 into a float key is written as a float). A key the file does not
have is an error unless written '+Key' (then it is added, typed from the YAML value). Files are read from the game's
RomFS, never from the mod, so a build always starts from the shipped values; a .zs file is written compressed again.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import byml, zs

ROMFS = os.path.expanduser("~/Games/OcarinaOfTime/romfs")


def read(romfs: str, rel: str):
    if ":" in rel:
        raise SystemExit("%s: files inside packs are not written yet (P3 adds SARC writing)" % rel)
    data = Path(romfs, rel).read_bytes()
    if rel.endswith(".zs"):
        data = zs.decompress(data, romfs)
    return byml.parse(data)


def build(overrides: dict, mod_dir: str, romfs: str = ROMFS) -> list[str]:
    report = []
    for rel, changes in overrides.items():
        root, version = read(romfs, rel)
        for path, value in (changes or {}).items():
            add = path.startswith("+")
            path = path.lstrip("+")
            old = byml.set_path(root, path, value, create=add)
            report.append("%s: %s %r -> %r" % (rel, path, old, byml.get_path(root, path)))
        out = byml.write(root, version)
        if byml.parse(out)[0] != root:
            raise SystemExit("%s: the written file does not read back the same" % rel)
        if rel.endswith(".zs"):
            out = zs.compress(out)
        dest = Path(mod_dir, "romfs", rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(out)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hstex.params", description=__doc__.split("\n")[0])
    ap.add_argument("--romfs", default=ROMFS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("file")
    s.add_argument("path", nargs="?")
    b = sub.add_parser("build")
    b.add_argument("overrides")
    b.add_argument("mod_dir")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        root, _ = read(a.romfs, a.file)
        v = byml.get_path(root, a.path) if a.path else root
        print(json.dumps(v, indent=1, default=lambda x: x.hex() if isinstance(x, bytes) else str(x)))
    else:
        import yaml
        overrides = yaml.safe_load(Path(a.overrides).read_text()) or {}
        for line in build(overrides, a.mod_dir, a.romfs):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
