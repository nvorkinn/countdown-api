"""Each canonical example (countdown_api.fixtures) is what the contract says: its keys, its TTLs, and its values.

Every consumer tests its own writers and readers against these files; these tests are what makes them the
contract's, so a change to one that the schemas don't allow fails here, before either side sees it.
"""

import hashlib
import json
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
    assert example["devices"] == ["config_store.json", "pairing_key.json", "touchscreen.json"]
    # What each device's config says it wants is in its source's set.
    sets = example["sets"]
    for value in (CONFIG["value"], PAIRING["value"]):
        assert value["weather"]["key"] in sets[keys.subscription(keys.WEATHER)]
        assert value["notice_board"]["postcode"] in sets[keys.subscription(keys.POSTCODE)]
        if address := value["notice_board"].get("address"):
            member = "|".join(
                (address["street"], address["house_number"], value["notice_board"]["postcode"], address["city"])
            )
            assert member in sets[keys.subscription(keys.ADDRESS)]
        for stop in value["arrivals"]["stops"]:
            assert stop["id"] in sets[keys.subscription(stop["source"])]
        for source, section in ((keys.SPOTIFY, "spotify"), (keys.DEVELOPER, "developer"), (keys.PARCEL, "parcels")):
            assert (value["device_id"] in sets[keys.subscription(source)]) == value[section]["enabled"]
    # The touchscreen wants what the e-paper screens already do, and its place's backgrounds, which only it has.
    touchscreen = fixtures.load("touchscreen.json")["config"]
    assert touchscreen["weather"]["key"] in sets[keys.subscription(keys.WEATHER)]
    assert touchscreen["notice_board"]["postcode"] in sets[keys.subscription(keys.POSTCODE)]
    for stop in touchscreen["arrivals"]["stops"]:
        assert stop["id"] in sets[keys.subscription(stop["source"])]
    assert sets[keys.subscription(keys.BACKGROUND)] == [touchscreen["weather"]["key"]]
    assert set(sets[keys.subscription(keys.BACKGROUND)]) <= set(sets[keys.subscription(keys.WEATHER)])


def test_an_epaper_screens_poll_carries_its_report() -> None:
    poll = fixtures.load("frame_poll.json")
    # The ETag of the frame on its panel, as the broker served it: in quotes.
    assert poll["if_none_match"] == fixtures.load("frame_record.json")["served_etag"]
    report = check("FrameReport", poll["report"])
    assert "{device_id}" in report.metrics
    assert [line.level for line in report.logs] == ["info", "warn"]
    # A poll with nothing to report is a poll all the same.
    assert check("FrameReport", {}).logs is None


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


def test_the_current_location_is_at_most_one_place_as_the_search_answers_it() -> None:
    here = [check("PlaceSearchResult", result) for result in SEARCH["here"]]
    assert len(here) <= 1
    assert SEARCH["here"] == SEARCH["places"][:1]
    assert all(place.value.key is not None for place in here)


def test_a_touchscreen_gets_its_owners_spotify_as_a_short_lived_token() -> None:
    token = check("SpotifyAccessToken", TOUCHSCREEN["spotify_token"])

    assert token.token_type == "Bearer"  # noqa: S105 -- the scheme's name, not a password
    assert token.expires_in > 0
    # What its Web Playback SDK needs: without streaming the SDK can't play.
    assert {"streaming", "user-modify-playback-state", "user-read-playback-state"} <= set(token.scope.split())
    assert "refresh_token" not in TOUCHSCREEN["spotify_token"]


