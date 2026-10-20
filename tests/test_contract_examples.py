"""Each canonical example (countdown_api.fixtures) is what the contract says: its keys, its TTLs, and its values.

Both repositories test their own writers and readers against these files; these tests are what makes them the
contract's, so a change to one that the schemas don't allow fails here, before either side sees it.
"""

import hashlib
from datetime import datetime

import pytest
from contract_helpers import ROOT, check, check_schema, check_schema_property, contract
from pydantic import TypeAdapter

from countdown_api import fixtures, keys, models, scripts

CONFIG = fixtures.load("config_store.json")
PAIRING = fixtures.load("pairing_key.json")


def test_config_store_is_a_config_under_its_key() -> None:
    assert CONFIG["key"] == keys.config(CONFIG["device_id"])
    config = check("ConfigResponse", CONFIG["value"])
    assert config.device_id == CONFIG["device_id"]
    # The stored config never carries a code: that's the pairing key's.
    assert config.pairing_code is None
    check_schema("DeviceId", CONFIG["device_id"])


def test_pairing_key_is_a_config_with_its_code_and_the_codes_ttl() -> None:
    assert PAIRING["key"] == keys.pairing(PAIRING["device_id"])
    assert PAIRING["ttl_s"] == keys.PAIRING_TTL_S == 600
    pairing = check("PairingConfig", PAIRING["value"])
    assert pairing.pairing_code == "ABC234"
    # A pairing value is a config too, so a reader can read it with ConfigResponse.
    assert check("ConfigResponse", PAIRING["value"]).pairing_code == pairing.pairing_code


def test_a_config_without_a_code_isnt_a_pairing_value() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    with pytest.raises(jsonschema.ValidationError):
        check_schema("PairingConfig", CONFIG["value"])


def test_render_screens_is_the_hash_of_slugs() -> None:
    example = fixtures.load("render_screens.json")
    assert example["key"] == keys.RENDER_SCREENS
    assert check("RenderScreens", example["screens"]) == example["screens"]
    assert CONFIG["device_id"] in example["screens"]


def test_render_queue_is_the_enqueue_scripts_keys_and_ttl() -> None:
    example = fixtures.load("render_queue.json")
    device_id = example["device_id"]
    assert example["jobs_key"] == keys.RENDER_JOBS
    assert example["queued_key"] == keys.render_queued(device_id)
    assert example["queued_ttl_ms"] == keys.RENDER_QUEUED_TTL_MS == 60_000
    assert example["enqueue_sha1"] == scripts.ENQUEUE.sha1
    check("RenderJobs", [device_id])


def test_enqueue_is_the_lua_file_byte_for_byte_and_its_sha1() -> None:
    source = (ROOT / contract()["scripts"]["enqueue"]["file"]).read_bytes()
    assert scripts.ENQUEUE.source.encode() == source
    assert hashlib.sha1(source, usedforsecurity=False).hexdigest() == scripts.ENQUEUE.sha1
    # KEYS[1] is the queued flag, KEYS[2] the jobs; ARGV[1] the device id, ARGV[2] the flag's TTL.
    assert scripts.ENQUEUE.keys == ("render_queued", "render_jobs")
    assert len(scripts.ENQUEUE.args) == 2


def test_frame_record_is_the_hash_and_its_ttl() -> None:
    example = fixtures.load("frame_record.json")
    assert example["key"] == keys.frame(example["device_id"])
    assert example["type"] == contract()["keys"]["frame"]["redis"] == "hash"
    assert example["ttl_s"] == keys.FRAME_TTL_S == 86_400
    fields = dict(example["fields"])
    frame = fixtures.read_bytes(fields["frame"]["file"])
    assert len(frame) == fields["frame"]["length"] == 800 * 480 // 8
    for field in ("etag", "rendered_at"):
        check_schema_property("FrameRecord", field, fields[field])
    fields["frame"] = frame
    record = models.FrameRecord.model_validate(fields)
    assert record.etag == hashlib.blake2b(frame, digest_size=8).hexdigest()
    assert example["served_etag"] == f'"{record.etag}"'
    assert datetime.fromisoformat(record.rendered_at).utcoffset().total_seconds() == 0


def test_energy_is_glowmarkts_readings_in_a_wrapper() -> None:
    example = fixtures.load("glow_energy.json")
    stored = check("StoredEnergy", example["stored"])
    assert stored.device_id == example["device_id"]
    assert stored.hourly == example["readings"]["PT1H"]
    assert stored.daily == example["readings"]["P1D"]
    assert stored.monthly == example["readings"]["P1M"]
    check_schema("DeviceId", example["device_id"])


def test_music_player_and_top_are_the_services_answers_in_a_wrapper() -> None:
    player = check("StoredPlayer", fixtures.load("music_player.json"))
    assert player.spotify is not None
    assert player.apple_music is not None
    # The progress is of the track the queue says is playing, and was fetched after the queue.
    assert player.spotify_playback is not None
    assert player.spotify_playback.track_id == player.spotify.get("currently_playing", {}).get("id")
    assert player.spotify_playback.fetched_at >= player.fetched_at
    top = check("StoredTop", fixtures.load("music_top.json"))
    assert set(top.spotify or {}) == {"long_term", "short_term"}


def test_album_art_keys_are_the_sha1_of_each_url() -> None:
    covers = fixtures.load("music_art.json")
    for cover in covers.values():
        assert cover["key"] == keys.album_art(cover["url"])
    # The value is the image file's own bytes (a JPEG), as a client that doesn't decode values reads it.
    art = fixtures.read_bytes("music_art.jpg")
    assert art.startswith(b"\xff\xd8\xff")
    assert TypeAdapter(models.AlbumArt).validate_python(art) == art


def test_developer_is_the_panels_data_in_a_wrapper() -> None:
    developer = check("StoredDeveloper", fixtures.load("developer.json"))
    assert developer.github is not None
    assert developer.plans


def test_weather_keys_are_weather_keys() -> None:
    example = fixtures.load("weather_keys.json")
    for case in example["keys"]:
        check("WeatherKey", case["key"])
    # The configs' own keys are among them, or the screens' subscriptions wouldn't be what their configs read.
    configs = {CONFIG["value"]["weather"]["key"], PAIRING["value"]["weather"]["key"]}
    assert configs <= set(fixtures.load("subscriptions.json")["sets"][keys.subscription(keys.WEATHER)])


def test_subscriptions_are_a_set_per_source_and_an_empty_nudge() -> None:
    example = fixtures.load("subscriptions.json")
    assert set(example["sets"]) == {keys.subscription(source) for source in keys.SOURCES}
    for members in example["sets"].values():
        check("Subscription", members)
    assert example["channel"] == keys.SUB_CHANGED
    check("SubChanged", example["message"])
    assert example["devices"] == ["config_store.json", "pairing_key.json"]
    # What each device's config says it wants is in its source's set.
    sets = example["sets"]
    for value in (CONFIG["value"], PAIRING["value"]):
        assert value["weather"]["key"] in sets[keys.subscription(keys.WEATHER)]
        assert value["notice_board"]["postcode"] in sets[keys.subscription(keys.POSTCODE)]
        for stop in value["departures"]["stops"]:
            assert stop["id"] in sets[keys.subscription(stop["source"])]
        for source, section in ((keys.SPOTIFY, "spotify"), (keys.DEVELOPER, "developer")):
            assert (value["device_id"] in sets[keys.subscription(source)]) == value[section]["enabled"]
