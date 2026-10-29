"""Client for the holidays MCP server."""

import asyncio
import json
import time

from fastmcp import Client


GATEWAY_URL = "http://127.0.0.1:8000/mcp"

TOOL_CACHE_TTL_MS = 60_000
TOOL_CACHE = {}


# ==========================================
# TOOL CACHE
# ==========================================

async def get_cached_tools(client, server_url):
    now_ms = time.monotonic() * 1000
    cached = TOOL_CACHE.get(server_url)

    if cached:
        remaining = cached["expires_at_ms"] - now_ms

        if remaining > 0:
            print(f"[CACHE HIT] TTL: {remaining:.0f} ms")
            return cached["tools"]

    print("[CACHE MISS] Calling tools/list")

    tools = await client.list_tools()

    TOOL_CACHE[server_url] = {
        "tools": tools,
        "expires_at_ms": (
            time.monotonic() * 1000 + TOOL_CACHE_TTL_MS
        )
    }

    print(f"[CACHE UPDATED] {len(tools)} tools")
    return tools


# ==========================================
# HOLIDAYS MCP CLIENT
# ==========================================

class HolidaysMCPClient:

    def __init__(self, server_url=GATEWAY_URL):
        self.server_url = server_url
        self.client = Client(server_url)
        self.tool_names = {}

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.__aexit__(exc_type, exc, tb)

    async def discover_tools(self):
        tools = await get_cached_tools(
            self.client,
            self.server_url
        )

        print("\n========== HOLIDAYS TOOLS ==========")

        for tool in tools:
            if "holiday" in tool.name.lower():
                print("-", tool.name)

        # Resolve gateway tool names from actual discovery.
        for operation in [
            "list_holidays",
            "search_holidays",
            "get_holiday_details",
            "recommend_holiday",
            "get_destination_weather"
        ]:
            matches = [
                tool.name for tool in tools
                if tool.name == operation
                or tool.name.endswith("_" + operation)
            ]

            if len(matches) != 1:
                raise RuntimeError(
                    f"Expected one tool for {operation}, "
                    f"found: {matches}"
                )

            self.tool_names[operation] = matches[0]

    async def discover_resources(self):
        resources = await self.client.list_resources()
        templates = await self.client.list_resource_templates()

        print("\n========== HOLIDAYS RESOURCES ==========")

        for resource in resources:
            if "holiday" in str(resource.uri).lower():
                print("-", resource.uri)

        print("\n========== RESOURCE TEMPLATES ==========")

        for template in templates:
            if "holiday" in str(template.uri_template).lower():
                print("-", template.uri_template)

    async def execute_tool(self, operation, arguments=None):
        tool_name = self.tool_names.get(operation)

        if not tool_name:
            raise RuntimeError(
                f"Tool {operation} has not been discovered"
            )

        result = await self.client.call_tool(
            tool_name,
            arguments or {}
        )

        if result.is_error:
            raise RuntimeError(str(result.content))

        if result.data is not None:
            return result.data

        texts = [
            item.text
            for item in result.content
            if hasattr(item, "text")
        ]

        if len(texts) == 1:
            try:
                return json.loads(texts[0])
            except json.JSONDecodeError:
                return texts[0]

        return texts

    async def list_holidays(self):
        return await self.execute_tool(
            "list_holidays"
        )

    async def search_holidays(
        self,
        max_budget=None,
        max_days=None,
        category=None
    ):
        arguments = {}

        if max_budget is not None:
            arguments["max_budget"] = max_budget

        if max_days is not None:
            arguments["max_days"] = max_days

        if category is not None:
            arguments["category"] = category

        return await self.execute_tool(
            "search_holidays",
            arguments
        )

    async def recommend_holiday(self, budget):
        return await self.execute_tool(
            "recommend_holiday",
            {"budget": budget}
        )
    async def get_destination_weather(
        self, latitude, longitude, start_date, end_date
    ):
        return await self.execute_tool(
            "get_destination_weather",
            {
                "latitude": latitude,
                "longitude": longitude,
                "start_date": start_date,
                "end_date": end_date
            }
        )


# ==========================================
# PERSISTENT CLIENT
# ==========================================

async def main():

    print("[STARTING] Holidays MCP Client")
    print("[GATEWAY]", GATEWAY_URL)

    while True:
        try:
            async with HolidaysMCPClient() as holidays:

                print("[CONNECTED] MCP Gateway")

                await holidays.discover_tools()
                await holidays.discover_resources()

                print("\n========== HOLIDAY CATALOG ==========")

                catalog = await holidays.list_holidays()
                print(json.dumps(catalog, indent=2, default=str))

                print("\n========== HOLIDAYS UNDER $1000 ==========")

                recommendations = await holidays.recommend_holiday(
                    budget=1000
                )

                print(json.dumps(
                    recommendations,
                    indent=2,
                    default=str
                ))

                print("\n[READY] Holidays Client running")
                print("[INFO] Cache TTL: 60000 ms")
                print("[INFO] Ctrl+C to stop")

                while True:
                    await asyncio.sleep(5)

                    await holidays.discover_tools()

        except asyncio.CancelledError:
            raise

        except Exception as error:
            print("[ERROR]", error)
            print("[RECONNECT] Retrying in 3 seconds")
            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOPPED] Holidays MCP Client")
