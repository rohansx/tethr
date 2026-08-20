"""the local proxy: the only address your tools ever see.

forwards /v1/* to whatever backend is currently live, injects the api key,
health-checks on an interval, and returns a fast clean 503 instead of
hanging when nothing is up. streaming is passed through, never buffered.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from tethr.session import Session, SessionState

app = FastAPI()

_client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0))
_healthy = False


def _current_backend() -> tuple[str, str] | None:
    """returns (base_url, api_key) for the current session, or None if nothing is live."""
    session = Session.load()
    if session.state != SessionState.LIVE or not session.url:
        return None
    # TODO: api key currently isn't persisted to session.json (it's session-
    # scoped and shouldn't be logged casually) -- wire this up in phase 4
    # once the up-flow generates and threads it through.
    return session.url, ""


async def _health_loop(interval_secs: int = 15) -> None:
    global _healthy
    while True:
        backend = _current_backend()
        if backend is None:
            _healthy = False
        else:
            base_url, _ = backend
            try:
                r = await _client.get(f"{base_url}/health", timeout=5)
                _healthy = r.status_code == 200
            except httpx.HTTPError:
                _healthy = False
        await asyncio.sleep(interval_secs)


@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(_health_loop())


@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def forward(path: str, request: Request):
    backend = _current_backend()
    if backend is None or not _healthy:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "message": "no tethr backend is currently live. run `tethr status` "
                    "or `tethr up`.",
                    "type": "tethr_no_backend",
                }
            },
        )

    base_url, api_key = backend
    url = f"{base_url}/v1/{path}"
    headers = dict(request.headers)
    headers["authorization"] = f"Bearer {api_key}"
    headers.pop("host", None)

    body = await request.body()
    upstream_req = _client.build_request(request.method, url, headers=headers, content=body)
    upstream = await _client.send(upstream_req, stream=True)

    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=dict(upstream.headers),
        background=upstream.aclose,
    )


def run(port: int = 11434) -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port)
