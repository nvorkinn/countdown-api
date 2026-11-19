"""store.yaml holds together: valid schemas, every key's value a schema, every example used, and the code generated."""

import json
import re

import pytest
from contract_helpers import ROOT, contract
from pydantic import TypeAdapter

from countdown_api import fixtures, keys, models

DEFS = contract()["$defs"]
KEYS = contract()["keys"]
SCRIPTS = contract()["scripts"]
PATHS = contract()["paths"]
OPERATIONS = {(path, method): operation for path, item in PATHS.items() for method, operation in item.items()}


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


def _refs(node: object) -> list[str]:
    """Return every `$ref` in `node`, however deep."""
    if isinstance(node, dict):
        return [node["$ref"]] if "$ref" in node else [ref for value in node.values() for ref in _refs(value)]
    if isinstance(node, list):
        return [ref for item in node for ref in _refs(item)]
    return []


@pytest.mark.parametrize(("path", "method"), sorted(OPERATIONS))
def test_each_routes_schemas_security_and_examples_exist(path: str, method: str) -> None:
    operation = OPERATIONS[path, method]
    assert method in {"get", "post", "put", "delete"}
    # The devices' API, or the settings site's pages a touchscreen opens: registering through the login, and a
    # device's settings, which it shows in a frame.
    assert path.startswith("/api/") or path in {"/register", "/device/{device_id}"}
    refs = _refs(operation)
    assert refs
    assert all(ref.removeprefix("#/$defs/") in DEFS for ref in refs), refs
    for requirement in operation.get("security", []):
        assert set(requirement) <= set(contract()["securitySchemes"])
    for example in operation.get("x-examples", []):
        assert fixtures.path(example).is_file()


def test_every_example_is_some_keys_or_routes() -> None:
    used = {example for key in KEYS.values() for example in key.get("examples", [])}
    used |= {example for operation in OPERATIONS.values() for example in operation.get("x-examples", [])}
    assert set(fixtures.names()) == used


def test_the_routes_are_what_they_were() -> None:
    # The routes the devices run on.
    assert sorted(OPERATIONS) == [
        ("/api/backgrounds/{digest}", "get"),
        ("/api/devices/arrivals", "get"),
        ("/api/devices/config", "get"),
        ("/api/devices/config", "put"),
        ("/api/devices/config/{section}", "put"),
        ("/api/devices/feed", "get"),
        ("/api/devices/notices", "get"),
        ("/api/devices/register", "post"),
        ("/api/devices/spotify/token", "get"),
        ("/api/devices/weather", "get"),
        ("/api/places/search", "get"),
        ("/api/stops/search", "get"),
        ("/device/{device_id}", "get"),
        ("/register", "get"),
        ("/register", "post"),
    ]


def test_every_key_is_in_keys_py_with_its_ttl() -> None:
    for name, key in KEYS.items():
        builder = getattr(keys, name, None) or getattr(keys, name.upper())
        params = key.get("params", {})
        built = builder(*(f"<{param}>" for param in params)) if params else builder
        expected = key["pattern"]
        for param in params:
            expected = expected.replace(f"{{{param}}}", f"<{param}>")
        if not key.get("hash") and not key.get("form"):
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
    assert keys.SOURCES == (
        "tfl",
        "entur",
        "weather",
        "glow",
        "spotify",
        "developer",
        "parcel",
        "postcode",
        "background",
    )
    assert keys.background_place("london-gb-2643743") == "v1:background-place:london-gb-2643743"
    assert keys.CONFIG_PREFIX == "v1:config:"
    assert (keys.PAIRING_TTL_S, keys.FRAME_TTL_S, keys.RENDER_QUEUED_TTL_MS) == (600, 86_400, 60_000)
    assert (keys.ENERGY_TTL_S, keys.SPOTIFY_TTL_S, keys.SPOTIFY_TOP_TTL_S) == (86_400, 180, 7_200)
    assert (keys.ALBUM_ART_TTL_S, keys.DEVELOPER_TTL_S, keys.PACE_TTL_S) == (300, 900, 60)
    assert (keys.PARCELS_TTL_S, keys.PARCELS_STATUS_TTL_S) == (43_200, 86_400)
    # countdown's providers' data, which countdown wrote under these keys before they were the contract's.
    assert keys.departures("490000123W") == "v1:departures:490000123W"
    assert keys.departures("NSR:StopPlace:58381") == "v1:departures:NSR:StopPlace:58381"
    assert keys.weather("london-gb-2643743") == "v1:weather:london-gb-2643743"
    assert keys.tfl_line_status("940GZZLUKNG") == "v1:notices:tfl-lines:940GZZLUKNG"
    assert keys.tfl_stations("940GZZLUKNG") == "v1:notices:tfl-stations:940GZZLUKNG"
    assert keys.tfl_roads("SE17 3LL") == "v1:notices:tfl-roads:SE173LL"
    assert keys.met_office("se17 3ll") == "v1:notices:met-office:SE173LL"
    assert keys.met_office("0150") == "v1:notices:met-office:0150"
    assert keys.BANK_HOLIDAYS == "v1:notices:bank-holidays"
    assert (keys.TFL_NETWORK, keys.TFL_NETWORK_TTL_S) == ("v1:notices:tfl-network", 600)
    assert keys.entur_situations("NSR:Quay:7333") == "v1:notices:entur:NSR:Quay:7333"
    assert keys.ENTUR_SITUATIONS_TTL_S == 900
    assert (keys.DEPARTURES_TTL_S, keys.WEATHER_TTL_S, keys.TFL_LINE_STATUS_TTL_S) == (120, 1_800, 600)
    assert (keys.TFL_STATIONS_TTL_S, keys.TFL_ROADS_TTL_S, keys.MET_OFFICE_TTL_S) == (1_800, 1_800, 1_800)
    assert keys.BANK_HOLIDAYS_TTL_S == 604_800


def test_store_json_is_store_yaml() -> None:
    shipped = json.loads((ROOT / "src" / "countdown_api" / "store.json").read_text(encoding="utf-8"))
    assert shipped == contract()


TAGGED = sorted(name for name, schema in DEFS.items() if "discriminator" in schema)


@pytest.mark.parametrize("name", TAGGED)
def test_each_tagged_union_maps_each_tag_to_its_member(name: str) -> None:
    schema = DEFS[name]
    tag = schema["discriminator"]["propertyName"]
    members = [option["$ref"] for option in schema["oneOf"]]
    assert sorted(schema["discriminator"]["mapping"].values()) == sorted(members)
    for value, ref in schema["discriminator"]["mapping"].items():
        assert DEFS[ref.removeprefix("#/$defs/")]["properties"][tag]["const"] == value


@pytest.mark.parametrize("name", TAGGED)
def test_each_tagged_union_is_a_pydantic_discriminated_union(name: str) -> None:
    # openapi-codegen would write a plain union; generate.py writes these itself, picked by their tag.
    metadata = getattr(models, name).__metadata__
    assert [field.discriminator for field in metadata] == [DEFS[name]["discriminator"]["propertyName"]]


def test_a_config_with_fields_a_newer_server_adds_still_validates() -> None:
    # A render pool that predates a field must not throw the screen's config away, so a config's sections ignore it.
    config = fixtures.load("config_store.json")["value"]
    newer = config | {"brightness": 7, "weather": config["weather"] | {"units": "metric"}}
    newer["style"] = config["style"] | {"contrast": "high"}

    parsed = TypeAdapter(models.ConfigResponse).validate_python(newer)

    assert parsed == TypeAdapter(models.ConfigResponse).validate_python(config)
