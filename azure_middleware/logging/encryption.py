"""AES-256-GCM encryption for log field encryption."""

import base64
import gzip
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# Prefix for encrypted fields in JSONL
ENCRYPTED_PREFIX = "$enc:"

# Flag bits for encrypted blob
FLAG_COMPRESSED = 0x01


class FieldEncryptor:
    """Encrypts and decrypts log fields using AES-256-GCM.

    Encrypted format:
        $enc:BASE64([flags:1][nonce:12][ciphertext:N][tag:16])

    Flags byte:
        bit 0: compressed (1) or not (0)
    """

    def __init__(self, key: bytes) -> None:
        """Initialize encryptor with AES-256 key.

        Args:
            key: 32-byte AES-256 key

        Raises:
            ValueError: If key is not exactly 32 bytes
        """
        if len(key) != 32:
            raise ValueError(f"Key must be exactly 32 bytes, got {len(key)}")
        self._aesgcm = AESGCM(key)

    def encrypt(self, value: str | dict | Any) -> str:
        """Encrypt a value for storage.

        Args:
            value: String, dict, or JSON-serializable value to encrypt

        Returns:
            Encrypted string with $enc: prefix
        """
        # Convert to bytes
        if isinstance(value, dict):
            data = json.dumps(value, separators=(",", ":")).encode("utf-8")
        elif isinstance(value, str):
            data = value.encode("utf-8")
        else:
            data = json.dumps(value, separators=(",", ":")).encode("utf-8")

        # Compress if beneficial (data >= 100 bytes)
        flags = 0x00
        if len(data) >= 100:
            compressed = gzip.compress(data, compresslevel=6)
            if len(compressed) < len(data):
                data = compressed
                flags = FLAG_COMPRESSED

        # Generate random nonce and encrypt
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, data, None)

        # Combine: flags (1) + nonce (12) + ciphertext (includes 16-byte tag)
        blob = bytes([flags]) + nonce + ciphertext
        return ENCRYPTED_PREFIX + base64.b64encode(blob).decode("ascii")

    def decrypt(self, encrypted: str) -> str | dict:
        """Decrypt an encrypted value.

        Args:
            encrypted: Encrypted string with $enc: prefix

        Returns:
            Decrypted value (dict if was JSON, otherwise string)

        Raises:
            ValueError: If format is invalid or decryption fails
        """
        if not encrypted.startswith(ENCRYPTED_PREFIX):
            raise ValueError(f"Invalid encrypted format: missing {ENCRYPTED_PREFIX} prefix")

        try:
            blob = base64.b64decode(encrypted[len(ENCRYPTED_PREFIX) :])
        except Exception as e:
            raise ValueError(f"Invalid base64 in encrypted field: {e}")

        if len(blob) < 13:  # 1 byte flags + 12 byte nonce minimum
            raise ValueError("Encrypted blob too short")

        flags = blob[0]
        nonce = blob[1:13]
        ciphertext = blob[13:]

        try:
            data = self._aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

        # Decompress if compressed
        if flags & FLAG_COMPRESSED:
            try:
                data = gzip.decompress(data)
            except Exception as e:
                raise ValueError(f"Decompression failed: {e}")

        # Try to parse as JSON, return string otherwise
        text = data.decode("utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def is_encrypted(self, value: str) -> bool:
        """Check if a string is an encrypted field.

        Args:
            value: String to check

        Returns:
            True if string starts with encryption prefix
        """
        return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def generate_key() -> str:
    """Generate a new AES-256 key.

    Returns:
        Base64-encoded 32-byte key suitable for config.yaml
    """
    key = AESGCM.generate_key(bit_length=256)
    return base64.b64encode(key).decode("ascii")
