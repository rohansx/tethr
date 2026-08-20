"""parses the TETHR_* marker lines the notebook prints to kernel output.

see docs/tech-spec.md#notebook-contract -- these four markers are the only
thing the cli reads out of kernel output. everything else in the log is
llama.cpp / cloudflared noise and is not a stable format to parse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MARKER_RE = re.compile(r"TETHR_(URL|READY|ERROR|HEARTBEAT)::(.*)")


@dataclass
class Markers:
    url: str | None = None
    ready: bool = False
    error: str | None = None
    heartbeat: int | None = None


def parse(log_text: str) -> Markers:
    markers = Markers()
    for line in log_text.splitlines():
        match = _MARKER_RE.search(line)
        if not match:
            continue
        kind, value = match.groups()
        if kind == "URL":
            markers.url = value.strip()
        elif kind == "READY":
            markers.ready = value.strip() == "1"
        elif kind == "ERROR":
            markers.error = value.strip()
        elif kind == "HEARTBEAT":
            markers.heartbeat = int(value.strip())
    return markers
