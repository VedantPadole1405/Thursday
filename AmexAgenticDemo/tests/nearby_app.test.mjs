import test from "node:test";
import assert from "node:assert/strict";
import { createNearbyController, parseToolResult } from "../mcp_servers/holidays/ui/controller.mjs";

function harness({ geoError, result, geolocation = true, toolName = "holidays_get_nearby_holidays", connectError } = {}) {
  const nodes = new Map();
  class Element {
    constructor() { this.value = "500"; this.disabled = true; this.textContent = ""; this.children = []; this.events = {}; }
    addEventListener(event, callback) { this.events[event] = callback; }
    replaceChildren() { this.children = []; }
    append(child) { this.children.push(child); }
    click() { return this.events.click(); }
  }
  for (const id of ["radius", "locate", "decline", "status", "results", "place", "search-place"]) nodes.set(id, new Element());
  nodes.get("place").value = "";
  const calls = [];
  const document = { getElementById: (id) => nodes.get(id), createElement: () => new Element() };
  let geoCalls = 0;
  let pendingLocation;
  const app = {
    async connect() { if (connectError) throw new Error("unavailable"); },
    getHostContext() { return { toolInfo: { tool: { name: toolName } } }; },
    async callServerTool(request) {
      calls.push(request);
      return result ?? { structuredContent: { status: "ok", radius_km: 500, holidays: [
        { destination: "Paris", country: "France", distance_km: 0, duration_days: 5, price_usd: 1200 },
      ] } };
    },
  };
  const geo = geolocation ? { getCurrentPosition(resolve, reject, options) {
    geoCalls++;
    assert.equal(options.maximumAge, 0);
    assert.equal(options.enableHighAccuracy, false);
    if (geoError === "pending") { pendingLocation = resolve; return; }
    if (geoError) reject({ code: geoError });
    else resolve({ coords: { latitude: 48.8566, longitude: 2.3522 } });
  } } : undefined;
  const controller = createNearbyController({ app, document, geolocation: geo });
  return { controller, app, nodes, calls, geoCalls: () => geoCalls,
    resolveLocation: () => pendingLocation({ coords: { latitude: 48.8566, longitude: 2.3522 } }) };
}

test("initialization and host tool events do not acquire location; explicit click searches and renders", async () => {
  const h = harness();
  await h.controller.initialize();
  h.app.ontoolresult({ structuredContent: { status: "consent_required", radius_km: 750 } });
  assert.equal(h.geoCalls(), 0);
  assert.equal(h.calls.length, 0);
  assert.equal(h.nodes.get("radius").value, "750");
  await h.nodes.get("locate").click();
  assert.equal(h.geoCalls(), 1);
  assert.deepEqual(h.calls[0], { name: "holidays_get_nearby_holidays", arguments: {
    latitude: 48.8566, longitude: 2.3522, radius_km: 750, location_consent: true,
  } });
  assert.match(h.nodes.get("results").children[0].textContent, /Paris, France/);
  assert.equal(h.nodes.get("locate").disabled, false);
});

for (const [label, error, expected] of [["denied", 1, /permission was denied/], ["unavailable", 2, /unavailable/], ["timeout", 3, /timed out/]]) {
  test(`${label} location does not send coordinates and allows retry`, async () => {
    const h = harness({ geoError: error });
    await h.controller.initialize();
    await h.nodes.get("locate").click();
    assert.equal(h.calls.length, 0);
    assert.match(h.nodes.get("status").textContent, expected);
    assert.equal(h.nodes.get("locate").disabled, false);
  });
}

test("decline avoids location and ignores late geolocation callbacks", async () => {
  const h = harness({ geoError: "pending" });
  await h.controller.initialize();
  h.nodes.get("decline").click();
  assert.equal(h.geoCalls(), 0);
  const lookup = h.nodes.get("locate").click();
  h.nodes.get("decline").click();
  h.resolveLocation();
  await lookup;
  assert.equal(h.calls.length, 0);
  assert.match(h.nodes.get("status").textContent, /declined/);
});

test("unsupported geolocation and invalid radius do not trigger lookup", async () => {
  const h = harness({ geolocation: false });
  await h.controller.initialize();
  await h.nodes.get("locate").click();
  assert.match(h.nodes.get("status").textContent, /unavailable/);
  const v = harness();
  await v.controller.initialize();
  for (const radius of ["", "-1", "0", "20051", "NaN"]) {
    v.nodes.get("radius").value = radius;
    await v.nodes.get("locate").click();
  }
  assert.equal(v.geoCalls(), 0);
});

test("empty results are explained and errors do not reveal raw tool data", async () => {
  const h = harness({ result: { structuredContent: { status: "ok", holidays: [], radius_km: 500 } } });
  await h.controller.initialize();
  await h.nodes.get("locate").click();
  assert.match(h.nodes.get("status").textContent, /No destinations/);
  const e = harness({ result: { isError: true, content: [{ type: "text", text: "secret-location" }] } });
  await e.controller.initialize();
  await e.nodes.get("locate").click();
  assert.doesNotMatch(e.nodes.get("status").textContent, /secret-location/);
  assert.match(e.nodes.get("status").textContent, /unavailable/);
});

