
import uvicorn

from fastmcp import FastMCP
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
