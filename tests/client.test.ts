// client.ts against a fake fetch: what each kind of route sends, and what it answers. Run by `node --test tests/`
// (Node strips the types). The types themselves are tsc's (tsconfig.json).
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  type Client,
  connectParcelPageUrl,
  createSoloistKeyCode,
  deleteSoloistKey,
  deviceSettingsPageUrl,
  getBackgroundImageUrl,
  getConfig,
  getFeedUrl,
  getSetup,
  getSoloistKey,
  listSoloistKeys,
  locateDevice,
  lookupPostcode,
  putConfig,
  registerDevice,
  registerTouchscreenUrl,
  reportSetup,
  saveSoloistKeyPageUrl,
  stopsNear,
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
    // A 204 has no body, and Response refuses one.
    return new Response(status === 204 ? null : text, { status, headers: { "Content-Type": contentType } });
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

test("a person's Soloist key is saved by a code the device asks for and shows as a link", async () => {
  const code = "9f2c4e6a8b0d1f3a5c7e9b1d3f5a7c9e";
  const made = fakeServer(201, { code, expires_in: 600 });
  assert.equal((await createSoloistKeyCode(made.client, { person: "wizzler" })).data?.code, code);
  assert.equal(made.sent[0]?.method, "POST");
  assert.equal(made.sent[0]?.url, "https://api.example.com/api/devices/soloist/codes");
  assert.deepEqual(made.sent[0]?.body, { person: "wizzler" });

  assert.equal(
    saveSoloistKeyPageUrl("https://example.com/", { code }).href,
    `https://example.com/soloist?code=${code}`,
  );

  const listed = fakeServer(200, { people: ["wizzler"] });
  assert.deepEqual((await listSoloistKeys(listed.client)).data?.people, ["wizzler"]);
  assert.equal(listed.sent[0]?.url, "https://api.example.com/api/devices/soloist/keys");
});

test("a person's key is asked for and forgotten by the device's name for them", async () => {
  const key = fakeServer(200, { api_key: "k" });
  await getSoloistKey(key.client, { person: "a b" });
  assert.equal(key.sent[0]?.url, "https://api.example.com/api/devices/soloist/key?person=a+b");

  const removed = fakeServer(204, "");
  const { response } = await deleteSoloistKey(removed.client, { person: "wizzler" });
  assert.equal(response.status, 204);
  assert.equal(removed.sent[0]?.method, "DELETE");
  assert.equal(removed.sent[0]?.url, "https://api.example.com/api/devices/soloist/keys/wizzler");
});

test("a setup wizard's location step sends the Wi-Fi it sees, a typed postcode, and a position", async () => {
  const wifi = [
    { mac_address: "a4:2b:b0:5c:1e:7f", signal_strength: -48 },
    { mac_address: "9c:c9:eb:21:4d:10", signal_strength: -63, channel: 36 },
  ];
  const located = fakeServer(200, { latitude: 51.48471, longitude: -0.09192, accuracy: 28.5, postcodes: [] });
  assert.equal((await locateDevice(located.client, { wifi_access_points: wifi })).data?.accuracy, 28.5);
  assert.equal(located.sent[0]?.method, "POST");
  assert.equal(located.sent[0]?.url, "https://api.example.com/api/devices/locate");
  assert.equal(located.sent[0]?.headers.get("Authorization"), "Bearer s3cret-s3cret-s3cret");
  assert.deepEqual(located.sent[0]?.body, { wifi_access_points: wifi });

  const throttled = fakeServer(429, { error: "slow down" });
  const { error, response } = await locateDevice(throttled.client, { wifi_access_points: wifi });
  assert.deepEqual(error, { error: "slow down" });
  assert.equal(response.status, 429);

  const postcode = fakeServer(200, {
    postcode: "SE17 2PU",
    latitude: 51.484787,
    longitude: -0.091724,
    country: "England",
  });
  assert.equal((await lookupPostcode(postcode.client, { postcode: "se17 2pu" })).data?.postcode, "SE17 2PU");
  assert.equal(postcode.sent[0]?.url, "https://api.example.com/api/postcodes/lookup?postcode=se17+2pu");

  const near = fakeServer(200, []);
  assert.deepEqual((await stopsNear(near.client, { latitude: 51.484787, longitude: -0.091724 })).data, []);
  assert.equal(near.sent[0]?.url, "https://api.example.com/api/stops/near?latitude=51.484787&longitude=-0.091724");
});

test("a touchscreen reports its side of its setup and asks which step it is at", async () => {
  const challenge = {
    client_id: "79012ca710ca4dd5ad18c2973510b670",
    code_challenge: "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    scope: "user-read-private",
  };
  const reported = fakeServer(200, { step: "account" });
  assert.equal((await reportSetup(reported.client, { spotify: challenge })).data?.step, "account");
  assert.equal(reported.sent[0]?.method, "PUT");
  assert.equal(reported.sent[0]?.url, "https://api.example.com/api/devices/setup");
  assert.equal(reported.sent[0]?.headers.get("Authorization"), "Bearer s3cret-s3cret-s3cret");
  assert.deepEqual(reported.sent[0]?.body, { spotify: challenge });

  const signIn = { id: "4b7d1e9a3c5f2a8d6e0b9c1f7a3d5e2b", redirect_uri: "https://app.example.com/cb", expires_in: 600 };
  const asked = fakeServer(200, { step: "spotify", spotify_sign_in: signIn });
  assert.deepEqual((await getSetup(asked.client)).data?.spotify_sign_in, signIn);
  assert.equal(asked.sent[0]?.method, "GET");
  assert.equal(asked.sent[0]?.url, "https://api.example.com/api/devices/setup");

  // A touchscreen that has reported nothing doesn't take part.
  const apart = fakeServer(404, { error: "no setup" });
  assert.equal((await getSetup(apart.client)).response.status, 404);
});
