# Nearby holiday recommendations

The Holidays MCP server provides `get_nearby_holidays` and an MCP App. It searches
the existing six simulated destinations using Haversine great-circle distance.
Distances and radius are kilometers, the default radius is 500 km, and the valid
range is greater than zero through 20050 km. Destinations are sorted nearest first.
This is demonstration travel data, not a live booking service.

## Named places from chat

The chat host should extract a place from a request such as "holidays near mubai"
and call `get_nearby_holidays` with `location: "mubai"`. Named places take priority
over device coordinates and do not require device-location consent. Mumbai,
Bombay, the typo mubai, and catalog destinations resolve locally. Other place
names are sent to [Open-Meteo's geocoding API](https://open-meteo.com/en/docs/geocoding-api)
(GeoNames data); this requires internet access. No device coordinates are sent
to that provider. Unknown, ambiguous, or unavailable lookups show a correction
or retry message and never silently switch to the user's device location.
Specify a country or region to disambiguate common names.

The app displays the resolved origin and recommendations immediately from the
host's initial tool result. Its place field lets users retry with a different
place or radius. Mumbai's default 500 km search includes Goa in this simulated
catalog. When no place is named, the app offers the device-location flow below.

## Run locally

From `AmexAgenticDemo`, with Python 3.11+ and Node.js 22.12+:

```sh
python -m pip install -r requirements.txt
npm ci
npm run build:holidays
python -m mcp_servers.holidays.server
```

The server listens on `http://127.0.0.1:8003/mcp`. The existing gateway at
`http://127.0.0.1:8000/mcp` mounts it under the `holidays` namespace. Connect an
MCP Apps capable chat host to either endpoint. Call `get_nearby_holidays` (or
`holidays_get_nearby_holidays` through the gateway) without coordinates to open
the app. Build the UI before serving it; generated `dist/` files are ignored.

## Consent and privacy

The app does not call geolocation on load, on tool notifications, or when the
radius changes. The user must choose **Use my location** each time. This allows
a single browser lookup and sends the coordinates through the host to the MCP
tool with `location_consent: true`. Browser permission is still required, even
if the user has clicked the button. **No thanks** cancels the app's pending
lookup and ignores late results. It cannot retract a request already sent.

The app and service do not store or log user coordinates, retain them between
searches, or return the search origin in tool results. Catalog destination
coordinates are public simulation data and remain in results. The host handles
tool transport and may process requests under its own privacy policies; avoid
enabling external request/body debug logging when using real location.
`location_consent` is a caller assertion, not server authentication. App visibility
and browser permission cannot authenticate arbitrary direct MCP callers.

The resource requests `_meta.ui.permissions.geolocation`. The host must delegate
geolocation to the sandbox iframe and the browser must provide a secure context.
Some hosts do not support this permission. The app explains denied permission,
unavailable or timed-out location, missing host context, and empty results without
requesting IP lookup or falling back to stored location. Users can instead ask
for holidays by destination. The host must supply `toolInfo.tool.name`, which
lets callbacks use the actual namespaced gateway tool.

## Verification

```sh
npm test
npm run build:holidays
python -m unittest discover -s tests -p test_nearby_holidays.py -v
```

The Node tests exercise the UI controller with simulated browser and MCP host
dependencies. Python tests cover distance filtering and validation, real MCP
tool calls, and a namespaced proxy's tool/resource metadata and UI reads. They
are offline and never acquire real location. Existing `test_holidays.py` and
`test_gateway.py` are manual live-server smoke scripts.

An optional smoke check in a particular chat host can confirm that opening the app does
not prompt for location, that **Use my location** triggers its permission flow,
and that denied/allowed location is reflected in the app. Host sandbox permission
delegation cannot be established by the offline test suite.

Protocol references: [FastMCP custom HTML apps](https://gofastmcp.com/apps/low-level)
and [MCP Apps resource permissions](https://apps.extensions.modelcontextprotocol.io/api/interfaces/app.McpUiResourcePermissions.html).
