"""CLI entry point for Azure OpenAI Local Middleware.

Usage:
    python -m azure_middleware [--config CONFIG_PATH] [--local LOCAL_PATH] [--host HOST] [--port PORT]
    
Config files:
    - config.yaml: Server settings (Azure, logging, pricing, limits)
    - local.yaml: Local settings (host, port, api_key)
"""

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="azure-middleware",
        description="Local FastAPI proxy for Azure OpenAI with authentication, logging, and cost tracking.\n\n"
                    "USAGE EXAMPLES:\n"
                    "  python -m azure_middleware --config config.yaml --local local.yaml\n"
                    "  python -m azure_middleware --host 127.0.0.1 --port 8000\n\n"
                    "Config files:\n"
                    "  config.yaml: Server settings (Azure, logging, pricing, limits)\n"
                    "  local.yaml: Local settings (host, port, api_key)",
        epilog="For more information, see the documentation or use --help for all options."
    )
    parser.add_argument(
        "--example",
        action="store_true",
        help="Show example usage and exit."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to server config.yaml file (default: ./config.yaml or ~/config.yaml)",
    )
    parser.add_argument(
        "--local",
        type=Path,
        default=None,
        help="Path to local.yaml file (default: ./local.yaml or ~/local.yaml)",
    )
    parser.add_argument(
        "--single-file",
        action="store_true",
        help="Use single config file mode (legacy, all settings in config.yaml)",
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

    if getattr(args, "example", False):
        print("\nExample usage:\n  python -m azure_middleware --config config.yaml --local local.yaml\n  python -m azure_middleware --host 127.0.0.1 --port 8000\n")
        return 0

    # Import here to avoid circular imports and speed up --help
    from azure_middleware.config import load_config, load_config_single_file, ConfigError
    from azure_middleware.server import create_app

    try:
        if args.single_file:
            config = load_config_single_file(args.config)
        else:
            config = load_config(args.config, args.local)
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
