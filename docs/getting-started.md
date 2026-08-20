# tethr — getting started (run this locally)

this is the phase-0 walkthrough from [roadmap.md](roadmap.md#phase-0--do-it-by-hand). it can't be run from the sandboxed session that wrote this code — outbound access to `api.kaggle.com` is blocked by that session's network policy — so it needs to happen on your machine. this doc is everything you need to do it and everything to report back.

## what we're actually trying to do

the one-line version: **turn a free kaggle gpu session into `http://localhost:11434/v1` on your laptop, answering like a local openai-compatible model server.**

why this exists: a genuinely good open model (think ~27B, the size that's actually useful for coding/chat) needs ~17GB of vram. you probably don't own a gpu that big. cloud apis work but cost money forever and every prompt leaves your machine. kaggle gives away ~30 gpu-hours/week on 2x T4 (32GB combined) for free, no credit card — but it's locked inside a browser tab, wiped every session, and invisible to the internet. tethr is the tool that makes that free compute usable from your actual editor/agent/curl, instead of copy-pasting notebook cells by hand.

the full design is in [architecture.md](architecture.md) and [tech-spec.md](tech-spec.md). the short version of the mechanism:

1. a **cli** (`tethr up`) pushes a small python script into a kaggle notebook via the kaggle api
2. that script (inside the notebook) starts `llama-server`, opens a tunnel (cloudflare), and prints a couple of `TETHR_*` marker lines to its own output
3. the cli polls the kernel's output for those markers, finds the tunnel url, and writes it to `~/.tethr/session.json`
4. a **local proxy** (`tethr proxy`) sits on `localhost:11434` and forwards everything to that tunnel url, so your tools never see kaggle at all

what's built so far (all in this repo): the docs, the cli skeleton (`up`/`status`/`down`/`proxy`/`logs`/`setup`), the notebook boot-script template, the proxy, and prep scripts for the two datasets phase 1 needs. **none of it has touched a real kaggle account yet.** that's what phase 0 is for — proving the manual path works and finding out where the design is wrong before trusting any of the code above.

there are two real unknowns this phase needs to answer (see "what to report back" below) — everything else is secondary.

## prerequisites

- a kaggle account, **phone-verified** (settings → phone verification — without this, notebooks get no internet and no gpu)
- python 3.11+ on your machine
- the kaggle api token you already generated (`KGAT_...`) — if you shared it in this chat, **regenerate a fresh one** at kaggle settings before using it for real, since the old one is sitting in chat history now

## step 1 — clone and set up the repo

```bash
git clone <your-repo-url> tethr
cd tethr
git checkout master   # this doc, plus everything built so far, lives there

python3 -m venv .venv
source .venv/bin/activate      # .venv\Scripts\activate on windows
pip install -e .
```

## step 2 — wire up the kaggle token

```bash
mkdir -p ~/.kaggle
echo 'KGAT_your_new_token_here' > ~/.kaggle/access_token
chmod 600 ~/.kaggle/access_token
```

sanity check it actually authenticates:

```bash
kaggle kernels list --mine
```

empty output (no kernels yet) is fine — an auth error is not. if you get one, double check the token wasn't truncated when copied.

## step 3 — the manual test (this is the actual phase 0)

don't use `tethr up` yet — the two kaggle datasets (model + compiled llama-server) it depends on don't exist yet, that's phase 1. phase 0 is about proving the raw mechanism works at all, by hand, in the kaggle web ui:

1. go to kaggle → **code** → **new notebook**
2. **settings → accelerator → GPU T4 x2**
3. **settings → internet → on**
4. for speed, test with a small model first, not the full 27B — you want to validate the plumbing (download, run, tunnel, curl) in minutes, not twenty. a small instruct gguf (search huggingface for something like `Qwen2.5-0.5B-Instruct-GGUF` and confirm the exact filename on the repo page — don't guess it) works fine for this.
5. paste and run, cell by cell:

```python
# cell 1 — get llama.cpp's server binary (prebuilt cuda release is faster than compiling for this smoke test)
!pip install -q huggingface_hub
from huggingface_hub import hf_hub_download
model_path = hf_hub_download(repo_id="<the small gguf repo you found>", filename="<the exact filename>")
print(model_path)
```

```python
# cell 2 — clone + build llama.cpp with cuda (this is the slow part, ~10-15 min)
!git clone --depth 1 https://github.com/ggerganov/llama.cpp
!cmake -B llama.cpp/build -S llama.cpp -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
!cmake --build llama.cpp/build --config Release -j --target llama-server
```

```python
# cell 3 — launch llama-server in the background
import subprocess
proc = subprocess.Popen([
    "./llama.cpp/build/bin/llama-server",
    "-m", model_path,
    "-ngl", "999",
    "--host", "127.0.0.1", "--port", "8080",
    "--api-key", "test-key-123",
])
```

```python
# cell 4 — wait for health, then open a quick cloudflare tunnel
import time, httpx
for _ in range(60):
    try:
        if httpx.get("http://127.0.0.1:8080/health", timeout=3).status_code == 200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(2)

!wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
!chmod +x cloudflared
tunnel = subprocess.Popen(["./cloudflared", "tunnel", "--url", "http://127.0.0.1:8080"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
import re
pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
for line in tunnel.stdout:
    print(line, end="")
    m = pattern.search(line)
    if m:
        print("TUNNEL URL:", m.group(0))
        break
```

6. copy the printed tunnel url
7. **from your laptop**, not the notebook:

```bash
curl https://xxxx.trycloudflare.com/v1/chat/completions \
  -H "Authorization: Bearer test-key-123" \
  -H "Content-Type: application/json" \
  -d '{"model":"local","messages":[{"role":"user","content":"say hi in 5 words"}]}'
```

8. now **save the notebook** (commit/save mode, not just leave the browser tab open) and check whether the tunnel url keeps answering `curl` a few minutes later, with the browser tab closed. this is the single biggest open question in the whole design.

## what to report back

these two answer the open risks flagged in the roadmap — everything else is nice-to-have:

1. **does the tunnel survive after you close the browser tab, once the notebook is in "save & run all" / commit mode?** if yes, the whole design works as planned. if no, `up` needs a fundamentally different approach (keep-alive strategy, or accept that sessions need an open tab).
2. **how long did you actually wait in the queued state** before the gpu was assigned?

secondary, useful for finishing `tethr_client.py`'s two `TODO`s once you're comfortable scripting against the api instead of the web ui:

3. what does `kaggle kernels status <slug>` actually print (raw text)? there's a `TODO` in `tethr/kaggle_client.py` guessing at this.
4. is there any kaggle cli/api call that actually stops a running kernel? (`down` in the cli currently raises `NotImplementedError` for this.)
5. vram headroom — did the model + context fit comfortably on 2x T4, or was it tight?

paste whatever you find back here (raw output is fine, doesn't need to be tidy) and the code gets fixed against it.

## after phase 0 works

move to [roadmap.md](roadmap.md#phase-1--prep-notebooks-the-datasets) phase 1: build the two real datasets (`notebooks/prep_model.py`, `notebooks/prep_binary.py` are already written for this), point `~/.tethr/config.toml` at them via `tethr setup`, and then `tethr up` becomes real instead of a skeleton.
