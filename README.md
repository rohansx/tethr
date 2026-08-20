# tethr

turn free notebook gpus into one stable openai-compatible endpoint on your own machine.

```
tethr up
```

ninety seconds later you have `http://localhost:11434/v1` answering like a local model server. point your editor plugin, your agent scripts, your existing openai client at it. nothing knows the gpu is somewhere in google's datacenter.

`tethr status` tells you if the session is alive and how much of the weekly quota is left. `tethr down` kills it.

## the problem

you want to run a genuinely good open model. three options exist today and all three are bad:

1. **cloud api.** works, costs money forever, and every prompt leaves your machine. you are renting.
2. **local hardware.** a 27B at Q4 needs ~17GB of vram. most laptops do not have it. a machine that does is a 100k+ purchase.
3. **free notebook gpus.** kaggle hands out roughly 30 gpu-hours a week on 2x T4 (32GB combined) with no credit card. plenty for a 27B. but the machine is invisible to the internet, gets wiped on every session, and only exists inside a browser tab.

option 3 is the one nobody has packaged. the compute is sitting there, free, and it is unusable from the tools you actually work in.

## who it is for

- people who build with local models but do not own a gpu big enough
- people who want to try a 27B before deciding whether to buy the hardware
- students and hackathon folks with zero budget and a real need for inference
- anyone who already has kaggle open in a tab and is copy-pasting notebook cells to do this by hand

## why this is not just a notebook gist

the manual version of this takes twenty minutes and breaks in five predictable places: the model re-downloads every session, llama.cpp recompiles every session, the tunnel url changes on every restart so every client config goes stale, the endpoint is wide open to the internet, and the session dies silently while you are mid-task.

tethr fixes all five as its actual product surface:

- **prebaked datasets.** model weights and a compiled cuda llama-server live as private kaggle datasets, attached like usb drives. boot in about a minute, not twenty.
- **stable url.** a named tunnel or a reserved ngrok domain, so client config is written once.
- **auth by default.** an api key is generated and injected, never an open endpoint on a public url.
- **quota awareness.** the tool knows about the weekly gpu budget and shows it, so you do not discover you are out mid-session.
- **one local address.** a thin local proxy so `localhost:11434` is the only thing your tools ever see, regardless of what is behind it.

## the real ambition (v2)

tethr is not a kaggle wrapper. it is a router over compute you own or scavenge. backends are pluggable and all speak the same openai api:

- **borrowed tier.** kaggle session, 27B, ~10-15 tok/s. good for chat, coding, drafting.
- **owned tier.** colibri on your own nvme, running a 744B MoE at well under 1 tok/s by streaming experts off disk. useless for chat, excellent for fire-and-forget overnight jobs.
- **fallback tier.** a small local model that is always up.

same endpoint, same api, routed by what is alive and what the job needs. that is the version worth writing a blog post about.

## non-goals

- not production infrastructure. the weekly quota makes that structurally impossible and that is fine.
- not a way to farm free compute. one account, one session, respectful of the platform's interactive-use intent.
- not a training tool. inference only.
- not a hosting service. there is no server component, no accounts, no tethr cloud.

## why not just use openrouter

no key, no bill, no data leaving to a third party you did not choose, and you can point it at your own hardware tomorrow.

## success criteria

v0 is a success if you personally stop opening kaggle in a browser and start typing `tethr up` instead.

v1 is a success if ten other people do the same.

## risks worth naming up front

- **platform tos.** notebook services are for interactive work and actively discourage long idle gpu holds. keep sessions attended-ish, keep the framing honest, do not build the farm.
- **quota changes.** free tiers move. the tool should degrade to "here is what is available" rather than break.
- **T4s are old.** ~10-15 tok/s is real but not fast. nobody should arrive expecting groq.
- **session death is normal.** the design treats a dead session as an ordinary state, not an error.

## docs

- [getting started](docs/getting-started.md) — run phase 0 locally, what to test, what to report back
- [architecture](docs/architecture.md) — the three planes, the session lifecycle, the proxy, failure modes
- [tech spec](docs/tech-spec.md) — stack decisions, notebook contract, cli surface, config
- [roadmap](docs/roadmap.md) — phases, milestones, and what "done" looks like at each step

## status

pre-v0. see [roadmap](docs/roadmap.md) for where things stand.
