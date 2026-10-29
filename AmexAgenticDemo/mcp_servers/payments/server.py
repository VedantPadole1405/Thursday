"""Local-only simulated Payments REST + MCP server with MCP Apps UI."""
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastmcp import FastMCP
from pydantic import BaseModel, Field

api = FastAPI(title="Payments REST API", version="1.1.0")
mcp = FastMCP(name="Payments MCP Server")

PAYMENT_STORE: dict[str, dict] = {}
IDEMPOTENCY_STORE: dict[str, str] = {}
STORE_LOCK = Lock()
SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP"]
UI_URI = "ui://payments/approval"
UI_FILE = Path(__file__).resolve().parent / "ui" / "dist" / "approval.html"


class PaymentRequest(BaseModel):
    account_id: str = Field(min_length=1)
    recipient_id: str = Field(min_length=1)
    amount: Decimal = Field(gt=0, le=10000, max_digits=12, decimal_places=2)
    currency: Literal["USD", "EUR", "GBP"] = "USD"
    idempotency_key: str = Field(min_length=1)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_payment(request: PaymentRequest) -> dict:
    data = request.model_dump(mode="json")
    with STORE_LOCK:
        existing_id = IDEMPOTENCY_STORE.get(request.idempotency_key)
        if existing_id:
            existing = PAYMENT_STORE[existing_id]
            if existing["original_request"] != data:
                raise ValueError("Idempotency key reused with different request data")
            return existing.copy()

        payment_id = str(uuid.uuid4())
        payment = {
            "payment_id": payment_id,
            "status": "pending_approval",
            "created_at": timestamp(),
            "account_id": request.account_id,
            "recipient_id": request.recipient_id,
            "amount": str(request.amount),
            "currency": request.currency,
            "created_by": "demo",
            "original_request": data,
        }
        PAYMENT_STORE[payment_id] = payment
        IDEMPOTENCY_STORE[request.idempotency_key] = payment_id
        return payment.copy()


def find_payment(payment_id: str) -> dict:
    with STORE_LOCK:
        payment = PAYMENT_STORE.get(payment_id)
        if payment is None:
            raise ValueError("Payment not found")
        return payment.copy()


def find_account_payments(account_id: str) -> list[dict]:
    with STORE_LOCK:
        return [p.copy() for p in PAYMENT_STORE.values() if p["account_id"] == account_id]


def change_payment_status(payment_id: str, action: Literal["approve", "reject", "cancel"]) -> dict:
    """DEMO ONLY: records a decision, never transfers funds."""
    statuses = {"approve": "approved_demo", "reject": "rejected", "cancel": "cancelled"}
    with STORE_LOCK:
        payment = PAYMENT_STORE.get(payment_id)
        if payment is None:
            raise ValueError("Payment not found")
        if payment["status"] != "pending_approval":
            raise ValueError(f"Payment cannot be changed from status {payment['status']}")
        payment["status"] = statuses[action]
        payment["updated_at"] = timestamp()
        return payment.copy()


# MCP tools
@mcp.tool()
def make_payment(
    account_id: str,
    recipient_id: str,
    amount: Decimal,
    currency: Literal["USD", "EUR", "GBP"],
    idempotency_key: str,
) -> dict:
    """Create a simulated payment pending approval. No money is transferred."""
    return create_payment(PaymentRequest(
        account_id=account_id,
        recipient_id=recipient_id,
        amount=amount,
        currency=currency,
        idempotency_key=idempotency_key,
    ))


@mcp.tool()
def get_payment_status(payment_id: str) -> dict:
    """Get a simulated payment's status."""
    return find_payment(payment_id)


@mcp.tool()
def list_payments(account_id: str) -> list[dict]:
    """List simulated payments for an account."""
    return find_account_payments(account_id)


@mcp.tool()
def cancel_payment(payment_id: str) -> dict:
    """Cancel a pending simulated payment."""
    return change_payment_status(payment_id, "cancel")


@mcp.tool()
def approve_payment_demo(payment_id: str) -> dict:
    """DEMO ONLY: mark a pending payment approved without moving funds. No authentication."""
    return change_payment_status(payment_id, "approve")


@mcp.tool()
def reject_payment_demo(payment_id: str) -> dict:
    """DEMO ONLY: reject a pending simulated payment. No authentication."""
    return change_payment_status(payment_id, "reject")



UI_URI = "ui://payments/approval"

@mcp.tool(
    meta={
        "ui": {
            "resourceUri": UI_URI
        }
    }
)
def show_payment_approval(payment_id: str) -> dict:
    """Display the payment approval MCP App."""
    return find_payment(payment_id)



# MCP resources
@mcp.resource("payments://policies")
def payment_policies() -> str:
    return json.dumps({
        "simulation": True,
        "approval_required": True,
        "maximum_payment": "10000.00",
        "supported_currencies": SUPPORTED_CURRENCIES,
        "note": "Approval is simulated; production requires identity and account authorization.",
    })


@mcp.resource("payments://currencies")
def payment_currencies() -> str:
    return json.dumps({"supported_currencies": SUPPORTED_CURRENCIES})


@mcp.resource("payments://service-info")
def payment_service_info() -> str:
    return json.dumps({"name": "Payments MCP Server", "version": "1.1.0", "mode": "local simulation"})


@mcp.resource("payments://transactions/{payment_id}")
def payment_transaction(payment_id: str) -> str:
    return json.dumps(find_payment(payment_id))


@mcp.resource(UI_URI, mime_type="text/html;profile=mcp-app")
def payment_approval_ui() -> str:
    """Return bundled HTML; host renders it in a sandboxed iframe."""
    if not UI_FILE.is_file():
        raise FileNotFoundError(f"Missing {UI_FILE}. Run npx vite build in payments/ui")
    return UI_FILE.read_text(encoding="utf-8")


# REST endpoints for local development
@api.post("/payments")
def create_payment_endpoint(request: PaymentRequest):
    try:
        return create_payment(request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@api.get("/payments/{payment_id}")
def get_payment_endpoint(payment_id: str):
    try:
        return find_payment(payment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api.get("/accounts/{account_id}/payments")
def list_payments_endpoint(account_id: str):
    return find_account_payments(account_id)


@api.post("/payments/{payment_id}/cancel")
def cancel_payment_endpoint(payment_id: str):
    try:
        return change_payment_status(payment_id, "cancel")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


mcp_app = mcp.http_app(path="/mcp")
app = FastAPI(
    title="Payments API + MCP Server",
    version="1.1.0",
    routes=[*mcp_app.routes, *api.routes],
    lifespan=mcp_app.lifespan,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
