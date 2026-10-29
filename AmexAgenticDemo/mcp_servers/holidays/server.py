
import json
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastmcp import FastMCP
from pydantic import BaseModel, Field


# ==========================================
# 1. INITIALIZE FASTAPI + FASTMCP
# ==========================================

api = FastAPI(
    title="Holidays REST API",
    version="1.0.0"
)

mcp = FastMCP(name="Holidays MCP Server")


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
            "recommend_holiday"
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
