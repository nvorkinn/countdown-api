"""The words every screen says the same way: ICU MessageFormat strings, by id, in each language a screen can be in.

The providers store what an API answered, raw. What a screen says about it is worded where it's shown: by the render
pool for an e-paper screen, by the touchscreen's own app for a touchscreen. So that both say the same thing, the
strings they word it with are here, one copy, and each formats them with its own ICU formatter and the stored values:

    from countdown_api import messages

    messages.catalog("en")["notice.line.title"]   # "{label}: {status}"
    messages.load("notices.json")                 # the file: each id's description and every language's string

A string is ICU MessageFormat, kept to what every formatter does alike: named arguments (`{line}`), `select` and
`plural` (cardinal, with `one` and `other`; no `#`, offsets or number, date or time formats). A date or a time is
formatted by the caller, from the locale's own patterns, and passed in as text.

Only what more than one kind of screen says is here: a string one kind alone says stays with that kind's code.
"""

import json
from pathlib import Path
from typing import Any

DIRECTORY = Path(__file__).parent
# The languages every message has a string in. English is the source: what a description describes.
LANGUAGES = ("en", "nb")


def path(name: str) -> Path:
    """Return the path of the message file `name`, e.g. `notices.json`; raises FileNotFoundError if there's none."""
    found = DIRECTORY / name
    if found.name != name or not found.is_file():
        msg = f"No message file named {name!r}"
        raise FileNotFoundError(msg)
    return found


def load(name: str) -> dict[str, dict[str, str]]:
    """Return the message file `name`, parsed: each id's `description` and its string in every language."""
    return json.loads(path(name).read_text(encoding="utf-8"))


def names() -> list[str]:
    """Return the name of every message file, sorted."""
    return sorted(found.name for found in DIRECTORY.iterdir() if found.is_file() and found.suffix == ".json")


def catalog(language: str) -> dict[str, str]:
    """Return every message's string in `language` (one of LANGUAGES), by id, from every file."""
    if language not in LANGUAGES:
        msg = f"No messages in {language!r}"
        raise ValueError(msg)
    strings: dict[str, Any] = {}
    for name in names():
        strings.update({message_id: message[language] for message_id, message in load(name).items()})
    return strings
