"""2x upscaling, locally with Upscayl (hstex/upscayl.py: the upscayl-* models) or through fal.ai. Colour goes to the model wrap-padded (tiling textures keep seamless edges) and is
cropped back; alpha is scaled apart (Lanczos), since the models drop it. Results are cached by model and input hash."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from . import upscayl

KEY_FILE = Path.home() / ".config/fal/key"
CACHE = Path(__file__).resolve().parents[1] / "work/cache"

MODELS = {
    "esrgan": ("fal-ai/esrgan", {"model": "RealESRGAN_x2plus", "scale": 2, "output_format": "png"}),
    "seedvr": ("fal-ai/seedvr/upscale/image", {"upscale_factor": 2, "upscale_mode": "factor", "output_format": "png",
                                               "enable_safety_checker": False}),
    "topaz-cgi": ("fal-ai/topaz/upscale/image", {"model": "CGI", "upscale_factor": 2, "output_format": "png",
                                                "face_enhancement": False}),
    "topaz-std": ("fal-ai/topaz/upscale/image", {"model": "Standard V2", "upscale_factor": 2, "output_format": "png",
                                                "face_enhancement": False}),
}

PAD = 0.125   # of each side, wrapped around


def _png(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, format="PNG")
    return buf.getvalue()


def _call(model: str, png: bytes, client: httpx.Client) -> bytes:
    endpoint, args = MODELS[model]
    key = KEY_FILE.read_text().strip()
    body = dict(args, image_url="data:image/png;base64," + base64.b64encode(png).decode())
    for attempt in range(5):
        try:
            r = client.post(f"https://fal.run/{endpoint}", json=body, headers={"Authorization": f"Key {key}"},
                            timeout=300)
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError(r.text[:200], request=r.request, response=r)
            r.raise_for_status()
            out = r.json()
            url = (out.get("image") or out["images"][0])["url"]
            if url.startswith("data:"):
                return base64.b64decode(url.split(",", 1)[1])
            return client.get(url, timeout=120).raise_for_status().content
        except (httpx.HTTPError, KeyError, json.JSONDecodeError):
            if attempt == 4:
                raise
            time.sleep(2 ** attempt * 3)
    raise RuntimeError("unreachable")


def upscale2x(rgba: np.ndarray, model: str, client: httpx.Client) -> np.ndarray:
    """rgba (h, w, 4) uint8 -> (2h, 2w, 4)."""
    h, w = rgba.shape[:2]
    ph, pw = max(1, int(h * PAD)), max(1, int(w * PAD))
    rgb = np.pad(rgba[..., :3], ((ph, ph), (pw, pw), (0, 0)), mode="wrap")
    png = _png(np.ascontiguousarray(rgb))
    path = CACHE / model / (hashlib.sha256(png).hexdigest() + ".png")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(upscayl.run(model, png) if model in upscayl.MODELS else _call(model, png, client))
        tmp.rename(path)
    up = np.asarray(Image.open(path).convert("RGB"))
    full_h, full_w = rgb.shape[0] * 2, rgb.shape[1] * 2
    if up.shape[:2] != (full_h, full_w):
        up = np.asarray(Image.fromarray(up).resize((full_w, full_h), Image.LANCZOS))
    color = up[2 * ph:2 * ph + 2 * h, 2 * pw:2 * pw + 2 * w]
    alpha = np.asarray(Image.fromarray(np.ascontiguousarray(rgba[..., 3])).resize((2 * w, 2 * h), Image.LANCZOS))
    return np.dstack([color, alpha]).astype(np.uint8)
