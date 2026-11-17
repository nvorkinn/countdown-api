"""The messages (countdown_api.messages): each says the same in every language, in ICU every formatter reads."""

import re

import pytest

from countdown_api import messages

# A consumer runs these tests too, from its own checkout of this repository, without this repository's dev group:
# there they are skipped, as the schema checks are without jsonschema (contract_helpers.check_schema).
Parser = pytest.importorskip("pyicumessageformat").Parser

FILES = {name: messages.load(name) for name in messages.names()}
MESSAGES = {message_id: message for file in FILES.values() for message_id, message in file.items()}
# What every formatter does alike: named arguments, select and plural with no offset.
ALLOWED_TYPES = {None, "select", "plural"}


def shape(tree: list) -> dict:
    """Return what a parsed message asks of its caller: each argument's name, its type, and a select's keys."""
    found: dict = {}
    for node in tree:
        if isinstance(node, str):
            continue
        options = node.get("options", {})
        found[node["name"]] = (node.get("type"), frozenset(options))
        for branch in options.values():
            found.update(shape(branch))
    return found


def test_there_are_messages_and_each_file_is_found_by_name() -> None:
    assert messages.names() == ["notices.json"]
    assert messages.path("notices.json").is_file()
    with pytest.raises(FileNotFoundError):
        messages.path("../store.json")


def test_a_catalog_is_every_ids_string_in_one_language() -> None:
    for language in messages.LANGUAGES:
        catalog = messages.catalog(language)
        assert set(catalog) == set(MESSAGES)
        assert all(isinstance(string, str) and string.strip() for string in catalog.values())
    assert messages.catalog("en")["notice.weather.title"] == "Weather warning"
    assert messages.catalog("nb")["notice.day.tomorrow"] == "I morgen"
    with pytest.raises(ValueError, match="No messages in"):
        messages.catalog("sv")


@pytest.mark.parametrize("message_id", sorted(MESSAGES))
def test_a_message_is_described_and_asks_the_same_of_its_caller_in_every_language(message_id: str) -> None:
    message = MESSAGES[message_id]
    assert set(message) == {"description", *messages.LANGUAGES}
    assert message["description"].strip()
    assert re.fullmatch(r"[a-z]+(\.[a-z_]+)+", message_id)
    shapes = {language: shape(Parser().parse(message[language])) for language in messages.LANGUAGES}
    # The same arguments, of the same types, with the same select keys: a translation changes only the words.
    assert shapes["nb"] == shapes["en"]
    for _type, keys in shapes["en"].values():
        assert _type in ALLOWED_TYPES
        if _type == "select":
            assert "other" in keys
        if _type == "plural":
            assert keys == {"one", "other"}


def test_a_string_has_no_formatting_only_some_formatters_do() -> None:
    for message in MESSAGES.values():
        for language in messages.LANGUAGES:
            assert "#" not in message[language]
            assert "offset:" not in message[language]
            assert "'" not in message[language]  # ICU's quoting, which formatters read differently
