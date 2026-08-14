"""Migration manifest format.

Lab members migrating legacy files (v1.1 wizard) execute the moves on their own
machines and drop a write-once JSON manifest into Dropbox; the scope PC — the only
database writer — ingests it. Manifests are named uniquely per user+timestamp, so
concurrent migrations cannot conflict.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

MANIFEST_VERSION = 1


@dataclass
class ManifestFile:
    original_path: str
    new_path: str
    acquired_at: str | None = None
    strain: str | None = None
    condition: str | None = None
    coverslip: str | None = None
    notes: str | None = None
    experiment: str | None = None
    extracted: dict = field(default_factory=dict)  # objective, channels, dims, ...


@dataclass
class Manifest:
    submitted_by: str
    submitted_at: str
    files: list[ManifestFile]
    version: int = MANIFEST_VERSION

    def write(self, inbox: Path) -> Path:
        inbox.mkdir(parents=True, exist_ok=True)
        stamp = self.submitted_at.replace(":", "").replace("-", "")
        dest = inbox / f"manifest-{self.submitted_by}-{stamp}.json"
        i = 2
        while dest.exists():
            dest = inbox / f"manifest-{self.submitted_by}-{stamp}-{i}.json"
            i += 1
        dest.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return dest


def load_manifest(path: Path) -> Manifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != MANIFEST_VERSION:
        raise ValueError(f"Unsupported manifest version: {data.get('version')}")
    files = [ManifestFile(**f) for f in data["files"]]
    return Manifest(
        submitted_by=data["submitted_by"],
        submitted_at=data["submitted_at"],
        files=files,
    )
