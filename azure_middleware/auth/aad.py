"""AAD (Azure Active Directory) token provider for Azure OpenAI."""

import asyncio
import logging
from typing import Protocol

from azure.identity import DefaultAzureCredential, AzureCliCredential, ClientSecretCredential


logger = logging.getLogger(__name__)

# Azure OpenAI scope for token acquisition
AZURE_OPENAI_SCOPE = "https://cognitiveservices.azure.com/.default"


class TokenProvider(Protocol):
    """Protocol for token providers."""

    async def get_token(self) -> str:
        """Get an access token.

        Returns:
            Access token string
        """
        ...


class AADTokenProvider:
    """Azure AD token provider using DefaultAzureCredential or ClientSecretCredential.

    If tenant_id, client_id, and client_secret are provided, uses ClientSecretCredential
    for service principal authentication.

    Otherwise, uses the Azure Identity library's credential chain:
    1. Environment variables
    2. Managed Identity
    3. Azure CLI
    4. Azure PowerShell
    5. Interactive browser (if available)
    """

    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        """Initialize the AAD token provider.

        Args:
            tenant_id: Azure AD tenant ID (optional)
            client_id: Azure AD client (application) ID (optional)
            client_secret: Azure AD client secret (optional)
        """
        # Use ClientSecretCredential if service principal credentials provided
        if tenant_id and client_id and client_secret:
            logger.info("Using ClientSecretCredential with provided service principal credentials")
            self._credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )
        else:
            # Try DefaultAzureCredential first, fall back to CLI for local dev
            try:
                self._credential = DefaultAzureCredential()
            except Exception:
                logger.info("DefaultAzureCredential failed, trying AzureCliCredential")
                self._credential = AzureCliCredential()

        self._token_cache: str | None = None
        self._token_expires_at: float = 0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        """Get an access token for Azure OpenAI.

        Caches tokens and refreshes when near expiry.

        Returns:
            Access token string

        Raises:
            Exception: If token acquisition fails
        """
        async with self._lock:
            import time

            # Return cached token if still valid (with 5 min buffer)
            if self._token_cache and time.time() < self._token_expires_at - 300:
                return self._token_cache

            # Get new token in thread pool (credential.get_token is sync)
            token = await asyncio.to_thread(
                self._credential.get_token, AZURE_OPENAI_SCOPE
            )

            self._token_cache = token.token
            self._token_expires_at = token.expires_on

            logger.debug(
                f"Acquired new AAD token, expires at {self._token_expires_at}"
            )

            return self._token_cache

    async def get_auth_header(self) -> dict[str, str]:
        """Get authorization header for Azure OpenAI request.

        Returns:
            Dict with Authorization header
        """
        token = await self.get_token()
        return {"Authorization": f"Bearer {token}"}
