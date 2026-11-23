// What tests/test_cpp.py builds against cpp/countdown_api and runs: it prints each request the canonical examples
// describe, a line each (method, path, whether it takes the secret, then the body), for the test to read.
#include <cstdio>
#include <string>

#include "countdown_api/api.h"

namespace api = countdown_api;

namespace {

void print(const api::Request& request) {
  std::printf("%s %s %s %s\n", request.method, request.path.c_str(), request.secret ? "secret" : "open",
              request.body.c_str());
}

}  // namespace

int main() {
  // touchscreen.json's epaper_registration.
  api::DeviceRegistration epaper;
  epaper.secret = "example-not-a-real-secret-0002";
  epaper.width = 800;
  epaper.height = 480;
  epaper.format = api::DeviceRegistration::FormatEnum::Mono1bppPacked;
  print(api::registerDevice(epaper));

  // touchscreen.json's registration.
  api::DeviceRegistration touchscreen;
  touchscreen.secret = "example-not-a-real-secret-0001";
  touchscreen.type = api::DeviceType::Touchscreen;
  touchscreen.width = 1280;
  touchscreen.height = 800;
  touchscreen.brightness_control = false;
  print(api::registerDevice(touchscreen));

  // frame_poll.json's report.
  api::FrameReport report;
  report.metrics = "esp32,device_id={device_id} uptime_s=3600i,free_heap=182344i,wifi_rssi=-61i,logs_dropped=0i";
  api::FrameLogEntry first;
  first.level = api::FrameLogEntry::LevelEnum::Info;
  first._msg = "Frame response: HTTP 304 (0 bytes), Retry-After: \"27\" seconds";
  first.uptime_ms = 3570041;
  api::FrameLogEntry second;
  second.level = api::FrameLogEntry::LevelEnum::Warn;
  second._msg = "Couldn't fetch the frame: connection lost; sleeping for 60 seconds";
  second.uptime_ms = 3600512;
  report.logs = {first, second};
  print(api::pollFrame(report));

  // Nothing to report, and a line a JSON string has to escape: a backslash, a tab, a newline, a control character,
  // UTF-8 as it is, and an uptime past 32 bits.
  print(api::pollFrame({}));
  api::FrameReport awkward;
  api::FrameLogEntry line;
  line._msg = "C:\\path\t\"quoted\"\n\x01 bl\xC3\xA5";
  line.uptime_ms = 5000000000;
  awkward.logs = {line};
  print(api::pollFrame(awkward));
  return 0;
}
