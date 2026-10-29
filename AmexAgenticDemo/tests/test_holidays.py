
import asyncio
import json
from fastmcp import Client


async def main():
    async with Client("http://127.0.0.1:8003/mcp") as client:

        print("[CONNECTED] Holidays MCP Server")

        tools = await client.list_tools()

        print("\n========== TOOLS ==========")
        for tool in tools:
            print("-", tool.name)

        resources = await client.list_resources()

        print("\n========== RESOURCES ==========")
        for resource in resources:
            print("-", resource.uri)

        result = await client.call_tool(
            "list_holidays",
            {}
        )

        if result.is_error:
            raise RuntimeError(str(result.content))

        print("\n========== HOLIDAY LIST ==========")
        print(json.dumps(
            result.data
            if result.data is not None
            else [
                item.model_dump(mode="json")
                for item in result.content
            ],
            indent=2
        ))


if __name__ == "__main__":
    asyncio.run(main())
