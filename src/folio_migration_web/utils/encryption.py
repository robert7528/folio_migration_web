"""Credential encryption utilities."""

import os
from pathlib import Path
from cryptography.fernet import Fernet

from ..config import get_settings


class CredentialManager:
    """Manager for encrypting and decrypting credentials."""

    def __init__(self, key: str | None = None):
        """Initialize with encryption key."""
        settings = get_settings()

        if key:
            self._key = key.encode() if isinstance(key, str) else key
        elif settings.encryption_key:
            self._key = settings.encryption_key.encode()
        else:
            self._key = self._get_or_create_key()

        self._fernet = Fernet(self._key)

    def _get_or_create_key(self) -> bytes:
        """Get or create encryption key from file."""
        key_path = Path.home() / ".folio_migration" / "encryption.key"

        if key_path.exists():
            return key_path.read_bytes()

        # Generate new key
        key = Fernet.generate_key()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(key)

        # Set restrictive permissions (Unix only)
        try:
            os.chmod(key_path, 0o600)
        except (OSError, AttributeError):
            pass  # Windows doesn't support chmod

        return key

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string."""
        return self._fernet.decrypt(ciphertext.encode()).decode()


# Singleton instance
_manager: CredentialManager | None = None


def get_credential_manager() -> CredentialManager:
    """Get the credential manager singleton."""
    global _manager
    if _manager is None:
        _manager = CredentialManager()
    return _manager


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string."""
    return get_credential_manager().encrypt(plaintext)


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a ciphertext string."""
    return get_credential_manager().decrypt(ciphertext)
