"""prep notebook: build llama.cpp with cuda support and package llama-server
plus its shared libraries as a tarball, ready to become a kaggle dataset.

run this once inside a kaggle notebook (gpu on -- needed to sanity-check the
build actually runs against the T4s, internet on). takes roughly 15 minutes,
almost all compile time.

after "save & run all", promote the output to a dataset named tethr-llama-cuda
and make it private. rebuild only when you want a newer llama.cpp.
"""

import subprocess
import tarfile
from pathlib import Path

WORKDIR = Path("/kaggle/working")
REPO_DIR = WORKDIR / "llama.cpp"
BUILD_DIR = REPO_DIR / "build"
OUT_TAR = WORKDIR / "llama-cuda.tar.gz"


def run(*cmd: str, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    run("git", "clone", "--depth", "1", "https://github.com/ggerganov/llama.cpp", str(REPO_DIR))

    run(
        "cmake", "-B", str(BUILD_DIR), "-S", str(REPO_DIR),
        "-DGGML_CUDA=ON", "-DCMAKE_BUILD_TYPE=Release",
    )
    run("cmake", "--build", str(BUILD_DIR), "--config", "Release", "-j", "--target", "llama-server")

    stage = WORKDIR / "stage"
    stage.mkdir(exist_ok=True)

    bin_path = next(BUILD_DIR.glob("**/llama-server"))
    (stage / "llama-server").write_bytes(bin_path.read_bytes())

    # bundle the shared libs llama-server was linked against so it runs
    # standalone once untarred on a fresh kernel with no build toolchain.
    for so_path in BUILD_DIR.glob("**/*.so*"):
        (stage / so_path.name).write_bytes(so_path.read_bytes())

    with tarfile.open(OUT_TAR, "w:gz") as tar:
        for item in stage.iterdir():
            tar.add(item, arcname=item.name)

    print(f"sanity check: {stage / 'llama-server'} --version")
    run(str(stage / "llama-server"), "--version")

    print(f"done: {OUT_TAR} ({OUT_TAR.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
