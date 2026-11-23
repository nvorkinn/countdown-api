"""The C++ headers in cpp/countdown_api: built with the host's compiler, they write what the examples show."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from contract_helpers import check_schema

from countdown_api import fixtures

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def requests(tmp_path_factory: pytest.TempPathFactory) -> list[tuple[str, str, str, object]]:
    """Build tests/cpp/main.cpp and return what it prints: each request's method, path, auth and JSON body."""
    compiler = shutil.which("c++")
    if compiler is None:
        pytest.skip("no C++ compiler (c++) to build the headers with")
    program = tmp_path_factory.mktemp("cpp") / "requests"
    # As strict as the firmware's own native build, and warnings fail it.
    flags = ["-std=c++17", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-I", str(ROOT / "cpp")]
    subprocess.run([compiler, *flags, str(ROOT / "tests" / "cpp" / "main.cpp"), "-o", str(program)], check=True)  # noqa: S603
    printed = subprocess.run([str(program)], check=True, capture_output=True, text=True).stdout  # noqa: S603
    found = []
    for line in printed.splitlines():
        method, path, auth, body = line.split(" ", 3)
        found.append((method, path, auth, json.loads(body)))
    return found


def test_registering_is_what_the_examples_send(requests: list[tuple[str, str, str, object]]) -> None:
    touchscreen = fixtures.load("touchscreen.json")
    # A field that isn't set is left out: an e-paper screen says no type, a touchscreen no format.
    assert requests[0] == ("POST", "/api/devices/register", "open", touchscreen["epaper_registration"])
    assert requests[1] == ("POST", "/api/devices/register", "open", touchscreen["registration"])
    for _, _, _, body in requests[:2]:
        check_schema("DeviceRegistration", body)


def test_polling_for_a_frame_is_what_the_example_sends(requests: list[tuple[str, str, str, object]]) -> None:
    assert requests[2] == ("POST", "/api/frame", "secret", fixtures.load("frame_poll.json")["report"])
    assert requests[3] == ("POST", "/api/frame", "secret", {})
    for _, _, _, body in requests[2:]:
        check_schema("FrameReport", body)


def test_a_string_is_escaped_as_json(requests: list[tuple[str, str, str, object]]) -> None:
    line = {"_msg": 'C:\\path\t"quoted"\n\x01 blå', "uptime_ms": 5_000_000_000}
    assert requests[4] == ("POST", "/api/frame", "secret", {"logs": [line]})
