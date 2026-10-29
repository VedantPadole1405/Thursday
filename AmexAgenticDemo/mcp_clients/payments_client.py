
import asyncio
import json
import time
import uuid

from fastmcp import Client


PAYMENTS_MCP_URL = "http://127.0.0.1:8000/mcp"

# Tool metadata cache
TOOL_CACHE = {}
TOOL_CACHE_TTL_MS = 60_000


async def get_cached_tools(client, server_name: str):
    now_ms = time.monotonic() * 1000
    cached = TOOL_CACHE.get(server_name)

    if cached:
        remaining_ms = cached["expires_at_ms"] - now_ms

        if remaining_ms > 0:
            print(
                f"[CACHE HIT] "
                f"TTL remaining: {remaining_ms:.0f} ms"
            )
            return cached["tools"]

    print("[CACHE MISS] Fetching tools/list from server")

    tools = await client.list_tools()

    TOOL_CACHE[server_name] = {
        "tools": tools,
        "expires_at_ms": (
            time.monotonic() * 1000 + TOOL_CACHE_TTL_MS
        )
    }

    print(f"[CACHE UPDATED] {len(tools)} tools")
    return tools


class PaymentsMCPClient:

    def __init__(self, server_url=PAYMENTS_MCP_URL):
        self.server_url = server_url
        self.client = Client(server_url)

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.client.__aexit__(
            exc_type, exc_value, traceback
        )

    async def discover_tools(self):
        """Discover and cache available MCP tools."""

        tools = await get_cached_tools(
            self.client,
            server_name=self.server_url
        )

        print("\n========== AVAILABLE TOOLS ==========")

        for tool in tools:
            print(f"Name: {tool.name}")
            print(f"Description: {tool.description}")
            print(json.dumps(tool.input_schema, indent=2))

        return tools

    async def discover_resources(self):
        """List MCP resources and resource templates."""

        resources = await self.client.list_resources()
        templates = await self.client.list_resource_templates()

        print("\n========== RESOURCES ==========")

        for resource in resources:
            print(resource.uri)

        print("\n========== RESOURCE TEMPLATES ==========")

        for template in templates:
            print(template.uri_template)

        return resources, templates

    async def read_resource(self, uri: str):
        """Read an MCP resource."""

        result = await self.client.read_resource(uri)

        for content in result:
            if hasattr(content, "text"):
                print(content.text)
            else:
                print(content)

        return result

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict
    ):
        """Execute a tool exposed by the MCP server."""

        result = await self.client.call_tool(
            tool_name,
            arguments
        )

        if result.is_error:
            raise RuntimeError(
                f"Tool '{tool_name}' failed: {result.content}"
            )

        return (
            result.data
            if result.data is not None
            else result.content
        )

    async def make_payment(
        self,
        account_id: str,
        recipient_id: str,
        amount: str,
        currency: str = "USD",
        idempotency_key: str | None = None
    ):
        """Create a simulated payment pending approval."""

        return await self.execute_tool(
            "make_payment",
            {
                "account_id": account_id,
                "recipient_id": recipient_id,
                "amount": amount,
                "currency": currency,
                "idempotency_key": (
                    idempotency_key or str(uuid.uuid4())
                )
            }
        )

    async def get_payment_status(self, payment_id: str):
        return await self.execute_tool(
            "get_payment_status",
            {"payment_id": payment_id}
        )

    async def list_payments(self, account_id: str):
        return await self.execute_tool(
            "list_payments",
            {"account_id": account_id}
        )




async def main():
    print("[STARTING] Persistent Payments MCP Client")
    print(f"[GATEWAY] {PAYMENTS_MCP_URL}")

    while True:
        try:
            print("\n[CONNECTING] Connecting to MCP Gateway...")

            async with PaymentsMCPClient() as payments:

                print("[CONNECTED] MCP Gateway session initialized")

                # Initial discovery
                tools = await payments.discover_tools()

                print(
                    "[INITIAL TOOLS]",
                    [tool.name for tool in tools]
                )

                # Discover resources
                await payments.discover_resources()

                print("\n[READY] Payments MCP Client is running")
                print("[INFO] Tool cache TTL: 60000 ms")
                print("[INFO] Press Ctrl+C to stop\n")

                while True:
                    await asyncio.sleep(5)

                    # Cache HIT until TTL expires.
                    # Cache MISS triggers a fresh tools/list request.
                    tools = await get_cached_tools(
                        payments.client,
                        payments.server_url
                    )

                    print(
                        "[AVAILABLE TOOLS]",
                        [tool.name for tool in tools]
                    )

        except asyncio.CancelledError:
            raise

        except Exception as error:
            print(f"\n[CONNECTION ERROR] {error}")
            print("[RECONNECT] Retrying in 3 seconds...")
            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOPPED] Payments MCP Client shut down")
