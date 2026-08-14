"""Tray icon for the watchdog (Windows; pystray, no Qt).

Menu: current user + session start, "I'm taking over", "Report an issue"
(opens the incidents CSV location), "Open dashboard".
"""

from __future__ import annotations

import logging
import threading
import webbrowser

from ..db import repo

log = logging.getLogger(__name__)


def _make_icon_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(30, 100, 180, 255))
    d.ellipse((20, 20, 44, 44), fill=(255, 255, 255, 255))
    d.ellipse((28, 28, 36, 36), fill=(30, 100, 180, 255))
    return img


class WatchdogTray:
    def __init__(self, service) -> None:
        import pystray

        self._pystray = pystray
        self.service = service
        self.icon = pystray.Icon(
            "after_scope", _make_icon_image(), "AfterScope", menu=self._menu()
        )
        self._thread: threading.Thread | None = None

    def _session_label(self) -> str:
        try:
            row = self.service.sm.open_session()
            if not row:
                return "No active session"
            user = "unknown user"
            if row["user_id"]:
                u = repo.get_user(self.service.ctx.db, row["user_id"])
                user = u["full_name"] if u else user
            return f"{user} since {row['started_at'][11:16]}"
        except Exception:
            return "AfterScope"

    def _menu(self):
        pystray = self._pystray
        return pystray.Menu(
            pystray.MenuItem(lambda item: self._session_label(), None, enabled=False),
            pystray.MenuItem("I'm taking over (switch user)", self._takeover),
            pystray.MenuItem("Set experiment details…", self._declare),
            pystray.MenuItem("Open dashboard", self._dashboard),
            pystray.MenuItem("Open exports folder", self._exports),
        )

    def _takeover(self, icon, item) -> None:
        log.info("Tray: takeover requested")
        self.service.request_takeover()

    def _declare(self, icon, item) -> None:
        log.info("Tray: declare requested")
        self.service.request_declare()

    def _dashboard(self, icon, item) -> None:
        index = self.service.cfg.dashboard_dir / "index.html"
        if index.exists():
            webbrowser.open(index.as_uri())

    def _exports(self, icon, item) -> None:
        import os

        path = self.service.cfg.exports_dir
        if path.exists():
            os.startfile(str(path))  # noqa: S606 — Windows only

    def start(self) -> None:
        self._thread = threading.Thread(target=self.icon.run, daemon=True, name="tray")
        self._thread.start()

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            pass
