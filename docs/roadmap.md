# tethr — roadmap

phased plan from "nothing exists" to v2. each phase has a concrete exit criterion — the thing that has to be true before moving on. do not skip phase 0; it is the cheapest way to find out the design is wrong before any code is written.

---

## phase 0 — do it by hand

**goal:** prove the manual path works at all, and find the real pain points before designing around imagined ones.

- [ ] create kaggle account, phone-verify it (unlocks gpu + internet on notebooks)
- [ ] one kaggle notebook, by hand: download qwen 27B gguf from hugging face, download/build llama-server, run it, open a cloudflare quick tunnel, curl it from your laptop
- [ ] time every step: download, compile, boot, first token
- [ ] note where it broke or surprised you (queue wait, vram headroom, tunnel weirdness, session timeout)

**exit criterion:** you have a working curl request from your laptop to a kaggle-hosted llama-server, done at least once, and a written note of what hurt.

**time:** ~2 hours.

---

## phase 1 — prep notebooks (the datasets)

**goal:** eliminate the 20-minute setup tax so every later iteration is fast.

- [ ] `tethr-model-<name>-q4` — private kaggle dataset: prep notebook downloads the gguf from hugging face *inside* kaggle, saves as dataset output
- [ ] `tethr-llama-cuda` — private kaggle dataset: prep notebook clones llama.cpp, builds with `-DGGML_CUDA=ON`, tars binaries + `.so` files, saves as dataset output
- [ ] verify both datasets attach to a fresh notebook and are usable without re-running the prep step

**exit criterion:** a brand new notebook with both datasets attached can `chmod +x` the binary and load the model with zero downloads.

**time:** ~1 session per dataset (binary build is the ~15 min one).

---

## phase 2 — `up` and `status` (mvp)

**goal:** replace the manual kaggle-tab workflow with one command, even if the url is unstable.

- [ ] repo scaffold: python package, `pyproject.toml`, cli entrypoint (`tethr`)
- [ ] `~/.tethr/config.toml` read/write, `~/.tethr/session.json` read/write
- [ ] notebook template (jinja) implementing the 5-step boot sequence from [architecture.md](architecture.md#what-runs-inside-the-notebook)
- [ ] `tethr up`: render template, push via kaggle cli/api, poll kernel status, poll output for `TETHR_URL::` / `TETHR_READY::1` markers, write `session.json`
- [ ] `tethr status`: read `session.json`, report state + url + uptime
- [ ] `tethr down`: cancel the kernel, clear `session.json`
- [ ] quick tunnel only (cloudflare, no domain needed) — url changes every session, that's expected at this phase
- [ ] `tethr logs [-f]`: tail kernel output

**exit criterion:** `tethr up` on a cold laptop gets you a working openai-compatible url in under 2 minutes, with no manual kaggle-ui steps.

---

## phase 3 — stable url + api key

**goal:** client config gets written once and never goes stale.

- [ ] pick one: cloudflare named tunnel (needs a domain) or ngrok free static domain (no domain needed — likely the better first-run default)
- [ ] `TETHR_TUNNEL_TOKEN` wired through kaggle secrets, never in the notebook body
- [ ] `TETHR_API_KEY` generated per session, injected via kaggle secrets, required on llama-server (`--api-key`)
- [ ] `tethr up` polls the fixed hostname's `/health` directly instead of scraping markers for the url
- [ ] `tethr setup`: interactive first-run — checks `~/.kaggle/kaggle.json`, offers to build the two datasets from phase 1, walks through tunnel provider choice

**exit criterion:** you configure your editor/agent once with `http://localhost:11434` and it never needs to change again, across restarts.

---

## phase 4 — the local proxy

**goal:** stop being a script, start being a tool that's always there.

- [ ] proxy process on fixed local port (default 11434, matching ollama's default)
- [ ] forwards `/v1/*` verbatim, streaming preserved (no sse buffering)
- [ ] injects the api key on the way out — client configs stay key-free
- [ ] health-checks the backend on an interval, tracks healthy/unhealthy
- [ ] fast `503` with a clear json body when nothing is healthy — never hangs
- [ ] `tethr proxy [--port]` to run in foreground; consider a background/daemon mode
- [ ] request count + rough token throughput logged to `~/.tethr/tethr.log`

**exit criterion:** you can leave the proxy running, let the kaggle session die and restart it, and your editor never notices beyond a slower response during the gap.

---

## phase 5 — decide on rust

**goal:** don't rewrite speculatively — rewrite only once the design has earned it.

- [ ] use `tethr` daily for two weeks after phase 4
- [ ] if still using it: port to rust (clap, reqwest+tokio, axum for the proxy, serde+toml for config) for a standalone static binary release
- [ ] if not: stop, the python version was the right call and further investment isn't justified yet

**exit criterion:** an explicit go/no-go decision, written down, not a default.

---

## v2 — router over owned + borrowed compute

**goal:** the version worth writing about — same endpoint, multiple backends, routed by what's alive and what the job needs.

- [ ] `[[backend]]` config supports multiple entries with priority
- [ ] respawn: when a kaggle session dies, automatically push a fresh one rather than requiring manual `tethr up`
- [ ] model switcher: swap dataset slug to change model without code changes
- [ ] colibri backend: 744B MoE on local nvme, registered as a low-priority "batch jobs only" tier
- [ ] always-up local fallback model, lowest priority, for when nothing borrowed is available
- [ ] routing stays dumb on purpose: prefer fast-if-healthy, fall through to local, let the caller name the slow tier explicitly by model name — no learned routing

**exit criterion:** one endpoint, three tiers alive behind it, and a job can hit any of them without the caller knowing which machine answered.

---

## open questions to resolve while building

these don't block a phase, but answers should get folded back into the docs as they're learned:

- how long is the queue wait in practice at your usual usage hours? if routinely long, `up` may need a fire-and-notify ux instead of blocking.
- does kaggle's commit/save mode keep the tunnel alive reliably without an open browser tab, or does it need the interactive session? this is the biggest technical risk in the whole design — resolve it in phase 0 or phase 2, not later.
- is 16k context enough in practice, or does kv cache pressure force a smaller model / shorter context?
- ngrok static domain vs cloudflare named tunnel — which is less first-run friction? friction here decides whether phase 3 actually gets adopted.

## non-goals (keep out of scope at every phase)

- no tethr-hosted anything — no accounts, no telemetry, no server side
- no queueing or batching — one session, one user, one model
- no multi-account rotation — that's the line between a dev tool and a farm
- no fighting the platform's session cap — respawn on a fresh allocation, don't try to fool the scheduler
