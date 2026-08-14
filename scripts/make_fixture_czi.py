"""Synthesize a small CZI file (for tests and the acquisition simulator).

Uses the official pylibCZIrw writer; produces a 2-channel 96x96 image with channel
names and scaling metadata. Run directly:  python scripts/make_fixture_czi.py out.czi
"""

from __future__ import annotations

import sys
from pathlib import Path


def make_fixture_czi(dest: Path, channels: int = 2, size: int = 96) -> Path:
    import numpy as np
    from pylibCZIrw import czi as pyczi

    dest.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed=size + channels)
    with pyczi.create_czi(str(dest), exist_ok=True) as doc:
        for c in range(channels):
            plane = (rng.random((size, size)) * 4000).astype("uint16")
            plane[20:40, 20:60] = 60000  # a bright feature so thumbnails look non-flat
            doc.write(data=plane, plane={"C": c, "T": 0, "Z": 0})
        doc.write_metadata(
            document_name=dest.stem,
            channel_names={i: n for i, n in enumerate(["TL Brightfield", "EGFP"][:channels])},
            scale_x=6.5e-8,
            scale_y=6.5e-8,
        )
    return dest


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "fixture.czi")
    print(make_fixture_czi(out))
