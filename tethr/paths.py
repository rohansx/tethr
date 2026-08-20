"""filesystem layout for ~/.tethr/"""

from pathlib import Path

HOME = Path.home() / ".tethr"
CONFIG_PATH = HOME / "config.toml"
SESSION_PATH = HOME / "session.json"
LOG_PATH = HOME / "tethr.log"


def ensure_home() -> Path:
    HOME.mkdir(parents=True, exist_ok=True)
    return HOME
