# tethr — tech spec

## stack decision

**v0 prototype: python.** the tool is io-bound glue. http calls, polling, template rendering, waiting. there is no hot loop. python gets it working in an evening, and the official `kaggle` package is python anyway so there is no runtime dependency you were not already paying.

**v1: rust, once the design has survived daily use.** the rewrite is worth it for three concrete reasons and not before them:

- talking to the kaggle rest api directly with reqwest kills the python dependency and makes the binary genuinely standalone
- the proxy is a long-lived process on a port, real infrastructure, deserves a real language
- single static binary is a clean release story

do not start in rust because rust is the brand. start in rust only once daily use proves the design.

**go** is the honest third option and arguably the sweet spot for a tunnel-and-http tool, but off-brand and not the fast path here.

### dependencies

| layer | v0 (python) | v1 (rust) |
|---|---|---|
| cli | typer | clap (derive) |
| http | httpx | reqwest + tokio |
| config | tomllib + pydantic | serde + toml |
| kaggle | `kaggle` cli via subprocess | reqwest against kaggle api, basic auth |
| proxy | fastapi/uvicorn | axum + tower |
| templating | jinja2 | minijinja or format! |
| errors | exceptions | anyhow (cli) + thiserror (lib) |

inside the notebook it is plain python plus subprocess. no framework.

## external requirements

**accounts**

- kaggle, phone-verified. this is what unlocks gpu access and notebook internet. without verification nothing here works.
- kaggle api token, downloaded to `~/.kaggle/kaggle.json`, chmod 600
- tunnel provider, pick one:
  - cloudflare quick tunnel: nothing needed, random url per session
  - cloudflare named tunnel: cloudflare account + a domain you control, gives a permanent hostname
  - ngrok free: gives one static domain without needing to own a domain, which is the best free path to a stable url

**local machine**

- python 3.11+ (v0) or rust 1.75+ (v1)
- `pip install kaggle`
- no gpu, no cuda, nothing heavy. all gpu work is remote.

**one-time prep, both done inside kaggle**

- model dataset: prep notebook downloads the gguf from hugging face and saves as a private dataset. never upload 17GB from home wifi.
- binary dataset: prep notebook clones llama.cpp, builds with `-DGGML_CUDA=ON`, tars the binaries and shared objects, saves as a private dataset. ~15 min, once.

## the model

**qwen3.8-27B, Q4_K_M gguf.** dense (no MoE routing complexity), apache 2.0, multimodal, long context. ~17GB on disk.

vram math on 2x T4 (32GB combined):

- weights ~17GB, split across both cards by llama.cpp automatically with `-ngl 999`
- leaves ~15GB total for kv cache and overhead
- 16k context is comfortable. 32k is probably fine. do not chase the full 262k on T4s.

expect roughly 10-15 tok/s. T4s are old inference cards. this is good for chat, coding assistance and drafting, and sluggish for tight agent loops.

fallback if 27B is tight: a smaller Q4 fits with room to spare and doubles the speed. worth supporting a model switcher early since it is just a different dataset slug.

## notebook contract

the cli and the notebook talk through two channels only: **kaggle secrets in**, **marker lines out**. keeping this contract narrow is what stops the notebook from becoming a second codebase.

**secrets in** (set once in kaggle add-ons, referenced by name)

- `TETHR_API_KEY` — inference auth
- `TETHR_TUNNEL_TOKEN` — only for named tunnels
- `HF_TOKEN` — only if a prep notebook needs a gated model

**markers out** (printed to kernel output, parsed by the cli)

```
TETHR_URL::https://xxx.trycloudflare.com
TETHR_READY::1
TETHR_ERROR::<message>
TETHR_HEARTBEAT::<unix_ts>
```

parse only these. never try to parse llama.cpp's or cloudflared's raw output, it changes between releases.

**launch flags** that matter:

```
llama-server \
  -m /kaggle/input/<model-dataset>/model.gguf \
  -ngl 999 \
  -c 16384 \
  --host 127.0.0.1 --port 8080 \
  --api-key $TETHR_API_KEY \
  --jinja
```

`--jinja` matters for tool calling. `127.0.0.1` matters because only cloudflared should reach it.

## cli surface

```
tethr up [--model qwen27b] [--ctx 16384]   push, wait for ready, write session.json
tethr status                                session state, url, uptime, quota left
tethr down                                  cancel the kernel, clear session
tethr proxy [--port 11434]                  run the local proxy in foreground
tethr logs [-f]                             tail kernel output
tethr setup                                 interactive first-run: checks token, offers to build datasets
```

`up` blocks with real progress (pushing, queued, booting, live) rather than a silent spinner. queued can last a while when gpus are scarce and the user needs to see that it is the platform, not the tool.

## config

`~/.tethr/config.toml`

```toml
[kaggle]
username = "..."
model_dataset = "user/tethr-model-qwen27b-q4"
binary_dataset = "user/tethr-llama-cuda"

[tunnel]
mode = "quick"              # quick | named | ngrok
hostname = ""               # required for named

[proxy]
port = 11434
health_interval_secs = 15

[[backend]]                 # v2
name = "kaggle"
priority = 1

[[backend]]
name = "colibri"
url = "http://127.0.0.1:8081/v1"
priority = 2
```

port 11434 is ollama's default on purpose. a lot of tooling already assumes it.

## proxy behaviour

- forwards `/v1/*` verbatim, streaming included. do not buffer sse, it breaks the typing effect and any streaming client.
- injects the api key on the way out, so client configs stay key-free
- health-checks `/health` on an interval, tracks healthy/unhealthy per backend
- when nothing is healthy: fast `503` with a json body explaining the state. never hang.
- generous read timeout (a cold prompt on T4s can take a while) but a short connect timeout
- logs request count and token throughput to `~/.tethr/tethr.log` for the "is this actually usable" question

## build order

see [roadmap](roadmap.md) for the phased plan. summary:

1. do it by hand once in a kaggle notebook to find the real pain points
2. prep notebooks — the two datasets
3. `up` and `status` — quick tunnel, marker parsing
4. stable url + api key
5. the proxy
6. decide on rust
7. v2 — respawn, model switcher, colibri backend, routing

## open questions to answer while building

- how long is the queue wait in practice at india evening hours? if it is routinely long, `up` needs a different ux (fire and notify, rather than block).
- does kaggle's commit mode actually keep the tunnel alive reliably, or does it need the interactive session? this is the single biggest technical risk in the design.
- is 16k context enough for actual use, or does kv cache pressure force a smaller model?
- ngrok static domain vs cloudflare named tunnel: which is less annoying on first run? first-run friction decides adoption.

## security notes

- api key on the endpoint is non-negotiable, not a nice-to-have. an open inference url on a public tunnel gets found and drains your weekly quota.
- never write tokens into the notebook body. the notebook gets pushed to kaggle as a file.
- `~/.kaggle/kaggle.json` chmod 600, and never read it into your own config
- the tunnel url is a secret in practice. do not log it anywhere shareable, do not put it in screenshots for the readme.
- generate the api key per session rather than reusing one forever
