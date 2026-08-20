# prep notebooks

phase 1 of the [roadmap](../docs/roadmap.md): build the two private kaggle datasets that make every later `tethr up` boot in ~1 minute instead of ~20.

these are not run by the cli — paste them into a new kaggle notebook by hand, run once (or whenever you want to bump a version), and save the output as a private dataset. they're one-time setup, not part of the product surface.

## `prep_model.py` → `tethr-model-qwen27b-q4`

- new kaggle notebook, **no gpu needed**, internet **on**
- if the model is gated on hugging face, add `HF_TOKEN` as a kaggle secret first
- paste in `prep_model.py`, run all
- "save version" → "save & run all" → once it finishes, the output becomes a dataset. rename it to `tethr-model-<name>-q4` and set it **private**
- update `model_dataset` in `~/.tethr/config.toml` (or re-run `tethr setup`) to point at `<your-kaggle-username>/tethr-model-<name>-q4`

## `prep_binary.py` → `tethr-llama-cuda`

- new kaggle notebook, **gpu on** (needed to build+sanity-check the cuda binary), internet **on**
- paste in `prep_binary.py`, run all — this takes roughly 15 minutes, almost all of it compiling
- save the output as a private dataset named `tethr-llama-cuda`
- update `binary_dataset` in `~/.tethr/config.toml` to point at `<your-kaggle-username>/tethr-llama-cuda`

rebuild this one only when you want a newer llama.cpp — it doesn't change per session.

## why these aren't `.ipynb` files

kaggle notebooks accept plain `.py` scripts through "file → import notebook" just as well as `.ipynb`, and a `.py` file is reviewable in a normal diff. if you prefer working in the kaggle notebook editor directly, paste the script content into cells in the order the comments suggest.
