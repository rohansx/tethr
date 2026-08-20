"""~/.tethr/config.toml — backend defs, tunnel mode, ports, dataset slugs.

this is the one file a user is expected to hand-edit. keep the schema small
and the defaults sane so `tethr setup` can write a working file with minimal
prompting.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, Field

from tethr.paths import CONFIG_PATH, ensure_home


class KaggleConfig(BaseModel):
    username: str = ""
    model_dataset: str = ""
    binary_dataset: str = ""


class TunnelConfig(BaseModel):
    mode: str = "quick"  # quick | named | ngrok
    hostname: str = ""  # required for named


class ProxyConfig(BaseModel):
    port: int = 11434
    health_interval_secs: int = 15


class BackendConfig(BaseModel):
    name: str
    priority: int = 1
    url: str | None = None  # set for backends that aren't the kaggle session


class Config(BaseModel):
    kaggle: KaggleConfig = Field(default_factory=KaggleConfig)
    tunnel: TunnelConfig = Field(default_factory=TunnelConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    backend: list[BackendConfig] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            return cls()
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls.model_validate(data)

    def save(self, path: Path = CONFIG_PATH) -> None:
        ensure_home()
        with path.open("wb") as f:
            tomli_w.dump(self.model_dump(exclude_none=True), f)
