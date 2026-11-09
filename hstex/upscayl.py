"""2x upscaling on this PC's GPU with Upscayl's runner (upscayl-bin, Real-ESRGAN on ncnn + Vulkan) and Upscayl's
models: free, no account. The runner and the model are downloaded once into ~/.cache/hstex/upscayl. Upscayl's models are
4x networks; upscayl-bin's -s 2 brings their output to 2x."""
from __future__ import annotations

import io
import os
import platform
import subprocess
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

RELEASE = "20251207-174704"
BIN_URL = "https://github.com/upscayl/upscayl-ncnn/releases/download/{r}/upscayl-bin-{r}-{os}.zip"
MODEL_URL = "https://raw.githubusercontent.com/upscayl/upscayl/main/resources/models/{name}.{ext}"
HOME = Path(os.environ.get("HSTEX_UPSCAYL_DIR", Path.home() / ".cache/hstex/upscayl"))

# (the builder's --model names: Upscayl's model files)
MODELS = {
    "upscayl-ultrasharp": "ultrasharp-4x",
    "upscayl-hifi": "high-fidelity-4x",
    "upscayl-standard": "upscayl-standard-4x",
}

# (one network on the GPU at a time: two at once only share it, and each takes its own video memory)
_gpu = threading.Lock()
_setup = threading.Lock()


def _os() -> str:
    s = platform.system()
    return {"Linux": "linux", "Windows": "windows", "Darwin": "macos"}[s]


def _binary() -> Path:
    exe = "upscayl-bin.exe" if _os() == "windows" else "upscayl-bin"
    folder = HOME / f"upscayl-bin-{RELEASE}-{_os()}"
    path = folder / exe
    if not path.exists():
        data = urllib.request.urlopen(BIN_URL.format(r=RELEASE, os=_os()), timeout=120).read()
        zipfile.ZipFile(io.BytesIO(data)).extractall(HOME)
        if not path.exists():   # (a zip without the folder level)
            path = next(HOME.rglob(exe))
        path.chmod(0o755)
    return path


def _model(name: str) -> Path:
    models = HOME / "models"
    models.mkdir(parents=True, exist_ok=True)
    for ext in ("param", "bin"):
        f = models / f"{name}.{ext}"
        if not f.exists():
            tmp = f.with_suffix(f".{ext}.part")
            tmp.write_bytes(urllib.request.urlopen(MODEL_URL.format(name=name, ext=ext), timeout=300).read())
            tmp.rename(f)
    return models


def run(model: str, png: bytes) -> bytes:
    """A PNG upscaled 2x by one of MODELS, as PNG bytes."""
    name = MODELS[model]
    with _setup:
        exe, models = _binary(), _model(name)
    with tempfile.TemporaryDirectory(prefix="hstex-upscayl-") as d:
        src, dst = Path(d, "in.png"), Path(d, "out.png")
        src.write_bytes(png)
        with _gpu:
            r = subprocess.run([str(exe), "-i", str(src), "-o", str(dst), "-s", "2", "-m", str(models), "-n", name,
                                "-f", "png"], capture_output=True, text=True)
        if r.returncode != 0 or not dst.exists():
            raise RuntimeError(f"upscayl-bin failed ({r.returncode}): {(r.stderr or r.stdout)[-300:]}")
        return dst.read_bytes()
