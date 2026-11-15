"""Each canonical example (countdown_api.fixtures) is what the contract says: its keys, its TTLs, and its values.

Every consumer tests its own writers and readers against these files; these tests are what makes them the
contract's, so a change to one that the schemas don't allow fails here, before either side sees it.
"""

import hashlib
from datetime import datetime

import pytest
from contract_helpers import ROOT, check, check_model, check_schema, check_schema_property, contract
from pydantic import TypeAdapter, ValidationError

from countdown_api import fixtures, keys, models, scripts

CONFIG = fixtures.load("config_store.json")
PAIRING = fixtures.load("pairing_key.json")
READ_ONLY = {name for name, field in contract()["$defs"]["ConfigBase"]["properties"].items() if field.get("readOnly")}


def test_config_store_is_a_config_under_its_key() -> None:
    assert CONFIG["key"] == keys.config(CONFIG["device_id"])
    config = check("ConfigResponse", CONFIG["value"])
    assert isinstance(config, models.EpaperConfig)
    assert config.device_id == CONFIG["device_id"]
    # The stored config never carries a code: that's the pairing key's.
    assert config.pairing_code is None
    check_schema("DeviceId", CONFIG["device_id"])


def test_pairing_key_is_a_config_with_its_code_and_the_codes_ttl() -> None:
    assert PAIRING["key"] == keys.pairing(PAIRING["device_id"])
    assert PAIRING["ttl_s"] == keys.PAIRING_TTL_S == 600
    pairing = check("ConfigResponse", PAIRING["value"])
    assert pairing.pairing_code == "ABC234"


def test_a_pairing_code_is_six_of_the_unambiguous_letters_and_digits() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    for code in ("ABC23", "ABC2345", "ABC23O", "abc234"):
        with pytest.raises(jsonschema.ValidationError):
            check_schema("ConfigResponse", {**PAIRING["value"], "pairing_code": code})
        with pytest.raises(ValidationError):
            check_model("ConfigResponse", {**PAIRING["value"], "pairing_code": code})


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


def test_parcels_are_the_owners_deliveries_and_a_link_status() -> None:
    example = fixtures.load("parcels.json")
    assert example["key"] == keys.parcels(example["device_id"])
    assert example["status_key"] == keys.parcels_status(example["device_id"])
    assert (example["ttl_s"], example["status_ttl_s"]) == (keys.PARCELS_TTL_S, keys.PARCELS_STATUS_TTL_S)
    stored = check("ParcelList", example["value"])
    # Ordered by expected date, soonest first, those with none last.
    dates = [parcel.expected_date for parcel in stored.parcels if parcel.expected_date is not None]
    assert dates == sorted(dates)
    undated = [parcel.expected_date is None for parcel in stored.parcels]
    assert undated == sorted(undated)
    # The example shows the statuses a panel and its notices tell apart, only ever in the normalised set.
    shown = {parcel.status for parcel in stored.parcels}
    assert {"in_transit", "out_for_delivery", "delivered", "exception"} <= shown
    assert shown <= set(contract()["$defs"]["ParcelStatus"]["enum"])
    for status in example["statuses"]:
        check("ParcelsLinkStatus", status)
    assert example["status"] in example["statuses"]
    check_schema("DeviceId", example["device_id"])


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
        for stop in value["arrivals"]["stops"]:
            assert stop["id"] in sets[keys.subscription(stop["source"])]
        for source, section in ((keys.SPOTIFY, "spotify"), (keys.DEVELOPER, "developer"), (keys.PARCEL, "parcels")):
            assert (value["device_id"] in sets[keys.subscription(source)]) == value[section]["enabled"]


TOUCHSCREEN = fixtures.load("touchscreen.json")


def test_touchscreen_registers_on_the_screens_route_and_reads_and_saves_its_config() -> None:
    device_id = TOUCHSCREEN["device_id"]
    check_schema("DeviceId", device_id)
    registration = check("DeviceRegistration", TOUCHSCREEN["registration"])
    assert registration.type == "touchscreen"
    # An e-paper screen registers on the same route, with its frame format as well as its size, and no type.
    assert check("DeviceRegistration", TOUCHSCREEN["epaper_registration"]).type is None
    assert check("DeviceRegistered", TOUCHSCREEN["registered"]).device_id == device_id
    # Its config, with its size as it registered (paired by token, it never has a pairing code).
    config = check("ConfigResponse", TOUCHSCREEN["config"])
    assert isinstance(config, models.TouchscreenConfig)
    assert config.device_id == device_id
    assert (config.width, config.height) == (registration.width, registration.height)
    # A save is the whole config as it came, with only what isn't read-only changed.
    saved = check("ConfigResponse", TOUCHSCREEN["save"])
    assert {name: getattr(saved, name) for name in READ_ONLY} == {name: getattr(config, name) for name in READ_ONLY}
    assert (saved.style, saved.display) != (config.style, config.display)


def test_a_section_save_is_one_section_whole_and_answers_the_config_with_its_new_version() -> None:
    save = TOUCHSCREEN["section_save"]
    config = check("ConfigResponse", TOUCHSCREEN["config"])
    assert save["section"] in contract()["$defs"]["ConfigSection"]["enum"]
    check_schema("ConfigVersion", save["if_match"])
    check_schema("ConfigVersion", save["etag"])
    assert save["etag"] != save["if_match"]
    answered = check("ConfigResponse", save["config"])
    # The section is what was sent, whole, and nothing else changed.
    assert getattr(answered, save["section"]).model_dump(mode="json") == save["body"]
    assert answered.model_copy(update={save["section"]: getattr(config, save["section"])}) == config


