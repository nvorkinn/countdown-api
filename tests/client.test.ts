// client.ts against a fake fetch: what each kind of route sends, and what it answers. Run by `node --test tests/`
// (Node strips the types). The types themselves are tsc's (tsconfig.json).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  type Client,
  connectParcelPageUrl,
  deviceSettingsPageUrl,
  getBackgroundImageUrl,
  getConfig,
  getFeedUrl,
  putConfig,
  registerDevice,
  registerTouchscreenUrl,
} from "../src/countdown_api/client.ts";

interface Sent {
  url: string;
  method: string | undefined;
  headers: Headers;
  body: unknown;
}

function fakeServer(status: number, body: unknown, contentType = "application/json"): { client: Client; sent: Sent[] } {
  const sent: Sent[] = [];
  const fetch = async (input: string | URL | Request, init: RequestInit = {}): Promise<Response> => {
    sent.push({
      url: String(input),
      method: init.method,
      headers: new Headers(init.headers),
      body: init.body === undefined ? undefined : JSON.parse(String(init.body)),
    });
    const text = typeof body === "string" ? body : JSON.stringify(body);
    return new Response(text, { status, headers: { "Content-Type": contentType } });
  };
  return { client: { baseUrl: "https://api.example.com", secret: "s3cret-s3cret-s3cret", fetch }, sent };
}

test("a device-secret route sends the secret and answers the JSON", async () => {
  const { client, sent } = fakeServer(200, { device_id: "a1b2c3d4e5f6" });
  const { data, error } = await getConfig(client);
  assert.deepEqual(data, { device_id: "a1b2c3d4e5f6" });
  assert.equal(error, undefined);
  assert.equal(sent[0]?.url, "https://api.example.com/api/devices/config");
  assert.equal(sent[0]?.method, "GET");
  assert.equal(sent[0]?.headers.get("Authorization"), "Bearer s3cret-s3cret-s3cret");
});

test("a body goes as JSON, with the caller's headers", async () => {
  const { client, sent } = fakeServer(200, {});
  const config = { type: "touchscreen" } as unknown as Parameters<typeof putConfig>[1];
  await putConfig(client, config, { headers: { "If-Match": '"v1"' } });
  assert.equal(sent[0]?.method, "PUT");
  assert.deepEqual(sent[0]?.body, { type: "touchscreen" });
  assert.equal(sent[0]?.headers.get("Content-Type"), "application/json");
  assert.equal(sent[0]?.headers.get("If-Match"), '"v1"');
});

test("a route without the device secret doesn't send it", async () => {
  const { client, sent } = fakeServer(201, { device_id: "a1b2c3d4e5f6" });
  const { response } = await registerDevice(client, {
    secret: "s3cret-s3cret-s3cret",
    width: 1024,
    height: 600,
  } as never);
  assert.equal(response.status, 201);
  assert.equal(sent[0]?.headers.get("Authorization"), null);
});

test("anything but a 2xx is the error body, JSON or text", async () => {
  const json = fakeServer(401, { error: "unauthorized" });
  const { data, error, response } = await getConfig(json.client);
  assert.equal(data, undefined);
  assert.deepEqual(error, { error: "unauthorized" });
  assert.equal(response.status, 401);

  const text = fakeServer(502, "Bad Gateway", "text/plain");
  assert.equal((await getConfig(text.client)).error, "Bad Gateway");
});

test("a device-secret route with no secret throws before it fetches", async () => {
  const { client, sent } = fakeServer(200, {});
  await assert.rejects(getConfig({ ...client, secret: "" }), /needs the device's secret/);
  assert.equal(sent.length, 0);
});

test("a page's address takes its path and query parameters", () => {
  const hash = "0".repeat(64);
  const register = registerTouchscreenUrl("https://example.com", { secret_hash: hash, width: 1024, height: 600 });
  assert.equal(register.href, `https://example.com/register?secret_hash=${hash}&width=1024&height=600`);
  assert.equal(
    deviceSettingsPageUrl("https://example.com/", { device_id: "a1b2/c3" }, { embed: "1" }).href,
    "https://example.com/device/a1b2%2Fc3?embed=1",
  );
  assert.equal(deviceSettingsPageUrl("https://example.com", { device_id: "a1b2c3d4e5f6" }).search, "");
  assert.equal(connectParcelPageUrl("https://example.com/").href, "https://example.com/account/parcel");
});

test("an image's address is its digest on the devices' API", () => {
  const digest = "ab".repeat(32);
  assert.equal(
    getBackgroundImageUrl("https://api.example.com", { digest }).href,
    `https://api.example.com/api/backgrounds/${digest}`,
  );
});

test("the event stream is an address the device reads itself", () => {
  assert.equal(getFeedUrl("https://api.example.com").href, "https://api.example.com/api/devices/feed");
});
