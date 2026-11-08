// Inject browser and MCP dependencies so the full consent flow can be tested offline.
export function parseToolResult(result) {
  if (result?.isError) throw new Error("Search unavailable");
  let data = result?.structuredContent;
  if (!data) {
    const text = result?.content?.find((item) => item.type === "text")?.text;
    if (text) data = JSON.parse(text);
  }
  return data?.result ?? data;
}

export function createNearbyController({ app, document, geolocation }) {
  const $ = (id) => document.getElementById(id);
  let connected = false;
  let busy = false;
  let generation = 0;
  let toolName;
  let hasDisplay = false;
  const status = (text) => { $("status").textContent = text; };
  const clear = () => $("results").replaceChildren();
  const setBusy = (value) => {
    busy = value;
    $("locate").disabled = value || !connected;
    $("radius").disabled = value;
    $("place").disabled = value;
    $("search-place").disabled = value || !connected;
  };

  function showResult(data) {
    clear();
    hasDisplay = true;
    const placeErrors = {
      location_not_found: "Place was not found. Check the spelling or add a country. Device location was not used.",
      location_ambiguous: "Several places match. Add a country or region. Device location was not used.",
      location_unavailable: "Place lookup is unavailable. Please retry. Device location was not used.",
    };
    if (placeErrors[data?.status]) {
      status(placeErrors[data.status]);
      return;
    }
    if (data?.status !== "ok" || !Array.isArray(data.holidays)) {
      status("Unable to search. Check your radius and try again.");
      return;
    }
    if (!data.holidays.length) {
      status(`No destinations within ${data.radius_km} km of ${data.origin ?? "your device location"}. Try a larger radius and search again.`);
      return;
    }
    for (const holiday of data.holidays) {
      const item = document.createElement("li");
      // Tool data is text, never HTML.
      item.textContent = `${holiday.destination}, ${holiday.country} — ${holiday.distance_km} km · ${holiday.duration_days} days · USD ${holiday.price_usd}`;
      $("results").append(item);
    }
    status(`${data.holidays.length} destination(s) within ${data.radius_km} km of ${data.origin ?? "your device location"}. Nearest first.`);
  }

  async function searchPlace() {
    if (!connected || busy) return;
    const location = $("place").value.trim();
    const radius = Number($("radius").value);
    if (!location) {
      status("Enter a place name, or choose Use my location for a device search.");
      return;
    }
    if (!Number.isFinite(radius) || radius <= 0 || radius > 20050) {
      status("Choose a radius greater than 0 and at most 20050 km.");
      return;
    }
    const request = ++generation;
    clear();
    setBusy(true);
    status("Finding holidays near the named place...");
    try {
      const result = await app.callServerTool({ name: toolName, arguments: { location, radius_km: radius } });
      if (request === generation) showResult(parseToolResult(result));
    } catch {
      if (request === generation) status("Place lookup is unavailable. Please retry. Device location was not used.");
    } finally {
      if (request === generation) setBusy(false);
    }
  }

  async function locate() {
    if (!connected || busy) return;
    clear();
    const radius = Number($("radius").value);
    if (!Number.isFinite(radius) || radius <= 0 || radius > 20050) {
      status("Choose a radius greater than 0 and at most 20050 km.");
      return;
    }
    if (!geolocation) {
      status("Location is unavailable in this chat host or browser. You can still ask for holidays by destination.");
      return;
    }
    const request = ++generation;
    setBusy(true);
    status("Waiting for location permission…");
    try {
      // Called only from an explicit click; never on app load or a host event.
      const position = await new Promise((resolve, reject) => {
        geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: false, timeout: 10000, maximumAge: 0,
        });
      });
      if (request !== generation) return;
      const { latitude, longitude } = position.coords;
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)
          || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
        status("A valid location was not available. Please try again.");
        return;
      }
      status("Finding nearby destinations…");
      const result = await app.callServerTool({ name: toolName, arguments: {
        latitude, longitude, radius_km: radius, location_consent: true,
      } });
      if (request === generation) showResult(parseToolResult(result));
    } catch (error) {
      if (request !== generation) return;
      // Never render/log exception messages that could contain coordinates.
      if (error?.code === 1) status("Location permission was denied. No search was sent. You can try again or ask for holidays by destination.");
      else if (error?.code === 3) status("Location lookup timed out. Please try again.");
      else status("Location or holiday search is unavailable. Please try again or ask for holidays by destination.");
    } finally {
      if (request === generation) setBusy(false);
    }
  }

  $("locate").addEventListener("click", locate);
  $("search-place").addEventListener("click", searchPlace);
  $("decline").addEventListener("click", () => {
    // Invalidate pending browser callbacks/tool responses after declining.
    generation += 1;
    hasDisplay = true;
    clear();
    setBusy(false);
    status("Location declined. Ask for holidays by destination, or choose Use my location if you change your mind.");
  });
  app.ontoolresult = (result) => {
    // Host results can display named-place recommendations without geolocation.
    try {
      const data = parseToolResult(result);
      if (busy) return;
      if (data?.status === "ok" || data?.status?.startsWith("location_") || data?.status === "invalid_request") {
        if (Number.isFinite(data.radius_km)) $("radius").value = String(data.radius_km);
        if (data.location_source === "named_place") $("place").value = data.origin;
        showResult(data);
      } else if (!hasDisplay && data?.status === "consent_required" && Number.isFinite(data.radius_km)) {
        $("radius").value = String(data.radius_km);
      }
    } catch { /* Keep consent controls available if the initial result is invalid. */ }
  };

  return { async initialize() {
    try {
      await app.connect();
      // Use the host's advertised name so gateway namespace prefixes are preserved.
      toolName = app.getHostContext()?.toolInfo?.tool?.name;
      if (!toolName || !/(^|_)get_nearby_holidays$/.test(toolName)) {
        status("This host did not provide the nearby search tool context. Reopen the app from get_nearby_holidays in a compatible MCP Apps host.");
        return;
      }
      connected = true;
      setBusy(false);
      if (!hasDisplay) status("Enter a place to search, or choose Use my location to allow a one-time device search.");
    } catch {
      status("Unable to connect to the chat host. Reopen the app in an MCP Apps compatible host.");
    }
  } };
}
