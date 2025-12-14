"""Configuration loading and validation for Azure OpenAI Middleware."""

import base64
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator


class ConfigError(Exception):
    """Configuration loading or validation error."""

    pass


class AuthMode(str, Enum):
    """Authentication mode for Azure OpenAI."""

    AAD = "aad"
    API_KEY = "api_key"


class AzureConfig(BaseModel):
    """Azure OpenAI connection settings."""

    endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    deployment: str = Field(..., description="Default deployment name")
    api_version: str = Field(default="2024-02-01", description="API version")
    auth_mode: AuthMode = Field(default=AuthMode.AAD, description="Authentication mode")
    api_key: SecretStr | None = Field(
        default=None, description="API key (if auth_mode=api_key)"
    )

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """Validate that endpoint is a valid Azure URL."""
        if not v.startswith("https://"):
            raise ValueError("Azure endpoint must start with https://")
        if not v.rstrip("/").endswith(".openai.azure.com"):
            raise ValueError("Azure endpoint must end with .openai.azure.com")
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_api_key_required(self) -> "AzureConfig":
        """Validate that API key is provided when auth_mode is api_key."""
        if self.auth_mode == AuthMode.API_KEY and not self.api_key:
            raise ValueError("api_key is required when auth_mode is 'api_key'")
        return self


class LocalConfig(BaseModel):
    """Local server settings."""

    host: str = Field(default="127.0.0.1", description="Bind address")
    port: int = Field(default=8000, ge=1, le=65535, description="Port number")
    api_key: SecretStr = Field(..., description="Local API key for request validation")

    @field_validator("api_key")
    @classmethod
    def validate_api_key_length(cls, v: SecretStr) -> SecretStr:
        """Validate that API key has minimum length."""
        if len(v.get_secret_value()) < 8:
            raise ValueError("Local API key must be at least 8 characters")
        return v


class PricingTier(BaseModel):
    """Per-model pricing in EUR per 1000 tokens."""

    input: float = Field(..., ge=0, description="Input token price")
    output: float = Field(default=0.0, ge=0, description="Output token price")


class LimitsConfig(BaseModel):
    """Cost and rate limits."""

    daily_cost_cap_eur: float = Field(
        default=5.0, ge=0, description="Daily spending cap in EUR"
    )


class LoggingConfig(BaseModel):
    """Logging and encryption settings."""

    encryption_key: SecretStr = Field(..., description="Base64-encoded AES-256 key")
    compression: Literal["gzip", "none"] = Field(
        default="gzip", description="Compression algorithm"
    )
    directory: str = Field(default="logs", description="Log directory path")

    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: SecretStr) -> SecretStr:
        """Validate that encryption key decodes to exactly 32 bytes."""
        try:
            key_bytes = base64.b64decode(v.get_secret_value())
        except Exception as e:
            raise ValueError(f"encryption_key must be valid base64: {e}")
        if len(key_bytes) != 32:
            raise ValueError(
                f"encryption_key must decode to exactly 32 bytes (got {len(key_bytes)})"
            )
        return v

    def get_key_bytes(self) -> bytes:
        """Get the raw encryption key bytes."""
        return base64.b64decode(self.encryption_key.get_secret_value())


class AppConfig(BaseModel):
    """Root configuration schema."""

    azure: AzureConfig
    local: LocalConfig
    pricing: dict[str, PricingTier] = Field(default_factory=dict)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    logging: LoggingConfig


def find_config_file(config_path: Path | None = None) -> Path:
    """Find the configuration file.

    Search order:
    1. Explicit path if provided
    2. ./config.yaml (current directory)
    3. ~/config.yaml (home directory)

    Args:
        config_path: Optional explicit path to config file

    Returns:
        Path to the config file

    Raises:
        ConfigError: If no config file is found
    """
    if config_path:
        if config_path.exists():
            return config_path
        raise ConfigError(f"Config file not found: {config_path}")

    # Try current directory
    cwd_config = Path("config.yaml")
    if cwd_config.exists():
        return cwd_config

    # Try home directory
    home_config = Path.home() / "config.yaml"
    if home_config.exists():
        return home_config

    raise ConfigError(
        "Config file not found. Create config.yaml in current directory or home directory, "
        "or specify path with --config"
    )


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load and validate configuration from YAML file.

    Args:
        config_path: Optional explicit path to config file

    Returns:
        Validated AppConfig instance

    Raises:
        ConfigError: If config file is not found or invalid
    """
    try:
        path = find_config_file(config_path)
    except ConfigError:
        raise

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}")
    except OSError as e:
        raise ConfigError(f"Cannot read {path}: {e}")

    if not isinstance(raw_config, dict):
        raise ConfigError(f"Config file {path} must contain a YAML mapping")

    try:
        return AppConfig.model_validate(raw_config)
    except Exception as e:
        raise ConfigError(f"Invalid configuration: {e}")


def get_pricing(config: AppConfig, deployment: str) -> PricingTier:
    """Get pricing for a deployment, with fallback to default.

    Args:
        config: Application configuration
        deployment: Deployment name

    Returns:
        PricingTier for the deployment
    """
    if deployment in config.pricing:
        return config.pricing[deployment]

    # Log warning and return zero pricing as fallback
    # This allows requests to proceed even if pricing is not configured
    import logging

    logging.warning(
        f"No pricing configured for deployment '{deployment}', using zero cost"
    )
    return PricingTier(input=0.0, output=0.0)
