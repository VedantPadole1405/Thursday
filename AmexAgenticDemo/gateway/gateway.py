
import uvicorn

from fastmcp import Client, FastMCP
from fastmcp.apps import AppConfig, ResourcePermissions
from fastmcp.server import create_proxy


# ==========================================
# BACKEND MCP SERVERS
# ==========================================

PAYMENTS_URL = "http://127.0.0.1:8001/mcp"
HOLIDAYS_URL = "http://127.0.0.1:8003/mcp"

PAYMENT_UI_URI = "ui://payments/approval"
# ==========================================
# MULTI-SERVER MCP GATEWAY
# ==========================================

gateway = FastMCP(
    name="Amex Multi-Server MCP Gateway"
)

payments_proxy = create_proxy(
    PAYMENTS_URL,
    name="Payments Proxy"
)

holidays_proxy = create_proxy(
    HOLIDAYS_URL,
    name="Holidays Proxy"
)


# ==========================================
# MOUNT BACKEND SERVERS
# ==========================================

gateway.mount(
    payments_proxy,
    namespace="payments"
)

gateway.mount(
    holidays_proxy,
    namespace="holidays"
)


def register_nearby_ui_alias(server, holidays_backend):
    """Keep the backend's UI URI readable after namespaced mounting.

    FastMCP namespaces resource URIs but preserves the tool's ui.resourceUri.
    The alias also carries permissions on resources/read, where hosts need them.
    """
    @server.resource(
        "ui://holidays/nearby",
        mime_type="text/html;profile=mcp-app",
        app=AppConfig(permissions=ResourcePermissions(geolocation={})),
    )
    async def nearby_holidays_ui() -> str:
        async with Client(holidays_backend) as client:
            contents = await client.read_resource("ui://holidays/nearby")
        return contents[0].text


register_nearby_ui_alias(gateway, HOLIDAYS_URL)


# ==========================================
# MCP HTTP ENDPOINT
# ==========================================

gateway_app = gateway.http_app(path="/mcp")


if __name__ == "__main__":
    uvicorn.run(
        gateway_app,
        host="127.0.0.1",
        port=8000
    )
