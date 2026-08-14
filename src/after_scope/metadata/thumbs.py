"""Small PNG previews of CZI files via pylibCZIrw's zoomed read."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

MAX_DIM = 256


def make_thumbnail(czi_path: Path | str, thumbs_dir: Path, stem: str) -> str | None:
    """Render a downscaled first-plane preview. Returns the PNG path or None."""
    try:
        import numpy as np
        from PIL import Image
        from pylibCZIrw import czi as pyczi
    except ImportError:
        return None
    try:
        with pyczi.open_czi(str(czi_path)) as doc:
            x0, x1 = doc.total_bounding_box["X"]
            width = max(1, x1 - x0)
            zoom = min(1.0, MAX_DIM / width)
            try:
                arr = doc.read(plane={"C": 0, "T": 0, "Z": 0}, zoom=zoom)
            except Exception:
                arr = doc.read(zoom=zoom)
    except Exception:
        log.debug("Thumbnail read failed for %s", czi_path, exc_info=True)
        return None
    try:
        arr = np.asarray(arr)
        if arr.ndim == 3 and arr.shape[2] == 1:
            arr = arr[:, :, 0]
        arr = arr.astype("float64")
        lo, hi = np.percentile(arr, (1, 99.5))
        if hi <= lo:
            hi = lo + 1
        arr = np.clip((arr - lo) / (hi - lo) * 255, 0, 255).astype("uint8")
        img = Image.fromarray(arr)
        img.thumbnail((MAX_DIM, MAX_DIM))
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        dest = thumbs_dir / f"{stem}.png"
        img.save(dest)
        return str(dest)
    except Exception:
        log.debug("Thumbnail render failed for %s", czi_path, exc_info=True)
        return None
