"""API key authentication provider for Azure OpenAI."""

from pydantic import SecretStr


class APIKeyProvider:
    """API key provider for Azure OpenAI.

    Uses a static API key from configuration.
    """

    def __init__(self, api_key: SecretStr) -> None:
        """Initialize with Azure API key.

        Args:
            api_key: Azure OpenAI API key
        """
        self._api_key = api_key

    async def get_auth_header(self) -> dict[str, str]:
        """Get API key header for Azure OpenAI request.

        Returns:
            Dict with api-key header
        """
        return {"api-key": self._api_key.get_secret_value()}
