"""renders templates/notebook.py.jinja for a given run config, ready to push."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_boot_script(
    *,
    model_dataset_slug: str,
    model_filename: str,
    binary_dataset_slug: str,
    ctx_size: int = 16384,
    tunnel_mode: str = "quick",
    tunnel_hostname: str = "",
) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), keep_trailing_newline=True)
    template = env.get_template("notebook.py.jinja")
    return template.render(
        model_dataset_slug=model_dataset_slug,
        model_filename=model_filename,
        binary_dataset_slug=binary_dataset_slug,
        ctx_size=ctx_size,
        tunnel_mode=tunnel_mode,
        tunnel_hostname=tunnel_hostname,
    )
