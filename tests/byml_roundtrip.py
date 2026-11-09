"""Every BYML in the RomFS (loose, .zs, and inside .pack.zs SARCs) parsed, written, parsed again: the same values and
types. Reports how many came out byte-identical. python3 tests/byml_roundtrip.py [romfs] [--limit N]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from hstex.byml import parse, write          # noqa: E402
from hstex.zs import decompress, sarc_files  # noqa: E402

SKIP = ("/Tex", "/Model", "/Sound", "/Movie", "/Voice", "/Shader", "/Font2")


def same(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a) if set(a) == set(b) else False
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, bytes) and getattr(a, "align", 4) != getattr(b, "align", 4):
        return False
    if isinstance(a, float) and a != a:
        return b != b
    return a == b


def files(romfs):
    for root, _, fs in os.walk(romfs):
        if any(s in root for s in SKIP):
            continue
        for f in sorted(fs):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, romfs)
            try:
                b = open(p, "rb").read()
                if f.endswith(".zs"):
                    b = decompress(b, romfs)
            except Exception:
                continue
            if b[:4] == b"SARC":
                for n, x in sarc_files(b).items():
                    if x[:4] == b"(\xb5/\xfd":
                        try:
                            x = decompress(x, romfs)
                        except Exception:
                            continue
                    if x[:2] == b"YB":
                        yield rel + ":" + n, x
            elif b[:2] == b"YB":
                yield rel, b


def main():
    romfs = next((a for a in sys.argv[1:] if not a.startswith("--") and not a.isdigit()),
                 os.path.expanduser("~/Games/OcarinaOfTime/romfs"))
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    n = ident = 0
    bad = []
    for name, b in files(romfs):
        n += 1
        try:
            v, ver = parse(b)
            w = write(v, ver)
            if not same(v, parse(w)[0]):
                bad.append((name, "values differ"))
            elif w == b:
                ident += 1
        except Exception as e:
            bad.append((name, repr(e)[:120]))
        if limit and n >= limit:
            break
    print("%d files, %d byte-identical, %d failed" % (n, ident, len(bad)))
    for name, why in bad[:20]:
        print("  FAIL", name, why)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
