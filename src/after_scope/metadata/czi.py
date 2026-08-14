"""CZI acquisition-metadata extraction — header-only, no pixel data.

The XML parser is pure and backend-agnostic; two backends supply the XML string:
pylibCZIrw (Zeiss official, primary) and czifile (pure-python fallback). Every field
is optional: a corrupt or non-CZI file still yields a minimal CziMeta from stat().
"""

from __future__ import annotations

import gzip
import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class CziMeta:
    path: str
    size_bytes: int | None = None
    acquired_at: str | None = None  # local naive ISO
    objective_name: str | None = None
    magnification: float | None = None
    na: float | None = None
    immersion: str | None = None
    pixel_size_um: float | None = None
    channels: list[dict] = field(default_factory=list)
    dims: dict[str, int] = field(default_factory=dict)
    raw_xml: str | None = None

    def to_db_dict(self) -> dict:
        return {
            "size_bytes": self.size_bytes,
            "acquired_at": self.acquired_at,
            "objective_name": self.objective_name,
            "magnification": self.magnification,
            "na": self.na,
            "immersion": self.immersion,
            "pixel_size_um": self.pixel_size_um,
            "channels_json": json.dumps(self.channels) if self.channels else None,
            "dims_json": json.dumps(self.dims) if self.dims else None,
        }


# --- pure XML parsing --------------------------------------------------------------


def _text(el: ET.Element | None) -> str | None:
    return el.text.strip() if el is not None and el.text and el.text.strip() else None


def _float(el: ET.Element | None) -> float | None:
    t = _text(el)
    if t is None:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _localize(iso: str) -> str | None:
    """CZI timestamps are ISO-8601, often UTC ('Z'); store local naive."""
    try:
        dt = datetime.fromisoformat(iso.strip())
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def parse_czi_xml(xml_str: str) -> dict:
    """Extract acquisition fields from CZI ImageDocument metadata XML."""
    out: dict = {}
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        log.warning("Unparseable CZI metadata XML")
        return out

    image = root.find(".//Information/Image")
    if image is not None:
        acq = _text(image.find("AcquisitionDateAndTime"))
        if acq:
            out["acquired_at"] = _localize(acq)
        dims = {}
        for d in ("X", "Y", "Z", "C", "T", "S", "M"):
            v = _text(image.find(f"Size{d}"))
            if v and v.isdigit():
                dims[d] = int(v)
        if dims:
            out["dims"] = dims

    # Objective actually used: ObjectiveSettings/ObjectiveRef -> Instrument/Objectives
    objectives = {o.get("Id"): o for o in root.findall(".//Information/Instrument/Objectives/Objective")}
    obj = None
    ref = root.find(".//Information/Image/ObjectiveSettings/ObjectiveRef")
    if ref is not None and ref.get("Id") in objectives:
        obj = objectives[ref.get("Id")]
    elif objectives:
        obj = next(iter(objectives.values()))
    if obj is not None:
        out["objective_name"] = obj.get("Name") or _text(obj.find("Manufacturer/Model"))
        out["magnification"] = _float(obj.find("NominalMagnification"))
        out["na"] = _float(obj.find("LensNA"))
        out["immersion"] = _text(obj.find("Immersion"))

    # Pixel size: Scaling/Items/Distance[Id=X]/Value in metres
    for dist in root.findall(".//Scaling/Items/Distance"):
        if dist.get("Id") == "X":
            v = _float(dist.find("Value"))
            if v:
                out["pixel_size_um"] = round(v * 1e6, 6)
            break

    channels = []
    for ch in root.findall(".//Information/Image/Dimensions/Channels/Channel"):
        entry: dict = {"name": ch.get("Name") or ch.get("Id")}
        exposure_ns = _float(ch.find("ExposureTime"))
        if exposure_ns is not None:
            entry["exposure_ms"] = round(exposure_ns / 1e6, 3)  # CZI stores nanoseconds
        for tag, key in (
            ("ExcitationWavelength", "excitation_nm"),
            ("EmissionWavelength", "emission_nm"),
            ("IlluminationType", "illumination"),
            ("Fluor", "fluor"),
        ):
            v = _text(ch.find(tag))
            if v:
                entry[key] = v
        intensity = _text(ch.find(".//LightSourcesSettings/LightSourceSettings/Intensity"))
        if intensity:
            entry["light_intensity"] = intensity
        channels.append(entry)
    if channels:
        out["channels"] = channels
    return out


# --- backends ----------------------------------------------------------------------


def _xml_via_pylibczirw(path: Path) -> str | None:
    try:
        from pylibCZIrw import czi as pyczi
    except ImportError:
        return None
    try:
        with pyczi.open_czi(str(path)) as doc:
            return doc.raw_metadata
    except Exception:
        log.debug("pylibCZIrw could not read %s", path, exc_info=True)
        return None


def _xml_via_czifile(path: Path) -> str | None:
    try:
        import czifile
    except ImportError:
        return None
    try:
        with czifile.CziFile(str(path)) as doc:
            return doc.metadata()
    except Exception:
        log.debug("czifile could not read %s", path, exc_info=True)
        return None


def extract(path: Path | str) -> CziMeta:
    """Extract metadata for a file; never raises, always returns a CziMeta."""
    path = Path(path)
    meta = CziMeta(path=str(path))
    try:
        stat = path.stat()
        meta.size_bytes = stat.st_size
        meta.acquired_at = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
    except OSError:
        return meta
    xml_str = _xml_via_pylibczirw(path) or _xml_via_czifile(path)
    if not xml_str:
        return meta
    meta.raw_xml = xml_str
    parsed = parse_czi_xml(xml_str)
    for k in ("acquired_at", "objective_name", "magnification", "na", "immersion", "pixel_size_um"):
        if parsed.get(k) is not None:
            setattr(meta, k, parsed[k])
    meta.channels = parsed.get("channels", [])
    meta.dims = parsed.get("dims", {})
    return meta


def save_raw_xml(xml_str: str, xml_dir: Path, stem: str) -> str | None:
    try:
        xml_dir.mkdir(parents=True, exist_ok=True)
        dest = xml_dir / f"{stem}.xml.gz"
        with gzip.open(dest, "wt", encoding="utf-8") as f:
            f.write(xml_str)
        return str(dest)
    except OSError:
        log.warning("Could not persist raw XML for %s", stem, exc_info=True)
        return None