def test_a_device_is_told_which_services_its_owners_account_has_linked_and_nothing_more() -> None:
    account = check("DeviceAccount", TOUCHSCREEN["account"])
    # The example's owner has pasted no Parcel key, so its parcels are off whatever its own switch says.
    assert not account.parcel.linked
    assert not check("ConfigResponse", TOUCHSCREEN["config"]).parcels.enabled
    assert account.spotify.linked
    # Only whether each is linked.
    assert all(set(link) == {"linked"} for link in TOUCHSCREEN["account"].values())


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
        {**touchscreen, "display": {**touchscreen["display"], "brightness": 5}},
        {**touchscreen, "display": {**touchscreen["display"], "brightness": 101}},
        {**touchscreen, "display": {**touchscreen["display"], "quiet_hours": {"on": True, "start": 1320}}},
        {**touchscreen, "display": {**touchscreen["display"], "quiet_hours": {"on": True, "start": 1320, "end": 1440}}},
        {**touchscreen, "language": "de"},
        {**touchscreen, "lyrics": {"size": "huge", "align": "left"}},
        {**touchscreen, "lyrics": {"size": "medium", "align": "justify"}},
        {**touchscreen, "style": {**touchscreen["style"], "skin": "dusk"}},
        {key: value for key, value in epaper.items() if key != "language"},
        {key: value for key, value in epaper.items() if key != "pairing_code"},
    )
    for config in wrong:
        with pytest.raises(jsonschema.ValidationError):
            check_schema("ConfigResponse", config)
        with pytest.raises(ValidationError):
            check_model("ConfigResponse", config)


def test_a_touchscreen_config_from_before_lyrics_is_still_one() -> None:
    older = {key: value for key, value in TOUCHSCREEN["config"].items() if key != "lyrics"}
    check_schema("ConfigResponse", older)
    assert check("TouchscreenConfig", older).lyrics is None


def test_a_touchscreen_config_from_before_brightness_and_quiet_hours_is_at_full_brightness_with_none() -> None:
    older = TOUCHSCREEN["config"] | {"display": {"sleep_minutes": 15}}
    check_schema("ConfigResponse", older)
    display = check("TouchscreenConfig", older).display
    assert display.brightness == 100
    assert display.quiet_hours is None


def test_a_touchscreens_quiet_hours_may_run_past_midnight() -> None:
    quiet = check("TouchscreenConfig", TOUCHSCREEN["config"]).display.quiet_hours
    assert (quiet.on, quiet.start, quiet.end) == (True, 22 * 60, 7 * 60)


def test_a_touchscreen_config_from_before_brightness_control_cannot_set_it() -> None:
    older = {key: value for key, value in TOUCHSCREEN["config"].items() if key != "brightness_control"}
    check_schema("ConfigResponse", older)
    assert check("TouchscreenConfig", older).brightness_control is False


def test_a_touchscreen_config_from_before_its_language_is_english() -> None:
    older = {key: value for key, value in TOUCHSCREEN["config"].items() if key != "language"}
    check_schema("ConfigResponse", older)
    assert check("TouchscreenConfig", older).language == "en"


