"""Gateway authentication."""

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx2
from dotenv import load_dotenv


load_dotenv()


# ==========================================
# 1. OAUTH CONFIGURATION
# ==========================================

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "")
CLIENT_ID = os.getenv("AUTH0_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("AUTH0_CLIENT_SECRET", "")
AUDIENCE = os.getenv("AUTH0_AUDIENCE", "")
SCOPES = os.getenv("AUTH0_SCOPES", "holidays:read")

TOKEN_REFRESH_BUFFER = 60  # seconds


# ==========================================
# 2. TOKEN MODEL
# ==========================================

@dataclass
class CachedToken:
    access_token: str
    token_type: str
    expires_at: float
    scope: str

    def is_valid(self) -> bool:
        return (
            time.monotonic()
            < self.expires_at - TOKEN_REFRESH_BUFFER
        )


# ==========================================
# 3. OAUTH CLIENT
# ==========================================

class OAuthClient:

    def __init__(
        self,
        domain: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        audience: Optional[str] = None,
        scopes: Optional[str] = None
    ):
        self.domain = (
            domain or AUTH0_DOMAIN
        ).strip().rstrip("/")

        self.client_id = client_id or CLIENT_ID
        self.client_secret = client_secret or CLIENT_SECRET
        self.audience = audience or AUDIENCE
        self.scopes = scopes or SCOPES

        self._cached_token: Optional[CachedToken] = None
        self._lock = asyncio.Lock()

        if not all([
            self.domain,
            self.client_id,
            self.client_secret,
            self.audience
        ]):
            raise ValueError(
                "Missing OAuth configuration. "
                "Check AUTH0_DOMAIN, AUTH0_CLIENT_ID, "
                "AUTH0_CLIENT_SECRET and AUTH0_AUDIENCE."
            )

        if not self.domain.startswith("https://"):
            self.domain = "https://" + self.domain

        self.token_url = f"{self.domain}/oauth/token"

    # ======================================
    # REQUEST ACCESS TOKEN
    # ======================================

    async def _request_token(self) -> CachedToken:
        print("[OAUTH] Requesting access token")

        payload = {
            "grant_type": "client_credentials",
            "audience": self.audience,
            "scope": self.scopes
        }

        # OAuth client authentication using HTTP Basic.
        # Credentials are not included in the URL.
        async with httpx2.AsyncClient(
            timeout=15.0
        ) as http:

            response = await http.post(
                self.token_url,
                data=payload,
                auth=(
                    self.client_id,
                    self.client_secret
                )
            )

            response.raise_for_status()
            data = response.json()

        token = data.get("access_token")
        token_type = data.get("token_type", "Bearer")
        expires_in = int(data.get("expires_in", 0))

        if not token:
            raise RuntimeError(
                "Authorization server returned no access token"
            )

        if token_type.lower() != "bearer":
            raise RuntimeError(
                f"Unsupported token type: {token_type}"
            )

        if expires_in <= TOKEN_REFRESH_BUFFER:
            raise RuntimeError(
                "Access token lifetime is too short"
            )

        cached = CachedToken(
            access_token=token,
            token_type=token_type,
            expires_at=time.monotonic() + expires_in,
            scope=data.get("scope", self.scopes)
        )

        print(
            f"[OAUTH] Token obtained; "
            f"expires in {expires_in} seconds"
        )

        return cached

    # ======================================
    # GET CACHED OR NEW TOKEN
    # ======================================

    async def get_access_token(self) -> str:
        if (
            self._cached_token
            and self._cached_token.is_valid()
        ):
            print("[OAUTH CACHE HIT]")
            return self._cached_token.access_token

        async with self._lock:
            # Recheck after acquiring the lock.
            if (
                self._cached_token
                and self._cached_token.is_valid()
            ):
                print("[OAUTH CACHE HIT]")
                return self._cached_token.access_token

            print("[OAUTH CACHE MISS]")

            self._cached_token = await self._request_token()

            return self._cached_token.access_token

    # ======================================
    # AUTHORIZATION HEADER
    # ======================================

    async def get_auth_headers(self) -> dict:
        token = await self.get_access_token()

        return {
            "Authorization": f"Bearer {token}"
        }

    # ======================================
    # INVALIDATE TOKEN
    # ======================================

    def invalidate_token(self):
        self._cached_token = None
        print("[OAUTH] Cached token invalidated")


# ==========================================
# 4. TEST OAUTH CLIENT
# ==========================================

async def main():
    oauth = OAuthClient()

    print("\n========== FIRST TOKEN REQUEST ==========")

    token1 = await oauth.get_access_token()
    print("Token obtained:", bool(token1))

    print("\n========== SECOND TOKEN REQUEST ==========")

    token2 = await oauth.get_access_token()

    print("Same cached token:", token1 == token2)

    print("\n========== AUTH HEADERS ==========")

    headers = await oauth.get_auth_headers()

    # Never print the actual token.
    print("Authorization header configured:",
          "Authorization" in headers)


if __name__ == "__main__":
    asyncio.run(main())
