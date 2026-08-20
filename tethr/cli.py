"""tethr cli surface: up, status, down, proxy, logs, setup.

see docs/tech-spec.md#cli-surface and docs/roadmap.md#phase-2--up-and-status-mvp.
`up` blocks with real progress rather than a silent spinner -- queued can
last a while when gpus are scarce and the user needs to see that it's the
platform, not the tool.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import typer
from rich.console import Console

from tethr import kaggle_client, markers, notebook
from tethr.config import Config
from tethr.paths import CONFIG_PATH
from tethr.session import Session, SessionState

app = typer.Typer(add_completion=False, help="turn free notebook gpus into one stable openai-compatible endpoint.")
console = Console()


@app.command()
def up(
    model: str = typer.Option("qwen27b", help="model dataset key from config"),
    ctx: int = typer.Option(16384, help="context size in tokens"),
) -> None:
    """push a session, wait until it's live, write session.json."""
    config = Config.load()
    if not config.kaggle.model_dataset or not config.kaggle.binary_dataset:
        console.print("[red]no kaggle datasets configured -- run `tethr setup` first.[/red]")
        raise typer.Exit(1)

    kernel_slug = f"{config.kaggle.username}/tethr-session"
    session = Session(state=SessionState.PUSHING, model=model, kernel_slug=kernel_slug)
    session.save()
    console.print(f"[dim]pushing session for {model} (ctx={ctx})...[/dim]")

    script = notebook.render_boot_script(
        model_dataset_slug=config.kaggle.model_dataset,
        model_filename="model.gguf",
        binary_dataset_slug=config.kaggle.binary_dataset,
        ctx_size=ctx,
        tunnel_mode=config.tunnel.mode,
        tunnel_hostname=config.tunnel.hostname,
    )

    with tempfile.TemporaryDirectory() as tmp:
        kernel_dir = Path(tmp)
        (kernel_dir / "boot.py").write_text(script)
        # TODO: kernel-metadata.json (slug, datasets, gpu, internet-on) needs
        # to be generated here too -- deferred to phase 2 implementation once
        # the kaggle push format is confirmed against a real account.
        try:
            kaggle_client.push_kernel(str(kernel_dir))
        except kaggle_client.KaggleError as exc:
            console.print(f"[red]push failed: {exc}[/red]")
            session.state = SessionState.IDLE
            session.save()
            raise typer.Exit(1)

    session.state = SessionState.QUEUED
    session.save()
    console.print("[dim]queued -- waiting for a gpu...[/dim]")

    _poll_until_live(session)


def _poll_until_live(session: Session, timeout_secs: int = 600) -> None:
    deadline = time.monotonic() + timeout_secs
    kernel_slug = session.kernel_slug or ""
    with tempfile.TemporaryDirectory() as tmp:
        while time.monotonic() < deadline:
            status = kaggle_client.get_status(kernel_slug)
            if status.status == "running" and session.state == SessionState.QUEUED:
                session.state = SessionState.BOOTING
                session.save()
                console.print("[dim]booting -- loading model, opening tunnel...[/dim]")

            log_text = kaggle_client.get_output(kernel_slug, tmp)
            parsed = markers.parse(log_text)

            if parsed.error:
                console.print(f"[red]notebook reported an error: {parsed.error}[/red]")
                session.state = SessionState.IDLE
                session.save()
                raise typer.Exit(1)

            if parsed.ready and parsed.url:
                session.state = SessionState.LIVE
                session.url = parsed.url
                session.started_at = time.time()
                session.save()
                console.print(f"[green]live[/green] -- {parsed.url}")
                console.print("point your tools at http://localhost:11434/v1 (run `tethr proxy`).")
                return

            time.sleep(5)

    console.print("[red]timed out waiting for the session to come up.[/red]")
    raise typer.Exit(1)


@app.command()
def status() -> None:
    """report session state, url, uptime, quota left."""
    session = Session.load()
    console.print(f"state: [bold]{session.state.value}[/bold]")
    if session.model:
        console.print(f"model: {session.model}")
    if session.url:
        console.print(f"url: {session.url}")
    if session.started_at:
        uptime = time.time() - session.started_at
        console.print(f"uptime: {uptime / 60:.1f}m")
    if session.state == SessionState.IDLE:
        console.print("[dim]nothing running -- `tethr up` to start a session.[/dim]")
    # TODO: quota reporting needs kaggle's gpu-hours-remaining, which isn't
    # exposed by the kernels api -- track as an open question in the roadmap.


@app.command()
def down() -> None:
    """cancel the kernel and clear session state."""
    session = Session.load()
    if session.state == SessionState.IDLE or not session.kernel_slug:
        console.print("[dim]nothing running.[/dim]")
        return
    try:
        kaggle_client.cancel(session.kernel_slug)
    except NotImplementedError:
        console.print("[yellow]kernel cancellation not wired up yet -- stop it from the kaggle ui for now.[/yellow]")
    Session.clear()
    console.print("session cleared.")


@app.command()
def proxy(port: int = typer.Option(11434, help="local port to listen on")) -> None:
    """run the local proxy in the foreground."""
    from tethr.proxy import run

    console.print(f"proxy listening on http://localhost:{port}")
    run(port=port)


@app.command()
def logs(follow: bool = typer.Option(False, "-f", "--follow", help="tail kernel output")) -> None:
    """print (or tail) kernel output."""
    session = Session.load()
    if not session.kernel_slug:
        console.print("[dim]nothing running.[/dim]")
        return
    with tempfile.TemporaryDirectory() as tmp:
        while True:
            console.print(kaggle_client.get_output(session.kernel_slug, tmp))
            if not follow:
                break
            time.sleep(5)


@app.command()
def setup() -> None:
    """interactive first-run: checks kaggle token, offers to build datasets."""
    kaggle_token = Path.home() / ".kaggle" / "kaggle.json"
    if not kaggle_token.exists():
        console.print(
            "[red]~/.kaggle/kaggle.json not found.[/red] "
            "download an api token from kaggle account settings, save it there, "
            "then `chmod 600 ~/.kaggle/kaggle.json`."
        )
        raise typer.Exit(1)
    console.print("[green]kaggle token found.[/green]")

    config = Config.load()
    username = typer.prompt("kaggle username", default=config.kaggle.username or "")
    model_dataset = typer.prompt(
        "model dataset slug (e.g. username/tethr-model-qwen27b-q4)",
        default=config.kaggle.model_dataset or f"{username}/tethr-model-qwen27b-q4",
    )
    binary_dataset = typer.prompt(
        "binary dataset slug (e.g. username/tethr-llama-cuda)",
        default=config.kaggle.binary_dataset or f"{username}/tethr-llama-cuda",
    )

    config.kaggle.username = username
    config.kaggle.model_dataset = model_dataset
    config.kaggle.binary_dataset = binary_dataset
    config.save()
    console.print(f"[green]wrote config to {CONFIG_PATH}.[/green]")
    console.print(
        "if those datasets don't exist yet, build them with the prep scripts in "
        "notebooks/ -- see notebooks/README.md."
    )


if __name__ == "__main__":
    app()
