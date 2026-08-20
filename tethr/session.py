"""~/.tethr/session.json — the only mutable state, and disposable.

deleting it should never break anything worse than "run `tethr up` again."
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from tethr.paths import SESSION_PATH, ensure_home


class SessionState(StrEnum):
    IDLE = "idle"
    PUSHING = "pushing"
    QUEUED = "queued"
    BOOTING = "booting"
    LIVE = "live"
    DYING = "dying"


class Session(BaseModel):
    state: SessionState = SessionState.IDLE
    kernel_slug: str | None = None
    url: str | None = None
    started_at: float | None = None
    model: str | None = None

    @classmethod
    def load(cls, path: Path = SESSION_PATH) -> "Session":
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text())

    def save(self, path: Path = SESSION_PATH) -> None:
        ensure_home()
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def clear(cls, path: Path = SESSION_PATH) -> None:
        if path.exists():
            path.unlink()
