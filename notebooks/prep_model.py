"""prep notebook: download the model gguf from hugging face at kaggle
datacenter speed and save it as a private kaggle dataset.

run this once inside a kaggle notebook (no gpu needed, internet on).
never run this on a home connection -- the whole point is that the 17GB
download happens inside kaggle, not from your laptop.

after "save & run all", promote the notebook's output to a dataset named
tethr-model-qwen27b-q4 (or your model name) and make it private.
"""

import os
from pathlib import Path

from huggingface_hub import hf_hub_download

# --- edit these for the model you want ---
REPO_ID = "Qwen/Qwen3.8-27B-Instruct-GGUF"  # placeholder -- confirm the real repo/quant you're using
FILENAME = "model-Q4_K_M.gguf"  # placeholder -- match the actual file in the repo
OUT_DIR = Path("/kaggle/working")

# set as a kaggle secret named HF_TOKEN if the repo is gated; otherwise leave unset
HF_TOKEN = os.environ.get("HF_TOKEN")


def main() -> None:
    print(f"downloading {REPO_ID}/{FILENAME} ...")
    path = hf_hub_download(
        repo_id=REPO_ID,
        filename=FILENAME,
        local_dir=OUT_DIR,
        token=HF_TOKEN,
    )
    final = OUT_DIR / "model.gguf"
    Path(path).rename(final)
    size_gb = final.stat().st_size / 1e9
    print(f"done: {final} ({size_gb:.1f} GB)")


if __name__ == "__main__":
    main()
