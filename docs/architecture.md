# tethr — architecture

## the shape of it

three planes, and the only clever part is that they are kept separate.

```
  your laptop                    cloudflare / ngrok            kaggle vm
 ┌──────────────┐               ┌──────────────┐         ┌────────────────────┐
 │ your tools   │               │              │         │  llama-server      │
 │ editor,      │               │   tunnel     │         │  (openai api)      │
 │ agents, curl │               │              │         │        ▲           │
 └──────┬───────┘               └──────▲───────┘         │        │           │
        │ localhost:11434              │                 │  ┌─────┴───────┐   │
 ┌──────▼───────┐                      │                 │  │ 2x T4 32GB  │   │
 │ tethr proxy  │──────────────────────┘                 │  └─────────────┘   │
 └──────┬───────┘   https + api key                      │                    │
        │                                                │  attached datasets │
 ┌──────▼───────┐                                        │  ├ model gguf 17GB │
 │ tethr cli    │───── kaggle rest api ──────────────────▶│  └ llama-server bin│
 │ up/status/dn │      push kernel, poll status           └────────────────────┘
 └──────────────┘
```

**control plane** = the cli talking to kaggle's api. push a notebook, poll until it is running, read its output.

**data plane** = your tools to the proxy to the tunnel to llama-server. the cli is not in this path at all. that separation is what lets the cli exit while inference keeps working.

**storage plane** = two private kaggle datasets that never change. this is the whole speed trick.

## why the datasets matter more than anything else

naive version of this project: notebook starts, downloads 17GB from hugging face, clones and compiles llama.cpp with cuda. twenty minutes before the first token, every single session, burning quota on setup.

tethr version: both artifacts are prepared once and stored as private kaggle datasets. attaching a dataset to a notebook is a mount, not a copy, so it is available immediately.

- `tethr-model-qwen27b-q4` — the gguf, ~17GB. built by a prep notebook that downloads from hugging face *inside* kaggle at datacenter speed, so nothing is uploaded from home.
- `tethr-llama-cuda` — compiled llama-server binaries plus their `.so` files, tarred. built once in a gpu session, roughly 15 minutes, then never again until you want a newer llama.cpp.

boot time after this: about a minute, most of it model load into vram.

## the session lifecycle

```
  idle ──▶ pushing ──▶ queued ──▶ booting ──▶ live ──▶ dying ──▶ idle
                                                 ▲                 │
                                                 └── respawn (v2) ──┘
```

- **pushing** — cli renders the notebook template with the run's config and pushes it via the kaggle api
- **queued** — kaggle schedules the kernel, gpu availability is not instant or guaranteed
- **booting** — datasets attach, llama-server starts, tunnel opens, health check has not passed yet
- **live** — `/v1/models` answers through the tunnel. the proxy flips to healthy.
- **dying** — session hits its cap, or gets reclaimed, or you called `down`

treat `dying` as routine, not exceptional. it happens on a schedule.

## what runs inside the notebook

the notebook is a template the cli fills in and pushes. it does five things in order:

1. untar the llama-server build from the attached dataset, `chmod +x`
2. launch llama-server as a background process, pointed at the gguf, `-ngl 999` to push all layers onto gpu (llama.cpp splits across both T4s on its own), `--host 127.0.0.1`, an api key from kaggle secrets
3. wait for `/health` to answer locally
4. start cloudflared pointed at the local port. if using a named tunnel the token comes from kaggle secrets and the hostname is fixed. if using a quick tunnel, scrape the generated url from cloudflared's output and print it in a parseable marker line so the cli can read it back from the kernel output
5. keep-alive loop, printing a heartbeat, so the kernel does not look idle

run it in kaggle's commit/save mode so it survives without a browser tab open.

**never bind llama-server to 0.0.0.0 without the api key set.** a public tunnel url with an open inference endpoint is someone else's free gpu, paid for out of your weekly quota.

## how the cli finds the endpoint

two paths depending on tunnel choice, and this is the main branch in the design:

**named tunnel / reserved domain (preferred).** the hostname is known before the session even starts. the cli does not need to discover anything, it just polls `https://llm.yourdomain.dev/health` until it answers. config is written once and never goes stale. costs you a domain (cloudflare) or the free ngrok static domain.

**quick tunnel (zero setup).** the url is random per session. the notebook prints it wrapped in a marker like `TETHR_URL::https://xxx.trycloudflare.com`, the cli polls kernel output for that marker. works with nothing but a kaggle account, but every client that hardcoded the url breaks on restart. this is exactly why the local proxy exists.

## the local proxy

small always-on process on a fixed port, forwarding to whatever the current backend is.

it is the answer to "the url changes and my session dies." your tools point at `localhost:11434` forever. behind it the tunnel url can change every session and nothing downstream notices. it also holds the api key so it never appears in client configs, health-checks the backend on an interval, and returns a clean error when nothing is up instead of a connection refused.

in v2 it becomes the router:

```
       localhost:11434
             │
     ┌───────▼────────┐
     │  tethr proxy   │
     └───┬────┬────┬──┘
         │    │    │
   kaggle│    │    │local small model
   27B   │    │    │always up
         │    │
         │  colibri on your nvme
         │  744B, <1 tok/s, batch jobs only
```

routing rules stay dumb on purpose: prefer the fast tier if healthy, fall through to local, and let the caller explicitly ask for the slow tier by model name. no cleverness, no learned routing.

## state and config

everything lives in `~/.tethr/`:

```
~/.tethr/
  config.toml      backend defs, tunnel mode, ports, dataset slugs
  session.json     current kernel slug, url, started_at, state
  tethr.log        proxy + cli log
```

`session.json` is the only mutable state and it is disposable. deleting it should never break anything worse than "run up again."

secrets never live here. the kaggle token stays in `~/.kaggle/kaggle.json` where its own cli expects it. the tunnel token and the inference api key live in kaggle secrets, referenced by name from the notebook, never written into the notebook body (the notebook gets pushed, and a pushed notebook is a file with your token in it).

## failure modes and what happens

| what breaks | how it shows up | what tethr does |
|---|---|---|
| no gpu available | kernel queued a long time | surface the queue state, do not silently hang |
| session hits cap | endpoint stops answering | proxy returns 503 with a real message. v2 respawns. |
| tunnel drops but server alive | health check fails, kernel still running | restart cloudflared inside the notebook, do not rebuild the session |
| weekly quota exhausted | push succeeds, gpu never assigned | check quota before push, refuse early with a clear message |
| model too big for vram | llama-server dies at load | catch in the boot phase, report the actual llama.cpp error rather than a timeout |

the general rule: fail loud in the cli, fail soft in the proxy. the proxy is in the path of your editor, and an editor plugin hanging on a dead socket is worse than a fast 503.

## what this is deliberately not

- no tethr-hosted anything. no accounts, no telemetry, no server side.
- no queueing or batching. one session, one user, one model.
- no multi-account rotation. that is the line between a dev tool and a farm.
- no attempt to keep sessions alive past the platform's cap. respawn on a fresh allocation, do not try to fool the scheduler.