SEARCH = fixtures.load("search.json")


def test_both_searches_answer_the_same_result_shape_with_what_picking_saves() -> None:
    stops = [check("StopSearchResult", result) for result in SEARCH["stops"]]
    places = [check("PlaceSearchResult", result) for result in SEARCH["places"]]
    core = set(contract()["$defs"]["SearchResult"]["required"])
    for result in (*SEARCH["stops"], *SEARCH["places"]):
        assert core | {"value"} <= set(result)
    # A stop's value is the stop as arrivals has it; a place's, the whole weather section, with a key of the place.
    for stop in stops:
        assert (stop.value.source, stop.value.id) == (stop.source, stop.id)
    for place in places:
        assert check("Weather", place.value.model_dump(mode="json")).location == place.name
        assert place.value.key is not None
        assert place.value.key.endswith(f"-{place.country_code.lower()}-{place.id}")
    # A platform is indented under its station, the result before it.
    assert [stop.indent for stop in stops] == [False, True, False]


def test_a_touchscreen_gets_its_owners_spotify_as_a_short_lived_token() -> None:
    token = check("SpotifyAccessToken", TOUCHSCREEN["spotify_token"])

    assert token.token_type == "Bearer"  # noqa: S105 -- the scheme's name, not a password
    assert token.expires_in > 0
    # What its Web Playback SDK needs: without streaming the SDK can't play.
    assert {"streaming", "user-modify-playback-state", "user-read-playback-state"} <= set(token.scope.split())
    assert "refresh_token" not in TOUCHSCREEN["spotify_token"]


def test_a_touchscreen_registers_through_the_login_with_its_secrets_hash() -> None:
    query = check("TouchscreenRegistration", TOUCHSCREEN["register"])
    registration = check("DeviceRegistration", TOUCHSCREEN["registration"])
    # The hash of the secret it registers with on the devices' API, so the two are the same device; never the secret.
    assert query.secret_hash == hashlib.sha256(registration.secret.encode()).hexdigest()
    assert registration.secret not in str(TOUCHSCREEN["register"])
    assert (query.width, query.height) == (registration.width, registration.height)
    # Sent back to its return URL, its query kept, with the device id or the error added.
    device_id = TOUCHSCREEN["device_id"]
    assert TOUCHSCREEN["registered_return"] == f"{query.return_to}&device_id={device_id}"
    assert TOUCHSCREEN["taken_return"] == f"{query.return_to}&error=taken"


def test_a_secret_hash_is_lower_case_hex_sha256() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    check_schema("SecretHash", TOUCHSCREEN["register"]["secret_hash"])
    for bad in ("E" * 64, "e" * 63, "e" * 65, "g" * 64):
        with pytest.raises(jsonschema.ValidationError):
            check_schema("SecretHash", bad)


def test_a_config_takes_only_its_types_style() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    epaper, touchscreen = CONFIG["value"], TOUCHSCREEN["config"]
    wrong = (
        {**epaper, "style": touchscreen["style"]},
        {**touchscreen, "style": epaper["style"]},
        {**touchscreen, "type": "epaper"},
        {key: value for key, value in epaper.items() if key != "format"},
        {key: value for key, value in touchscreen.items() if key != "display"},
        {**epaper, "type": "kiosk"},
        {**touchscreen, "display": {"sleep_minutes": 10}},
        {**touchscreen, "style": {**touchscreen["style"], "theme": "auto"}},
        {key: value for key, value in epaper.items() if key != "language"},
        {key: value for key, value in epaper.items() if key != "pairing_code"},
    )
    for config in wrong:
        with pytest.raises(jsonschema.ValidationError):
            check_schema("ConfigResponse", config)
        with pytest.raises(ValidationError):
            check_model("ConfigResponse", config)


def test_a_touchscreens_config_has_only_what_it_shows_itself() -> None:
    # The flat fields, the panels it shows, its look and its screen's sleep: no language, pairing code, time zone,
    # interval, music or other integrations, which only an e-paper screen has.
    assert set(models.TouchscreenConfig.model_fields) == {
        "device_id",
        "type",
        "width",
        "height",
        "clock_format",
        "arrivals",
        "weather",
        "notice_board",
        "style",
        "display",
    }
    assert set(TOUCHSCREEN["config"]) == set(models.TouchscreenConfig.model_fields)
    epaper_only = set(models.EpaperConfig.model_fields) - set(models.TouchscreenConfig.model_fields)
    assert epaper_only == {
        "pairing_code",
        "interval",
        "language",
        "timezone",
        "format",
        "spotify",
        "apple_music",
        "glowmarkt",
        "developer",
        "parcels",
    }


def test_registrations_take_only_whats_allowed() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    epaper = TOUCHSCREEN["epaper_registration"]
    for wrong in (
        {"secret": "too-short", "type": "touchscreen"},
        {key: value for key, value in epaper.items() if key != "format"},
        {key: value for key, value in TOUCHSCREEN["registration"].items() if key != "height"},
        {**TOUCHSCREEN["registration"], "format": "png"},
    ):
        with pytest.raises(jsonschema.ValidationError):
            check_schema("DeviceRegistration", wrong)


def test_a_config_with_no_weather_place_has_no_weather_key() -> None:
    config = check("ConfigResponse", {**CONFIG["value"], "weather": {"location": "", "key": None}})
    assert config.weather.key is None
