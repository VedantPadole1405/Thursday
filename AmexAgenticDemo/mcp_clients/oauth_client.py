"""Client for the accounts MCP server."""
import asyncio
import os

import httpx2
from dotenv import load_dotenv

from mcp import Client
from mcp.client.auth.extensions.client_credentials import (
    ClientCredentialsOAuthProvider,
)
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


load_dotenv()

SERVER_URL = os.getenv("MCP_SERVER_URL", "https://mcp.example.com/mcp")
SCOPES = os.getenv("MCP_SCOPES", "read write")


class InMemoryTokenStorage:
    def __init__(self) -> None:
        self.tokens: OAuthToken | None = None
        self.client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info


def create_oauth_provider() -> ClientCredentialsOAuthProvider:
    client_id = os.getenv("MCP_CLIENT_ID")
    client_secret = os.getenv("MCP_CLIENT_SECRET")
    issuer = os.getenv("MCP_OAUTH_ISSUER")

    missing = [
        name
        for name, value in (
            ("MCP_CLIENT_ID", client_id),
            ("MCP_CLIENT_SECRET", client_secret),
            ("MCP_OAUTH_ISSUER", issuer),
        )
        if not value or not value.strip()
    ]
    if missing:
        raise RuntimeError(
            "Missing OAuth client credentials. Set "
            + " and ".join(missing)
            + " before connecting to the MCP server."
        )

    return ClientCredentialsOAuthProvider(
        server_url=SERVER_URL,
        storage=InMemoryTokenStorage(),
        client_id=client_id,
        client_secret=client_secret,
        scope=SCOPES,
        issuer=issuer,
    )


async def main() -> None:
    provider = create_oauth_provider()

    async with httpx2.AsyncClient(auth=provider) as http_client:
        transport = streamable_http_client(
            SERVER_URL,
            http_client=http_client,
        )
        async with Client(transport) as client:
            # Use the client
            tools = await client.list_tools()
            print("Available tools:", [t.name for t in tools.tools])


if __name__ == "__main__":
    asyncio.run(main())