def test_a_touchscreens_config_has_only_what_it_shows_itself() -> None:
    # The flat fields, whether its brightness can be set, its language, the panels it shows, its look, its screen's
    # sleep and its parcel notices: no pairing code, time zone, interval, music or other integrations, which only an
    # e-paper screen has.
    assert set(models.TouchscreenConfig.model_fields) == {
        "device_id",
        "type",
        "width",
        "height",
        "brightness_control",
        "clock_format",
        "language",
        "arrivals",
        "weather",
        "notice_board",
        "style",
        "display",
        "lyrics",
        "parcels",
    }
    assert set(TOUCHSCREEN["config"]) == set(models.TouchscreenConfig.model_fields)
    epaper_only = set(models.EpaperConfig.model_fields) - set(models.TouchscreenConfig.model_fields)
    assert epaper_only == {
        "pairing_code",
        "interval",
        "timezone",
        "format",
        "spotify",
        "apple_music",
        "glowmarkt",
        "developer",
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


# --- countdown's providers' data, and the routes that serve it to a touchscreen ---------------------------------------

PANELS = fixtures.load("device_panels.json")


def test_departures_are_each_stops_under_its_key() -> None:
    example = fixtures.load("departures.json")
    assert example["ttl_s"] == keys.DEPARTURES_TTL_S
    for stop in example["stops"]:
        departures = check("StopDepartures", stop["value"])
        assert stop["key"] == keys.departures(departures.stop_id)
        times = [departure.expected_at for departure in departures.departures]
        assert times == sorted(times)  # soonest first
    sources = {stop["value"]["stop_id"].startswith("NSR:") for stop in example["stops"]}
    assert sources == {True, False}  # TfL's and Entur's, in one shape


def test_weather_is_a_places_forecast_under_its_weather_key() -> None:
    example = fixtures.load("weather.json")
    assert example["key"] == keys.weather(example["weather_key"])
    assert example["ttl_s"] == keys.WEATHER_TTL_S
    stored = check("StoredForecast", example["value"])
    check_schema("WeatherKey", example["weather_key"])
    assert stored.location == example["weather_key"]
    # What a touchscreen needs from it: now (day or night), the next hours, and sunrise and sunset.
    assert isinstance(stored.forecast.current["is_day"], bool)
    assert stored.forecast.hourly["time"]
    assert stored.forecast.daily["sunrise"]


def test_backgrounds_are_a_places_day_under_its_weather_key() -> None:
    example = fixtures.load("background.json")
    assert example["key"] == keys.background(example["weather_key"])
    assert example["ttl_s"] == keys.BACKGROUND_TTL_S
    stored = check("StoredBackground", example["value"])
    assert stored.location == example["weather_key"]
    starts = [image.starts_at for image in stored.images]
    assert starts == sorted(starts)  # in the order they start showing
    assert [image.phase for image in stored.images] == ["dawn", "day", "dusk", "night"]


def test_a_background_image_is_its_webp_under_its_sha256() -> None:
    example = fixtures.load("background.json")
    image = fixtures.read_bytes(example["image"]["file"])
    assert image[:4] == b"RIFF" and image[8:12] == b"WEBP"
    digest = hashlib.sha256(image).hexdigest()
    check_schema("BackgroundDigest", digest)
    assert example["image"]["key"] == keys.background_image(digest)
    assert example["image"]["ttl_s"] == keys.BACKGROUND_IMAGE_TTL_S
    assert example["image"]["url"] == f"/api/backgrounds/{digest}"
    assert digest in {image["digest"] for image in example["value"]["images"]}
    assert TypeAdapter(models.BackgroundImage).validate_python(image) == image


def test_a_background_place_is_a_touchscreens_place_beside_its_subscription() -> None:
    example = fixtures.load("background_place.json")
    touchscreen = fixtures.load(example["device"])["config"]
    assert example["weather_key"] == touchscreen["weather"]["key"]
    check_schema("WeatherKey", example["weather_key"])
    assert example["set"] == keys.subscription(keys.BACKGROUND)
    assert example["weather_key"] in fixtures.load("subscriptions.json")["sets"][example["set"]]
    assert example["key"] == keys.background_place(example["weather_key"])
    assert "ttl_s" not in example  # kept until its place leaves the set
    place = check("BackgroundPlace", example["value"])
    assert place.country == touchscreen["notice_board"]["country"]
    assert place.postcodes == [touchscreen["notice_board"]["postcode"]]
    # A typed location that isn't placed yet has no country.
    assert check("BackgroundPlace", {"name": "london", "country": None, "postcodes": []}).country is None
    with pytest.raises(ValidationError):
        check_model("BackgroundPlace", {"name": "London"})


def test_a_line_statuses_short_forms_are_of_its_reasons_and_within_the_limits() -> None:
    stored = fixtures.load("tfl_notices.json")["lines"]["value"]
    lines = check("StoredLineStatus", stored)
    reasons = {" ".join(status["reason"].split()) for line in stored["lines"] for status in line["lineStatuses"]}
    assert {short.text for short in lines.shorts} < reasons  # of its reasons, and one has none yet
    for short in stored["shorts"]:
        check("NoticeShort", short)
        for field, limit in (("title", 32), ("summary", 64)):
            with pytest.raises(ValidationError):
                check_model("NoticeShort", short | {field: "x" * (limit + 1)})
    # A value stored before there were any reads as one with none (the models read a missing list as None).
    without = {key: value for key, value in stored.items() if key != "shorts"}
    assert not check("StoredLineStatus", without).shorts
    assert not check("StoredStationDisruptions", fixtures.load("tfl_notices.json")["stations"]["value"]).shorts
    assert not check("StoredRoadDisruptions", fixtures.load("tfl_notices.json")["roads"]["value"]).shorts


def test_tfl_notices_are_tfls_answers_under_their_keys() -> None:
    example = fixtures.load("tfl_notices.json")
    stop_id, postcode = example["stop_id"], example["postcode"]
    for kind, builder, schema in (
        ("lines", keys.tfl_line_status, "StoredLineStatus"),
        ("stations", keys.tfl_stations, "StoredStationDisruptions"),
    ):
        assert example[kind]["key"] == builder(stop_id)
        assert check(schema, example[kind]["value"]).stop_id == stop_id
    assert example["roads"]["key"] == keys.tfl_roads(postcode)
    assert check("StoredRoadDisruptions", example["roads"]["value"]).postcode == postcode
    lines = check("StoredLineStatus", example["lines"]["value"]).lines
    assert lines[0]["lineStatuses"][0]["statusSeverityDescription"]  # TfL's own names
    ttls = (example["lines"]["ttl_s"], example["stations"]["ttl_s"], example["roads"]["ttl_s"])
    assert ttls == (keys.TFL_LINE_STATUS_TTL_S, keys.TFL_STATIONS_TTL_S, keys.TFL_ROADS_TTL_S)


def test_the_tfl_network_is_every_tube_line_and_the_elizabeth_line() -> None:
    example = fixtures.load("tfl_network.json")
    assert example["key"] == keys.TFL_NETWORK
    assert example["ttl_s"] == keys.TFL_NETWORK_TTL_S
    lines = check("StoredNetworkStatus", example["value"]).lines
    assert {line["modeName"] for line in lines} == {"tube", "elizabeth-line"}
    assert len(lines) == 12  # the 11 Tube lines and the Elizabeth line
    assert lines[0]["lineStatuses"][0]["statusSeverityDescription"]  # TfL's own names


def test_entur_situations_are_enturs_answer_for_the_stop() -> None:
    example = fixtures.load("entur_situations.json")
    stored = check("StoredEnturSituations", example["value"])
    assert example["key"] == keys.entur_situations(stored.stop_id)
    assert example["ttl_s"] == keys.ENTUR_SITUATIONS_TTL_S
    stop = stored.data["stopPlace"]
    lines = [line for quay in stop["quays"] for line in quay["lines"]]
    situations = [situation for line in lines for situation in line["situations"]]
    assert {"summary", "validityPeriod", "severity", "reportType"} <= set(situations[0])  # Entur's own names
    assert [call["serviceJourney"]["line"]["publicCode"] for call in stop["estimatedCalls"]]


def test_met_office_warnings_are_the_regions_feed_under_the_postcodes_place() -> None:
    example = fixtures.load("met_office.json")
    assert example["key"] == keys.met_office(example["postcode"])
    assert example["ttl_s"] == keys.MET_OFFICE_TTL_S
    stored = check("StoredMetOfficeWarnings", example["value"])
    assert stored.postcode == example["postcode"]
    assert stored.items[0].title.startswith(("Yellow", "Amber", "Red"))


def test_bank_holidays_are_every_part_of_the_uks() -> None:
    example = fixtures.load("bank_holidays.json")
    assert example["key"] == keys.BANK_HOLIDAYS
    assert example["ttl_s"] == keys.BANK_HOLIDAYS_TTL_S
    stored = check("StoredBankHolidays", example["value"])
    assert set(stored.divisions) == {"england-and-wales", "scotland", "northern-ireland"}


def test_locations_are_where_each_postcode_is_or_that_it_isnt_one() -> None:
    example = fixtures.load("location.json")
    assert example["ttl_s"] == keys.LOCATION_TTL_S
    found = {}
    for entry in example["locations"]:
        assert entry["key"] == keys.location(entry["postcode"])
        stored = check("StoredLocation", entry["value"])
        assert stored.postcode == entry["postcode"]
        assert stored.found == (stored.location is not None)
        found[stored.postcode] = stored
    assert found["SE17 3LL"].location.region == "London"
    assert found["EH1 1YZ"].location.region is None  # outside England
    assert found["0150"].location.country == "Norway"
    assert not found["ZZ1 1ZZ"].found
    assert not found["0001"].found


def test_floods_are_the_eas_warnings_near_the_postcodes_place_under_its_names() -> None:
    example = fixtures.load("floods.json")
    assert example["ttl_s"] == keys.FLOODS_TTL_S
    for entry in example["places"]:
        assert entry["key"] == keys.floods(entry["postcode"])
        stored = check("StoredFloods", entry["value"])
        assert stored.postcode == entry["postcode"]
        # Written back under the EA's own names, as a writer dumps it.
        assert json.loads(stored.model_dump_json()) == entry["value"]
    levels = [warning["severityLevel"] for warning in example["places"][0]["value"]["floods"]["items"]]
    assert sorted(levels) == [1, 2, 3, 4]
    assert example["places"][-1]["value"]["floods"]["items"] == []  # all clear is still written


def test_bins_are_each_addresss_collection_days_or_that_binable_has_none() -> None:
    example = fixtures.load("bins.json")
    assert example["ttl_s"] == keys.BINS_TTL_S
    found = {}
    for entry in example["addresses"]:
        assert entry["key"] == keys.bins(entry["address"])
        assert entry["address"].count("|") == 3
        stored = check("StoredBinCollections", entry["value"])
        assert stored.found == bool(stored.collections)
        for collection in stored.collections:
            assert collection.dates == sorted(collection.dates)
        found[entry["address"]] = stored
    assert set(fixtures.load("subscriptions.json")["sets"][keys.subscription(keys.ADDRESS)]) <= set(found)
    oslo = found["Thorvald Meyers gate|10|0555|Oslo"]
    assert [collection.fraction for collection in oslo.collections] == ["paper", "residualWaste"]


def test_metalerts_are_mets_answers_for_all_of_norway_in_both_languages() -> None:
    example = fixtures.load("metalerts.json")
    assert example["key"] == keys.METALERTS
    assert example["ttl_s"] == keys.METALERTS_TTL_S
    stored = check("StoredMetAlerts", example["value"])
    for answer in (stored.no, stored.en):
        assert answer["type"] == "FeatureCollection"
        assert {feature["geometry"]["type"] for feature in answer["features"]} <= {"Polygon", "MultiPolygon"}
    assert [feature["properties"]["id"] for feature in stored.no["features"]] == [
        feature["properties"]["id"] for feature in stored.en["features"]
    ]


def test_the_panels_examples_are_a_paired_touchscreens() -> None:
    config = check("ConfigResponse", PANELS["config"])
    assert isinstance(config, models.TouchscreenConfig)
    assert config.device_id == PANELS["device_id"]


def test_get_weather_answers_the_configs_place_and_its_stored_forecast() -> None:
    weather = check("DeviceWeather", PANELS["weather"])
    place = PANELS["config"]["weather"]
    assert (weather.location, weather.key) == (place["location"], place["key"])
    assert PANELS["weather"]["forecast"] == fixtures.load("weather.json")["value"]
    assert PANELS["weather"]["background"] == fixtures.load("background.json")["value"]


def test_get_weather_without_a_background_is_still_a_device_weather() -> None:
    weather = {key: value for key, value in PANELS["weather"].items() if key != "background"}
    assert check("DeviceWeather", weather).background is None


def test_get_arrivals_answers_each_configured_stop_in_order_with_what_is_stored() -> None:
    arrivals = check("DeviceArrivals", PANELS["arrivals"])
    assert [(stop.source, stop.id) for stop in arrivals.stops] == [
        (stop["source"], stop["id"]) for stop in PANELS["config"]["arrivals"]["stops"]
    ]
    stored = {stop["value"]["stop_id"]: stop["value"] for stop in fixtures.load("departures.json")["stops"]}
    for stop in PANELS["arrivals"]["stops"]:
        assert stop["departures"] == stored.get(stop["id"])


def test_get_notices_answers_the_stored_sources_for_the_devices_stops_and_postcode() -> None:
    notices = check("DeviceNotices", PANELS["notices"])
    tfl = fixtures.load("tfl_notices.json")
    assert notices.postcode == PANELS["config"]["notice_board"]["postcode"]
    tfl_stops = [stop["id"] for stop in PANELS["config"]["arrivals"]["stops"] if stop["source"] == "tfl"]
    assert [stop.stop_id for stop in notices.tfl_stops] == tfl_stops
    assert PANELS["notices"]["tfl_stops"][0]["lines"] == tfl["lines"]["value"]
    assert PANELS["notices"]["tfl_stops"][1] == {"stop_id": tfl_stops[1], "lines": None, "stations": None}
    assert PANELS["notices"]["tfl_roads"] == tfl["roads"]["value"]
    assert PANELS["notices"]["met_office"] == fixtures.load("met_office.json")["value"]
    assert PANELS["notices"]["bank_holidays"] == fixtures.load("bank_holidays.json")["value"]
    assert PANELS["notices"]["tfl_network"] == fixtures.load("tfl_network.json")["value"]
    entur_stops = [stop["id"] for stop in PANELS["config"]["arrivals"]["stops"] if stop["source"] == "entur"]
    assert [stop.stop_id for stop in notices.entur_stops or []] == entur_stops
    assert PANELS["notices"]["entur_stops"] == [{"stop_id": entur_stops[0], "situations": None}]  # none stored
    # Its parcels are switched on, so it has what the parcel provider stored for it.
    assert PANELS["config"]["parcels"] == {"enabled": True, "days_ahead": None, "kept_hours": 4}
    assert PANELS["notices"]["parcels"] == fixtures.load("parcels.json")["value"]
    # A UK postcode: the EA's warnings near it, and none of MET Norway's.
    floods = {entry["postcode"]: entry["value"] for entry in fixtures.load("floods.json")["places"]}
    assert PANELS["notices"]["floods"] == floods[notices.postcode]
    assert notices.metalerts is None


NORWAY = fixtures.load("device_notices_norway.json")


def test_get_notices_for_a_norwegian_postcode_has_mets_warnings_covering_its_place() -> None:
    notices = check("DeviceNotices", NORWAY["notices"])
    assert (notices.postcode, notices.country) == (NORWAY["postcode"], "NO")
    assert NORWAY["location"] == keys.location(notices.postcode)
    assert (notices.tfl_roads, notices.met_office, notices.bank_holidays, notices.floods) == (None, None, None, None)
    stored = fixtures.load("metalerts.json")["value"]
    assert NORWAY["notices"]["metalerts"]["fetched_at"] == stored["fetched_at"]
    for language in ("no", "en"):
        narrowed = NORWAY["notices"]["metalerts"][language]
        # Each answer's other members as they came, and its Features a subset of it, in its order.
        assert {key: value for key, value in narrowed.items() if key != "features"} == {
            key: value for key, value in stored[language].items() if key != "features"
        }
        assert narrowed["features"] == [
            feature for feature in stored[language]["features"] if feature in narrowed["features"]
        ]
        assert 0 < len(narrowed["features"]) < len(stored[language]["features"])
    ids = {
        language: [f["properties"]["id"] for f in notices.metalerts.model_dump()[language]["features"]]
        for language in ("no", "en")
    }
    assert ids["no"] == ids["en"]
    # Its household's bin collection days, as the bins provider stored them for its address.
    board = fixtures.load("touchscreen.json")["config"]["notice_board"]
    address = board["address"]
    member = f"{address['street']}|{address['house_number']}|{board['postcode']}|{address['city']}"
    stored_bins = {entry["key"]: entry["value"] for entry in fixtures.load("bins.json")["addresses"]}
    assert NORWAY["notices"]["bins"] == stored_bins[keys.bins(member)]


def test_a_touchscreens_parcels_are_off_and_its_notices_have_none_when_left_out() -> None:
    # As a config or an answer from before they were added reads.
    config = {key: value for key, value in TOUCHSCREEN["config"].items() if key != "parcels"}
    assert check("ConfigResponse", config).parcels is None
    notices = {key: value for key, value in PANELS["notices"].items() if key != "parcels"}
    assert check("DeviceNotices", notices).parcels is None


def test_notices_from_a_server_before_floods_and_metalerts_still_validate() -> None:
    older = {key: value for key, value in PANELS["notices"].items() if key not in {"floods", "metalerts"}}
    notices = check("DeviceNotices", older)
    assert (notices.floods, notices.metalerts) == (None, None)
