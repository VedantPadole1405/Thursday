
"""LangGraph workflow for weather-aware holiday recommendations."""

import asyncio
import json
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, START, END

from mcp_clients.holidays_client import HolidaysMCPClient
from langgraph_host.skill_loader import load_skill


# ==========================================
# 1. LANGGRAPH STATE
# ==========================================

class HolidayState(TypedDict, total=False):
    budget: float
    start_date: str
    end_date: str
    skill: str
    packages: list[dict]
    recommendations: list[dict]
    errors: list[str]


# ==========================================
# 2. LOAD HOLIDAY PLANNING SKILL
# ==========================================

async def load_skill_node(state: HolidayState) -> dict:
    """
    Load holiday-planner/SKILL.md into graph state.
    """

    skill = load_skill("holidays")

    print("\n[SKILL] Holiday Planning Skill loaded")
    print(f"[SKILL] Instructions: {len(skill)} characters")

    return {
        "skill": skill
    }


# ==========================================
# 3. FETCH HOLIDAY PACKAGES THROUGH MCP
# ==========================================

async def fetch_holidays_node(state: HolidayState) -> dict:
    """
    Connect to MCP Gateway and retrieve holiday packages
    matching the user's budget.
    """

    print("\n[HOLIDAYS] Connecting to MCP Gateway...")

    async with HolidaysMCPClient() as client:

        await client.discover_tools()

        packages = await client.recommend_holiday(
            budget=state["budget"]
        )

    if not isinstance(packages, list):
        raise RuntimeError(
            "Expected a list of holiday packages"
        )

    print(
        f"[HOLIDAYS] Found {len(packages)} packages "
        f"under ${state['budget']}"
    )

    return {
        "packages": packages
    }


# ==========================================
# 4. WEATHER EVALUATION
# ==========================================

async def evaluate_weather_node(state: HolidayState) -> dict:
    """
    Evaluate weather for all holiday packages concurrently.

    Each destination gets its own MCP client connection
    to avoid concurrent operations on the same session.
    """

    packages = state.get("packages", [])

    if not packages:
        print("[WEATHER] No packages to evaluate")

        return {
            "recommendations": []
        }

    print(
        f"\n[WEATHER] Checking {len(packages)} "
        "destinations concurrently..."
    )

    semaphore = asyncio.Semaphore(3)

    async def check_destination(package: dict) -> dict:

        async with semaphore:
            try:
                print(
                    f"[WEATHER] Checking "
                    f"{package['destination']}..."
                )

                async with HolidaysMCPClient() as client:

                    await client.discover_tools()

                    weather = await client.get_destination_weather(
                        latitude=package["latitude"],
                        longitude=package["longitude"],
                        start_date=state["start_date"],
                        end_date=state["end_date"]
                    )

                if not isinstance(weather, dict):
                    raise ValueError(
                        "Weather tool returned invalid data"
                    )

                daily = weather.get("daily", {})

                precipitation = daily.get(
                    "precipitation_sum", []
                ) or []

                valid_rain = [
                    float(value)
                    for value in precipitation
                    if value is not None
                ]

                max_rain = max(
                    valid_rain,
                    default=None
                )

                # Demo rule:
                # Heavy rain >= 20 mm/day is unfavorable
                # for beach and adventure holidays.

                category = package.get("category", "")

                if max_rain is None:
                    suitable = None
                    risk = "unknown"

                elif (
                    category in ("Beach", "Adventure")
                    and max_rain >= 20
                ):
                    suitable = False
                    risk = "high"

                else:
                    suitable = True
                    risk = "low"

                result = {
                    **package,
                    "weather_suitable": suitable,
                    "weather_risk": risk,
                    "maximum_daily_rain_mm": max_rain,
                    "weather_data_available": (
                        max_rain is not None
                    )
                }

                print(
                    f"[WEATHER] {package['destination']}: "
                    f"risk={risk}, "
                    f"max_rain={max_rain}"
                )

                return result

            except Exception as error:
                print(
                    f"[WEATHER ERROR] "
                    f"{package['destination']}: {error}"
                )

                return {
                    **package,
                    "weather_suitable": None,
                    "weather_risk": "unknown",
                    "maximum_daily_rain_mm": None,
                    "weather_data_available": False,
                    "weather_error": str(error)
                }

    recommendations = await asyncio.gather(
        *[
            check_destination(package)
            for package in packages
        ]
    )

    return {
        "recommendations": recommendations
    }


# ==========================================
# 5. RANK HOLIDAY RECOMMENDATIONS
# ==========================================

def rank_holidays_node(state: HolidayState) -> dict:
    """
    Rank holidays by weather suitability,
    followed by package price.
    """

    print("\n[RANKING] Ranking holiday packages...")

    recommendations = state.get(
        "recommendations", []
    )

    def ranking_key(holiday: dict):
        suitability = holiday.get(
            "weather_suitable"
        )

        priority = {
            True: 0,
            None: 1,
            False: 2
        }.get(suitability, 1)

        return (
            priority,
            holiday["price_usd"]
        )

    ranked = sorted(
        recommendations,
        key=ranking_key
    )

    for index, holiday in enumerate(
        ranked,
        start=1
    ):
        print(
            f"{index}. {holiday['destination']} | "
            f"${holiday['price_usd']} | "
            f"Weather risk: {holiday['weather_risk']}"
        )

    return {
        "recommendations": ranked
    }


# ==========================================
# 6. BUILD LANGGRAPH WORKFLOW
# ==========================================

builder = StateGraph(HolidayState)

builder.add_node(
    "load_skill",
    load_skill_node
)

builder.add_node(
    "fetch_holidays",
    fetch_holidays_node
)

builder.add_node(
    "evaluate_weather",
    evaluate_weather_node
)

builder.add_node(
    "rank_holidays",
    rank_holidays_node
)


# ==========================================
# 7. DEFINE GRAPH EDGES
# ==========================================

builder.add_edge(
    START,
    "load_skill"
)

builder.add_edge(
    "load_skill",
    "fetch_holidays"
)

builder.add_edge(
    "fetch_holidays",
    "evaluate_weather"
)

builder.add_edge(
    "evaluate_weather",
    "rank_holidays"
)

builder.add_edge(
    "rank_holidays",
    END
)


# ==========================================
# 8. COMPILE GRAPH
# ==========================================

holiday_graph = builder.compile()


# ==========================================
# 9. EXECUTE WORKFLOW
# ==========================================

async def main():

    print("\n====================================")
    print("   LANGGRAPH HOLIDAY PLANNER")
    print("====================================")

    initial_state: HolidayState = {
        "budget": 1000,
        "start_date": "2026-11-05",
        "end_date": "2026-11-10",
        "errors": []
    }

    print("\n[INPUT]")
    print(json.dumps(initial_state, indent=2))

    result = await holiday_graph.ainvoke(
        initial_state
    )

    print("\n====================================")
    print("   FINAL HOLIDAY RECOMMENDATIONS")
    print("====================================")

    print(
        json.dumps(
            result.get("recommendations", []),
            indent=2,
            default=str
        )
    )

    print("\n[SUCCESS] LangGraph workflow completed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOPPED] LangGraph holiday workflow")