test("connection failure or absent host tool context keeps location disabled", async () => {
  for (const options of [{ connectError: true }, { toolName: "" }]) {
    const h = harness(options);
    await h.controller.initialize();
    await h.nodes.get("locate").click();
    assert.equal(h.nodes.get("locate").disabled, true);
    assert.equal(h.geoCalls(), 0);
  }
});

test("parses JSON fallback and FastMCP wrapped results", () => {
  assert.deepEqual(parseToolResult({ content: [{ type: "text", text: '{"status":"ok"}' }] }), { status: "ok" });
  assert.deepEqual(parseToolResult({ structuredContent: { result: { status: "ok" } } }), { status: "ok" });
});

test("repeated clicks do not start concurrent location lookups", async () => {
  const h = harness({ geoError: "pending" });
  await h.controller.initialize();
  const lookup = h.nodes.get("locate").click();
  await h.nodes.get("locate").click();
  assert.equal(h.geoCalls(), 1);
  h.resolveLocation();
  await lookup;
  assert.equal(h.calls.length, 1);
});

test("declining while a tool request is pending ignores its late result", async () => {
  const h = harness();
  let resolveTool;
  h.app.callServerTool = () => new Promise((resolve) => { resolveTool = resolve; });
  await h.controller.initialize();
  const lookup = h.nodes.get("locate").click();
  await Promise.resolve();
  assert.equal(typeof resolveTool, "function");
  h.nodes.get("decline").click();
  resolveTool({ structuredContent: { status: "ok", radius_km: 500, holidays: [
    { destination: "Paris", country: "France", distance_km: 0, duration_days: 5, price_usd: 1200 },
  ] } });
  await lookup;
  assert.equal(h.nodes.get("results").children.length, 0);
  assert.match(h.nodes.get("status").textContent, /declined/);
  assert.equal(h.nodes.get("locate").disabled, false);
});

test("destination markup is rendered as literal text", async () => {
  const markup = '<img src=x onerror="alert(1)">';
  const h = harness({ result: { structuredContent: { status: "ok", radius_km: 500, holidays: [
    { destination: markup, country: "France", distance_km: 0, duration_days: 5, price_usd: 1200 },
  ] } } });
  await h.controller.initialize();
  await h.nodes.get("locate").click();
  const rendered = h.nodes.get("results").children[0];
  assert.ok(rendered.textContent.startsWith(markup));
  assert.equal(rendered.children.length, 0);
  assert.equal(rendered.innerHTML, undefined);
});

test("initial named-place results render without geolocation and survive initialization", async () => {
  const h = harness();
  h.app.ontoolresult({ structuredContent: { status: "ok", radius_km: 500,
    origin: "Mumbai, India", location_source: "named_place", holidays: [
      { destination: "Goa", country: "India", distance_km: 435, duration_days: 5, price_usd: 450 },
    ] } });
  await h.controller.initialize();
  assert.equal(h.geoCalls(), 0);
  assert.equal(h.calls.length, 0);
  assert.match(h.nodes.get("results").children[0].textContent, /Goa/);
  assert.match(h.nodes.get("status").textContent, /Mumbai, India/);
  h.app.ontoolresult({ structuredContent: { status: "consent_required", radius_km: 500 } });
  assert.match(h.nodes.get("status").textContent, /Mumbai, India/);
});

test("unknown named place is explained without requesting device location", async () => {
  const h = harness();
  await h.controller.initialize();
  h.app.ontoolresult({ structuredContent: { status: "location_not_found" } });
  assert.match(h.nodes.get("status").textContent, /place.*not found/i);
  assert.equal(h.geoCalls(), 0);
});

test("named-place retry sends location and radius without device coordinates", async () => {
  const h = harness();
  await h.controller.initialize();
  h.nodes.get("place").value = "mubai";
  h.nodes.get("radius").value = "750";
  await h.nodes.get("search-place").click();
  assert.equal(h.geoCalls(), 0);
  assert.deepEqual(h.calls[0].arguments, { location: "mubai", radius_km: 750 });
});

test("late host notifications do not undo an explicit decline", async () => {
  const h = harness();
  await h.controller.initialize();
  h.nodes.get("decline").click();
  h.app.ontoolresult({ structuredContent: { status: "ok", radius_km: 500, origin: "Mumbai, India", holidays: [
    { destination: "Goa", country: "India", distance_km: 435, duration_days: 5, price_usd: 450 },
  ] } });
  assert.equal(h.nodes.get("results").children.length, 0);
  assert.match(h.nodes.get("status").textContent, /declined/);
});
