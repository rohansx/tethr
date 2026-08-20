"""control plane: talks to kaggle through the official `kaggle` cli.

v0 shells out to the cli rather than hitting the rest api directly -- it's
already a dependency (the cli needs it for auth against ~/.kaggle/kaggle.json)
and it saves reimplementing kaggle's push/status/output handling. v1 (rust)
drops this in favor of reqwest against the api directly, see docs/tech-spec.md.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


class KaggleError(RuntimeError):
    """a kaggle cli invocation failed or returned something we didn't expect."""


def _run(*args: str) -> str:
    result = subprocess.run(
        ["kaggle", *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise KaggleError(result.stderr.strip() or f"kaggle {' '.join(args)} failed")
    return result.stdout


@dataclass
class KernelStatus:
    status: str  # queued | running | complete | error | cancelAcknowledged
    failure_message: str | None = None


def push_kernel(kernel_dir: str) -> None:
    """push a kernel-metadata.json + script dir. raises KaggleError on failure."""
    _run("kernels", "push", "-p", kernel_dir)


def get_status(kernel_slug: str) -> KernelStatus:
    out = _run("kernels", "status", kernel_slug)
    # TODO: the cli's status output isn't structured json in all versions --
    # confirm the actual format against a real account in phase 2 and parse
    # accordingly. this is a placeholder shape.
    try:
        data = json.loads(out)
        return KernelStatus(status=data.get("status", "unknown"))
    except json.JSONDecodeError:
        return KernelStatus(status=out.strip())


def get_output(kernel_slug: str, dest_dir: str) -> str:
    """pull kernel log output down to dest_dir, return the combined log text."""
    _run("kernels", "output", kernel_slug, "-p", dest_dir)
    log_path = f"{dest_dir}/{kernel_slug.split('/')[-1]}.log"
    try:
        with open(log_path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def cancel(kernel_slug: str) -> None:
    # NOTE: the kaggle cli has no first-class "stop kernel" command as of
    # writing. this likely needs the rest api directly (DELETE on the kernel
    # session) -- tracked as an open question for phase 2.
    raise NotImplementedError("kernel cancellation: confirm the right kaggle api call in phase 2")
