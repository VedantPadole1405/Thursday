
import json
import math
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastmcp import FastMCP
from fastmcp.apps import AppConfig, ResourcePermissions
from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from pydantic import BaseModel, Field


# ==========================================
# 1. INITIALIZE FASTAPI + FASTMCP
# ==========================================

api = FastAPI(
    title="Holidays REST API",
    version="1.0.0"
)

mcp = FastMCP(name="Holidays MCP Server")


class NearbyPrivacyMiddleware(Middleware):
    """Reject malformed location arguments before SDK validation can log their values."""

    async def on_call_tool(self, context, call_next):
        if context.message.name == "get_nearby_holidays":
            arguments = context.message.arguments or {}
            allowed = {"latitude", "longitude", "radius_km", "location_consent"}
            invalid = bool(set(arguments) - allowed)
            for name in ("latitude", "longitude", "radius_km"):
                value = arguments.get(name)
                if value is None and name != "radius_km":
                    continue
                if name in arguments and (
                    isinstance(value, bool) or not isinstance(value, (int, float))
                ):
                    invalid = True
                elif name in arguments:
                    try:
                        invalid = invalid or not math.isfinite(value)
                    except OverflowError:
                        invalid = True
            if "location_consent" in arguments and not isinstance(arguments["location_consent"], bool):
                invalid = True
            if invalid:
                return ToolResult(structured_content={
                    "status": "invalid_request",
                    "message": "Location and radius must be numbers, with explicit boolean consent.",
                })
        return await call_next(context)


mcp.add_middleware(NearbyPrivacyMiddleware())

NEARBY_UI_URI = "ui://holidays/nearby"
NEARBY_UI_FILE = Path(__file__).parent / "ui" / "dist" / "nearby.html"
DEFAULT_RADIUS_KM = 500
MAX_RADIUS_KM = 20050


# ==========================================
# 2. HOLIDAY DATA MODEL
# ==========================================

class HolidayPackage(BaseModel):
    holiday_id: str
    destination: str
    country: str
    latitude: float
    longitude: float
    duration_days: int
    price_usd: float
    category: Literal[
        "Beach", "City", "Adventure", "Luxury", "Nature"
    ]
    description: str

# ==========================================
# 3. IN-MEMORY HOLIDAY CATALOG
# ==========================================

HOLIDAY_CATALOG = [
    HolidayPackage(
        holiday_id="HOL001",
        destination="Paris",
        country="France",
        latitude=48.8566,
        longitude=2.3522,
        duration_days=5,
        price_usd=1200,
        category="City",
        description="Museums, landmarks and sightseeing"
    ),
    HolidayPackage(
        holiday_id="HOL002",
        destination="Bali",
        country="Indonesia",
        latitude=-8.3405,
        longitude=115.0920,
        duration_days=7,
        price_usd=950,
        category="Beach",
        description="Beaches, temples and tropical resorts"
    ),
    HolidayPackage(
        holiday_id="HOL003",
        destination="Tokyo",
        country="Japan",
        latitude=35.6762,
        longitude=139.6503,
        duration_days=6,
        price_usd=1500,
        category="City",
        description="Technology, culture and city exploration"
    ),
    HolidayPackage(
        holiday_id="HOL004",
        destination="Dubai",
        country="UAE",
        latitude=25.276987,
        longitude=55.296249,
        duration_days=4,
        price_usd=800,
        category="Luxury",
        description="Desert experiences and modern attractions"
    ),
    HolidayPackage(
        holiday_id="HOL005",
        destination="Goa",
        country="India",
        latitude=15.2993,
        longitude=74.1240,
        duration_days=5,
        price_usd=450,
        category="Beach",
        description="Beaches, heritage and coastal sightseeing"
    ),
    HolidayPackage(
        holiday_id="HOL006",
        destination="Swiss Alps",
        country="Switzerland",
        latitude=46.8182,
        longitude=8.2275,
        duration_days=6,
        price_usd=1800,
        category="Nature",
        description="Mountain scenery, hiking and alpine villages"
    )
]


import httpx
from datetime import date


