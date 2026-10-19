"""The store contract's canonical examples: one or more for each key in store.yaml (its `examples`).

They are the single copy both repositories test against: auth-broker that what it writes is what they show and that it
reads what they show, pi-dashboard the same for its side, and this repository's tests that each is what the contract's
schemas allow. Change one here, in a PR of this repository, and the two sides' tests then say what has to follow.

    from countdown_api import fixtures

    fixtures.load("config_store.json")["value"]   # the JSON, parsed
    fixtures.read_bytes("frame_record.bin")       # a file that isn't JSON
    fixtures.DIRECTORY / "music_art.jpg"           # where they are

Everything in them is made up: no real device, code, token or password.
"""

import json
from pathlib import Path
from typing import Any

DIRECTORY = Path(__file__).parent


def path(name: str) -> Path:
    """Return the path of the example `name`, e.g. `config_store.json`; raises FileNotFoundError if there's none."""
    found = DIRECTORY / name
    if found.name != name or not found.is_file():
        msg = f"No store contract example named {name!r}"
        raise FileNotFoundError(msg)
    return found


def load(name: str) -> Any:  # noqa: ANN401 -- whatever JSON the example holds
    """Return the JSON example `name`, parsed."""
    return json.loads(path(name).read_text(encoding="utf-8"))


def read_bytes(name: str) -> bytes:
    """Return the example `name`'s bytes, for one that isn't JSON (a frame, a cover)."""
    return path(name).read_bytes()


def names() -> list[str]:
    """Return the name of every example, sorted."""
    return sorted(found.name for found in DIRECTORY.iterdir() if found.is_file() and found.suffix != ".py")
