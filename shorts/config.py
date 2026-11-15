import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Cfg(dict):
    """dict with attribute access for nested sections."""

    def __getattr__(self, k):
        v = self[k]
        return Cfg(v) if isinstance(v, dict) else v


def load(path: str | Path | None = None) -> Cfg:
    p = Path(path) if path else ROOT / "config.toml"
    with open(p, "rb") as f:
        return Cfg(tomllib.load(f))


def rel(p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else ROOT / q
