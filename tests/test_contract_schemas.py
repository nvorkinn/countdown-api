"""store.yaml holds together: valid schemas, every key's value a schema, every example used, and the code generated."""

import json
import re

import pytest
from contract_helpers import ROOT, contract

from countdown_api import fixtures, keys, models

DEFS = contract()["$defs"]
KEYS = contract()["keys"]
SCRIPTS = contract()["scripts"]


@pytest.mark.parametrize("name", sorted(DEFS))
def test_each_schema_is_json_schema_2020_12(name: str) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator.check_schema({"$defs": DEFS, "$ref": f"#/$defs/{name}"})
    jsonschema.Draft202012Validator.check_schema(DEFS[name])


@pytest.mark.parametrize("name", sorted(DEFS))
def test_each_schema_has_a_model(name: str) -> None:
    assert hasattr(models, name)


@pytest.mark.parametrize("name", sorted(KEYS))
def test_each_keys_value_is_a_schema_and_its_examples_exist(name: str) -> None:
    key = KEYS[name]
    assert key["value"] in DEFS
    assert key["redis"] in {"string", "hash", "set", "list", "channel"}
    assert key["encoding"] in {"json", "text", "bytes"}
    for example in key.get("examples", []):
        assert fixtures.path(example).is_file()


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_each_scripts_keys_and_args_are_what_its_lua_uses(name: str) -> None:
    script = SCRIPTS[name]
    assert set(script["keys"]) <= set(KEYS)
    source = (ROOT / script["file"]).read_text(encoding="utf-8")
    for table, declared in (("KEYS", script["keys"]), ("ARGV", script["args"])):
        used = {int(index) for index in re.findall(rf"\b{table}\[(\d+)\]", source)}
        assert used == set(range(1, len(declared) + 1)), f"{name}: {table} in the Lua vs the contract"


def test_every_example_is_some_keys() -> None:
    used = {example for key in KEYS.values() for example in key.get("examples", [])}
    assert set(fixtures.names()) == used


def test_every_key_is_in_keys_py_with_its_ttl() -> None:
    for name, key in KEYS.items():
        builder = getattr(keys, name, None) or getattr(keys, name.upper())
        params = key.get("params", {})
        built = builder(*(f"<{param}>" for param in params)) if params else builder
        expected = key["pattern"]
        for param in params:
            expected = expected.replace(f"{{{param}}}", f"<{param}>")
        if not key.get("hash"):
            assert built == expected
        for unit in ("S", "MS"):
            if f"ttl_{unit.lower()}" in key:
                assert getattr(keys, f"{name.upper()}_TTL_{unit}") == key[f"ttl_{unit.lower()}"]
        assert built.startswith(f"{keys.PREFIX}:")


def test_the_keys_are_what_they_were() -> None:
    # The layout both sides run on today: a change to any of these is a new key, not an edit.
    device = "a1b2c3d4e5f6"
    assert keys.subscription(keys.TFL) == "v1:sub:tfl"
    assert keys.SUB_CHANGED == "v1:sub:changed"
    assert keys.config(device) == "v1:config:a1b2c3d4e5f6"
    assert keys.pairing(device) == "v1:pairing:a1b2c3d4e5f6"
    assert keys.RENDER_SCREENS == "v1:render:screens"
    assert keys.RENDER_JOBS == "v1:render:jobs"
    assert keys.render_queued(device) == "v1:render:queued:a1b2c3d4e5f6"
    assert keys.frame(device) == "v1:frame:a1b2c3d4e5f6"
    assert keys.energy(device) == "v1:energy:a1b2c3d4e5f6"
    assert keys.spotify(device) == "v1:spotify:a1b2c3d4e5f6"
    assert keys.spotify_top(device) == "v1:spotify-top:a1b2c3d4e5f6"
    assert keys.developer(device) == "v1:developer:a1b2c3d4e5f6"
    assert keys.parcels(device) == "v1:parcels:a1b2c3d4e5f6"
    assert keys.parcels_status(device) == "v1:parcels-status:a1b2c3d4e5f6"
    assert keys.pace(keys.DEVELOPER, device) == "v1:pace:developer:a1b2c3d4e5f6"
    assert keys.album_art("https://i.scdn.co/image/ab01300") == "v1:art:f0c75b31e316838c7115ebf3205ef753eb4a0353"
    assert keys.SOURCES == ("tfl", "entur", "weather", "glow", "spotify", "developer", "parcel", "postcode")
    assert keys.CONFIG_PREFIX == "v1:config:"
    assert (keys.PAIRING_TTL_S, keys.FRAME_TTL_S, keys.RENDER_QUEUED_TTL_MS) == (600, 86_400, 60_000)
    assert (keys.ENERGY_TTL_S, keys.SPOTIFY_TTL_S, keys.SPOTIFY_TOP_TTL_S) == (86_400, 180, 7_200)
    assert (keys.ALBUM_ART_TTL_S, keys.DEVELOPER_TTL_S, keys.PACE_TTL_S) == (300, 900, 60)
    assert (keys.PARCELS_TTL_S, keys.PARCELS_STATUS_TTL_S) == (43_200, 86_400)


def test_store_json_is_store_yaml() -> None:
    shipped = json.loads((ROOT / "src" / "countdown_api" / "store.json").read_text(encoding="utf-8"))
    assert shipped == contract()
