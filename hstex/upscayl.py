"""2x upscaling on this PC's GPU with Upscayl's runner (upscayl-bin, Real-ESRGAN on ncnn + Vulkan) and Upscayl's
models: free, no account. The runner and the model are downloaded once into ~/.cache/hstex/upscayl. Upscayl's models are
4x networks; upscayl-bin's -s 2 brings their output to 2x."""
from __future__ import annotations

import io
import os
import platform
import queue
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import Future
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

BATCH = 16          # (images per upscayl-bin run: it loads the model once a run, which costs more than a small image)
WAIT = 1.0          # (s: how long a batch waits to fill once it has one image)

_setup = threading.Lock()
_queue: "queue.Queue[tuple[str, bytes, Future]]" = queue.Queue()
_worker: threading.Thread | None = None


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


def _run_batch(name: str, items: list[tuple[bytes, Future]]) -> None:
    exe, models = _binary(), _model(name)
    with tempfile.TemporaryDirectory(prefix="hstex-upscayl-") as d:
        src, dst = Path(d, "in"), Path(d, "out")
        src.mkdir()
        dst.mkdir()
        for i, (png, _) in enumerate(items):
            (src / f"{i}.png").write_bytes(png)
        r = subprocess.run([str(exe), "-i", str(src), "-o", str(dst), "-s", "2", "-m", str(models), "-n", name,
                            "-f", "png"], capture_output=True, text=True)
        for i, (_, fut) in enumerate(items):
            out = dst / f"{i}.png"
            if out.exists():
                fut.set_result(out.read_bytes())
            else:
                fut.set_exception(RuntimeError(f"upscayl-bin failed ({r.returncode}): {(r.stderr or r.stdout)[-300:]}"))


def _work() -> None:
    """The one GPU worker: batches of up to BATCH images of one model (two networks at once only share the GPU)."""
    while True:
        first = _queue.get()
        batch, deadline = [first], time.monotonic() + WAIT
        while len(batch) < BATCH:
            try:
                batch.append(_queue.get(timeout=max(0.0, deadline - time.monotonic())))
            except queue.Empty:
                break
        by_model: dict[str, list[tuple[bytes, Future]]] = {}
        for model, png, fut in batch:
            by_model.setdefault(MODELS[model], []).append((png, fut))
        for name, items in by_model.items():
            try:
                _run_batch(name, items)
            except Exception as e:  # noqa: BLE001
                for _, fut in items:
                    if not fut.done():
                        fut.set_exception(e)


def run(model: str, png: bytes) -> bytes:
    """A PNG upscaled 2x by one of MODELS, as PNG bytes (batched with other threads' calls)."""
    global _worker
    with _setup:
        _binary(), _model(MODELS[model])
        if _worker is None:
            _worker = threading.Thread(target=_work, name="upscayl", daemon=True)
            _worker.start()
    fut: Future = Future()
    _queue.put((model, png, fut))
    return fut.result()
