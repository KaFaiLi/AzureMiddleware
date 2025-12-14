"""CLI entry point for Azure OpenAI Local Middleware.

Usage:
    python -m azure_middleware [--config CONFIG_PATH] [--host HOST] [--port PORT]
"""

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="azure-middleware",
        description="Local FastAPI proxy for Azure OpenAI with authentication, logging, and cost tracking",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml file (default: ./config.yaml or ~/config.yaml)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Override host from config",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override port from config",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Import here to avoid circular imports and speed up --help
    from azure_middleware.config import load_config, ConfigError
    from azure_middleware.server import create_app

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Apply CLI overrides
    host = args.host or config.local.host
    port = args.port or config.local.port

    # Create app
    app = create_app(config)

    # Run server
    import uvicorn

    print(f"Starting Azure OpenAI Middleware on http://{host}:{port}")
    print(f"  Azure endpoint: {config.azure.endpoint}")
    print(f"  Auth mode: {config.azure.auth_mode.value}")
    print(f"  Daily cost cap: €{config.limits.daily_cost_cap_eur:.2f}")
    print()

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