@mcp.tool()
async def get_destination_weather(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str
) -> dict:
    """
    Get daily weather forecasts for a holiday destination.

    Dates must be YYYY-MM-DD.
    Forecast availability depends on the weather provider.
    """

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if end < start:
        raise ValueError("End date must be after start date")

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": (
            "precipitation_sum,"
            "precipitation_probability_max,"
            "weather_code,"
            "temperature_2m_max"
        ),
        "timezone": "auto",
        "start_date": start_date,
        "end_date": end_date
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    return {
        "latitude": latitude,
        "longitude": longitude,
        "daily": data.get("daily", {}),
        "source": "Open-Meteo",
        "forecast_available": bool(data.get("daily", {}).get("time"))
    }


# ==========================================
# 4. BUSINESS LOGIC
# ==========================================

def get_all_holidays() -> list[dict]:
    return [
        package.model_dump()
        for package in HOLIDAY_CATALOG
    ]


def find_holiday(holiday_id: str) -> dict:
    for package in HOLIDAY_CATALOG:
        if package.holiday_id == holiday_id:
            return package.model_dump()

    raise ValueError(
        f"Holiday package {holiday_id} not found"
    )


def filter_holidays(
    destination: str | None = None,
    max_budget: float | None = None,
    max_days: int | None = None,
    category: str | None = None
) -> list[dict]:

    results = get_all_holidays()

    if destination:
        query = destination.lower()

        results = [
            h for h in results
            if query in (
                h["destination"] + " " + h["country"]
            ).lower()
        ]

    if max_budget is not None:
        results = [
            h for h in results
            if h["price_usd"] <= max_budget
        ]

    if max_days is not None:
        results = [
            h for h in results
            if h["duration_days"] <= max_days
        ]

    if category:
        results = [
            h for h in results
            if h["category"].lower() == category.lower()
        ]

    return results


# ==========================================
# 5. MCP TOOLS
# ==========================================

def nearby_holidays(latitude: float, longitude: float, radius_km: float) -> list[dict]:
    """Filter the simulation catalog using great-circle distance, without retaining location."""
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180")
    if not math.isfinite(radius_km) or not 0 < radius_km <= MAX_RADIUS_KM:
        raise ValueError(f"Radius must be greater than 0 and at most {MAX_RADIUS_KM} km")

    matches = []
    lat1 = math.radians(latitude)
    for package in get_all_holidays():
        lat2 = math.radians(package["latitude"])
        delta_lat = lat2 - lat1
        delta_lon = math.radians(package["longitude"] - longitude)
        haversine = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        )
        distance = 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, haversine))))
        # Filter before rounding so a destination outside the radius never slips in.
        if distance <= radius_km:
            matches.append((distance, package))
    return [
        {**package, "distance_km": round(distance, 2)}
        for distance, package in sorted(matches, key=lambda item: (item[0], item[1]["holiday_id"]))
    ]


@mcp.tool(
    app=AppConfig(resource_uri=NEARBY_UI_URI),
    annotations={"readOnlyHint": True, "openWorldHint": False},
)
def get_nearby_holidays(
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float = DEFAULT_RADIUS_KM,
    location_consent: bool = False,
) -> dict:
    """Open the Nearby Holidays consent app by calling without coordinates.

    Only the app should submit coordinates, after the user's explicit consent.
    Search the simulated catalog within radius_km (0 < radius <= 20050 km).
    User coordinates are used transiently and are never returned or persisted.
    """
    if not math.isfinite(radius_km) or not 0 < radius_km <= MAX_RADIUS_KM:
        return {"status": "invalid_request", "message": "Choose a radius greater than 0 and at most 20050 km."}
    if latitude is None and longitude is None:
        return {"status": "consent_required", "radius_km": radius_km}
    if not location_consent:
        return {"status": "consent_required", "radius_km": radius_km}
    if latitude is None or longitude is None:
        return {"status": "invalid_request", "message": "Both coordinates are required."}
    try:
        results = nearby_holidays(latitude, longitude, radius_km)
    except ValueError:
        # Do not echo submitted coordinates in results or error messages.
        return {"status": "invalid_request", "message": "Location or radius is outside the supported range."}
    return {"status": "ok", "radius_km": radius_km, "holidays": results}


