"""Config models and loading.

One annotated YAML file (master copy typically in Dropbox so the lab manager can edit
it anywhere) is validated on load; a last-known-good copy is cached locally so a
half-synced or broken edit never takes the watchdog down.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from .paths import AppPaths, default_data_dir

log = logging.getLogger(__name__)


class InstrumentCfg(BaseModel):
    name: str = "Zeiss microscope"
    machine: str = ""


class ZenCfg(BaseModel):
    process_names: list[str] = Field(default_factory=lambda: ["Zen.exe"])
    # Dev/simulate: match by substring of the command line instead of the process
    # name (a python script's process name is just "python").
    cmdline_contains: str | None = None
    poll_seconds: float = 3.0


class WatchDirCfg(BaseModel):
    path: Path
    recursive: bool = True


class OrganizeCfg(BaseModel):
    mode: Literal["move", "copy", "index_only"] = "move"
    filename_template: str = "{date}_{initials}_{experiment}_{strain}_{condition}_{seq:03d}"
    dest_template: str = "{dropbox_root}/MicroscopeData/{year}/{initials}/{date}_{experiment}"
    min_stable_seconds: int = 60
    max_path_length: int = 240


class DropboxCfg(BaseModel):
    root: Path = Path("~/AfterScopeDropbox")


class DustCfg(BaseModel):
    required: Literal["prompt", "required", "off"] = "prompt"
    filename_prefix: str = "dustref"
    preset_hint: str = "AfterScope_DustRef"
    objective: str = "100x"
    modality: str = "brightfield"


class SolventCfg(BaseModel):
    approved_solvent: str = "approved lens solvent"
    suggest_after_days: int = 14


class HandoverCfg(BaseModel):
    idle_minutes: float = 45.0
    auto_close_hours: float = 6.0


class RosterEntry(BaseModel):
    name: str
    initials: str
    email: str | None = None


class ShowIf(BaseModel):
    key: str
    equals: Any = True


class ChecklistItemCfg(BaseModel):
    key: str
    label: str
    type: Literal["checkbox", "yes_no", "select", "text", "number", "solvent_clean"] = "checkbox"
    required: bool = False
    options: list[str] = Field(default_factory=list)
    show_if: ShowIf | None = None
    # If the response equals this value, an incident draft is created.
    flag_if: Any | None = None
    # Named prefill hook evaluated against the session (e.g. "objectives_contain_oil").
    prefill_from: str | None = None
    help: str | None = None


class EnforcementCfg(BaseModel):
    allow_skip: bool = True
    skip_requires_reason: bool = True
    nag_at_next_start: bool = True


class ScanCfg(BaseModel):
    seconds: int = 60
    file_patterns: list[str] = Field(default_factory=lambda: ["*.czi"])
    # Files modified up to this long before session start are still candidates
    # (covers clock slop and saves begun just before the watchdog noticed ZEN).
    pre_start_slack_seconds: int = 120


class DeclareCfg(BaseModel):
    enabled: bool = True
    create_scratch_dir: bool = True
    # Where the pre-created session folder goes; None -> the first watch_dir.
    scratch_root: Path | None = None


class AnnotateCfg(BaseModel):
    mode: Literal["toast", "off"] = "toast"
    timeout_seconds: int = 15


class TrayCfg(BaseModel):
    enabled: bool = True


class UiCfg(BaseModel):
    # How the wizard presents:
    #   dimmed     centered frameless window over a dimmed backdrop (scope PC default)
    #   fullscreen frameless fullscreen takeover (the original kiosk look)
    #   windowed   plain resizable window (dev)
    # `kiosk` is the legacy switch: honoured only when `mode` is unset.
    kiosk: bool = True
    mode: str | None = None

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in ("dimmed", "fullscreen", "windowed"):
            raise ValueError("ui.mode must be dimmed, fullscreen or windowed")
        return v

    def effective_mode(self) -> str:
        if self.mode is not None:
            return self.mode
        return "fullscreen" if self.kiosk else "windowed"


class AppConfig(BaseModel):
    instrument: InstrumentCfg = Field(default_factory=InstrumentCfg)
    zen: ZenCfg = Field(default_factory=ZenCfg)
    watch_dirs: list[WatchDirCfg] = Field(default_factory=list)
    scan: ScanCfg = Field(default_factory=ScanCfg)
    organize: OrganizeCfg = Field(default_factory=OrganizeCfg)
    dropbox: DropboxCfg = Field(default_factory=DropboxCfg)
    dust: DustCfg = Field(default_factory=DustCfg)
    solvent: SolventCfg = Field(default_factory=SolventCfg)
    handover: HandoverCfg = Field(default_factory=HandoverCfg)
    roster: list[RosterEntry] = Field(default_factory=list)
    checklist: list[ChecklistItemCfg] = Field(default_factory=list)
    enforcement: EnforcementCfg = Field(default_factory=EnforcementCfg)
    declare: DeclareCfg = Field(default_factory=DeclareCfg)
    annotate: AnnotateCfg = Field(default_factory=AnnotateCfg)
    tray: TrayCfg = Field(default_factory=TrayCfg)
    ui: UiCfg = Field(default_factory=UiCfg)
    data_dir: Path | None = None

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, v: Any) -> Any:
        return Path(v).expanduser() if v else None

    # --- derived Dropbox locations -------------------------------------------------
    @property
    def afterscope_root(self) -> Path:
        return self.dropbox.root / "AfterScope"

    @property
    def exports_dir(self) -> Path:
        return self.afterscope_root / "exports"

    @property
    def backup_dir(self) -> Path:
        return self.afterscope_root / "backup"

    @property
    def dashboard_dir(self) -> Path:
        return self.afterscope_root / "dashboard"

    @property
    def incidents_dir(self) -> Path:
        return self.afterscope_root / "incidents"

    @property
    def migrations_inbox(self) -> Path:
        return self.afterscope_root / "migrations" / "inbox"

    def resolve_paths(self, base_dir: Path) -> None:
        """Expand ~ and make relative paths relative to the config file location."""

        def fix(p: Path) -> Path:
            p = Path(str(p)).expanduser()
            return p if p.is_absolute() else (base_dir / p).resolve()

        self.dropbox.root = fix(self.dropbox.root)
        for wd in self.watch_dirs:
            wd.path = fix(wd.path)
        if self.declare.scratch_root is not None:
            self.declare.scratch_root = fix(self.declare.scratch_root)
        if self.data_dir is not None:
            self.data_dir = fix(self.data_dir)

    def effective_scratch_root(self) -> Path | None:
        if self.declare.scratch_root is not None:
            return self.declare.scratch_root
        return self.watch_dirs[0].path if self.watch_dirs else None

    def app_paths(self) -> AppPaths:
        return AppPaths(self.data_dir if self.data_dir else default_data_dir())


def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping, got {type(data).__name__}")
    return data


def load_config(path: Path, cache_path: Path | None = None) -> AppConfig:
    """Load + validate config; fall back to the cached last-known-good copy."""
    cache = cache_path or AppPaths(default_data_dir()).last_good_config
    try:
        cfg = AppConfig.model_validate(_read_yaml(path))
        cfg.resolve_paths(path.parent)
    except Exception as exc:
        if cache.exists():
            log.error("Config %s failed to load (%s); using last-known-good %s", path, exc, cache)
            cfg = AppConfig.model_validate(_read_yaml(cache))
            cfg.resolve_paths(path.parent if path.exists() else cache.parent)
            return cfg
        raise
    # Cache the raw file as last-known-good for next time.
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, cache)
    except OSError:  # caching is best-effort
        log.warning("Could not cache last-known-good config", exc_info=True)
    return cfg
