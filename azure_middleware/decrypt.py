"""CLI utility for decrypting log files."""

import argparse
import json
import sys
from pathlib import Path

from azure_middleware.logging.encryption import FieldEncryptor, ENCRYPTED_PREFIX


def decrypt_log_file(
    input_path: Path,
    output_path: Path | None,
    key: bytes,
    fields: list[str] | None = None,
) -> int:
    """Decrypt a JSONL log file.

    Args:
        input_path: Path to encrypted log file
        output_path: Path for decrypted output (None for stdout)
        key: AES-256 key bytes
        fields: Specific fields to decrypt (None for all)

    Returns:
        Exit code (0 for success)
    """
    encryptor = FieldEncryptor(key)

    # Default fields to decrypt
    if fields is None:
        fields = ["request_encrypted", "response_encrypted"]

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return 1

    decrypted_lines = []
    error_count = 0

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"Warning: Line {line_num}: Invalid JSON: {e}", file=sys.stderr)
            error_count += 1
            decrypted_lines.append(line)
            continue

        # Decrypt specified fields
        for field in fields:
            if field in entry and entry[field]:
                value = entry[field]
                if isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX):
                    try:
                        decrypted = encryptor.decrypt(value)
                        # Replace encrypted field with decrypted
                        new_field = field.replace("_encrypted", "")
                        entry[new_field] = decrypted
                        del entry[field]
                    except Exception as e:
                        print(f"Warning: Line {line_num}: Failed to decrypt {field}: {e}", file=sys.stderr)
                        error_count += 1

        decrypted_lines.append(json.dumps(entry, ensure_ascii=False))

    # Output
    output_content = "\n".join(decrypted_lines)
    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(output_content)
                f.write("\n")
            print(f"Decrypted {len(decrypted_lines)} entries to {output_path}", file=sys.stderr)
        except Exception as e:
            print(f"Error writing output: {e}", file=sys.stderr)
            return 1
    else:
        print(output_content)

    if error_count > 0:
        print(f"Completed with {error_count} warnings", file=sys.stderr)

    return 0


def main() -> int:
    """Main entry point for decrypt CLI."""
    parser = argparse.ArgumentParser(
        prog="azure-middleware-decrypt",
        description="Decrypt Azure Middleware log files",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to encrypted JSONL log file",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "-k", "--key",
        type=str,
        required=True,
        help="Base64-encoded AES-256 encryption key",
    )
    parser.add_argument(
        "-f", "--fields",
        type=str,
        nargs="+",
        default=None,
        help="Fields to decrypt (default: request_encrypted, response_encrypted)",
    )

    args = parser.parse_args()

    # Decode key
    import base64
    try:
        key_bytes = base64.b64decode(args.key)
        if len(key_bytes) != 32:
            print(f"Error: Key must be 32 bytes, got {len(key_bytes)}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error: Invalid base64 key: {e}", file=sys.stderr)
        return 1

    return decrypt_log_file(args.input, args.output, key_bytes, args.fields)


if __name__ == "__main__":
    sys.exit(main())