@mcp.resource(
    NEARBY_UI_URI,
    mime_type="text/html;profile=mcp-app",
    app=AppConfig(permissions=ResourcePermissions(geolocation={})),
)
def nearby_holidays_ui() -> str:
    """Serve the self-contained MCP App and request host geolocation delegation."""
    if not NEARBY_UI_FILE.is_file():
        raise FileNotFoundError("Build the Nearby Holidays UI with npm run build:holidays")
    return NEARBY_UI_FILE.read_text(encoding="utf-8")


@mcp.tool()
def list_holidays() -> list[dict]:
    """List all available simulated holiday packages."""

    return get_all_holidays()


@mcp.tool()
def search_holidays(
    destination: str | None = None,
    max_budget: float | None = None,
    max_days: int | None = None,
    category: str | None = None
) -> list[dict]:
    """Search holiday packages using filters."""

    return filter_holidays(
        destination=destination,
        max_budget=max_budget,
        max_days=max_days,
        category=category
    )


@mcp.tool()
def get_holiday_details(holiday_id: str) -> dict:
    """Get the details of a holiday package."""

    return find_holiday(holiday_id)


@mcp.tool()
def recommend_holiday(
    budget: float,
    max_days: int | None = None,
    category: str | None = None
) -> list[dict]:
    """Recommend simulated holidays within a budget."""

    if budget < 0:
        raise ValueError("Budget cannot be negative")

    results = filter_holidays(
        max_budget=budget,
        max_days=max_days,
        category=category
    )

    return sorted(
        results,
        key=lambda h: h["price_usd"]
    )


# ==========================================
# 6. MCP RESOURCES
# ==========================================

@mcp.resource("holidays://catalog")
def holiday_catalog_resource() -> str:
    """Read the full holiday catalog."""

    return json.dumps(
        get_all_holidays(),
        indent=2
    )


@mcp.resource("holidays://policies")
def holiday_policies() -> str:
    """Read holiday service policies."""

    return json.dumps({
        "service": "Holidays",
        "version": "1.0.0",
        "mode": "simulation",
        "currency": "USD",
        "booking_enabled": False,
        "prices_are_live": False,
        "flight_included": False,
        "payment_required": False,
        "rules": [
            "Prices are illustrative only",
            "No real travel reservations are made",
            "All packages are demonstration data"
        ]
    }, indent=2)


@mcp.resource("holidays://service-info")
def holiday_service_info() -> str:
    """Read information about the Holidays MCP Server."""

    return json.dumps({
        "name": "Holidays MCP Server",
        "version": "1.0.0",
        "tools": [
            "list_holidays",
            "search_holidays",
            "get_holiday_details",
            "recommend_holiday",
            "get_nearby_holidays"
        ]
    }, indent=2)


@mcp.resource("holidays://packages/{holiday_id}")
def holiday_package_resource(holiday_id: str) -> str:
    """Read an individual holiday package."""

    return json.dumps(
        find_holiday(holiday_id),
        indent=2
    )


# ==========================================
# 7. FASTAPI REST ENDPOINTS
# ==========================================

@api.get("/holidays")
def list_holidays_api(
    max_budget: float | None = Query(default=None, ge=0),
    max_days: int | None = Query(default=None, gt=0),
    category: str | None = None
):
    return filter_holidays(
        max_budget=max_budget,
        max_days=max_days,
        category=category
    )


@api.get("/holidays/{holiday_id}")
def get_holiday_api(holiday_id: str):
    try:
        return find_holiday(holiday_id)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error)
        )


# ==========================================
# 8. COMBINE MCP AND FASTAPI
# ==========================================

mcp_app = mcp.http_app(path="/mcp")

app = FastAPI(
    title="Holidays API + MCP Server",
    version="1.0.0",
    routes=[
        *mcp_app.routes,
        *api.routes
    ],
    lifespan=mcp_app.lifespan
)


# ==========================================
# 9. START SERVER
# ==========================================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8003
    )
