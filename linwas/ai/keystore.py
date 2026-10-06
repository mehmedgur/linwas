"""API anahtar kasası.

Önce sistem anahtar kasasını (secretstorage/GNOME Keyring, KWallet) dener.
Kasa yoksa anahtarı yalnızca oturum süresince bellekte tutar ve kullanıcıya
bildirir.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SERVICE = "linwas"

# Oturum belleği: kasa kullanılamadığında geçici depolama
_session_keys: dict[str, str] = {}


def _try_keyring() -> bool:
    """keyring modülü ve kullanılabilir backend var mı?"""
    try:
        import keyring
        import keyring.errors

        # Boş bir okuma yaparak backend'i test et
        keyring.get_password(_SERVICE, "__probe__")
        return True
    except Exception:
        return False


_keyring_available: bool | None = None


def _keyring_ok() -> bool:
    global _keyring_available
    if _keyring_available is None:
        _keyring_available = _try_keyring()
        if not _keyring_available:
            logger.warning(
                "Sistem anahtar kasası kullanılamıyor; "
                "anahtarlar yalnızca bu oturum için saklanacak."
            )
    return _keyring_available


def set_key(provider_id: str, api_key: str) -> bool:
    """API anahtarını kaydeder. Başarılıysa True döner."""
    if _keyring_ok():
        try:
            import keyring

            keyring.set_password(_SERVICE, provider_id, api_key)
            _session_keys.pop(provider_id, None)
            return True
        except Exception as exc:
            logger.warning("Anahtar kasasına yazılamadı: %s", exc)

    # Kasa yoksa oturum belleğine yaz
    _session_keys[provider_id] = api_key
    return False


def get_key(provider_id: str) -> str | None:
    """API anahtarını okur; bulunamazsa None döner."""
    if _keyring_ok():
        try:
            import keyring

            value = keyring.get_password(_SERVICE, provider_id)
            if value:
                return value
        except Exception as exc:
            logger.warning("Anahtar kasasından okunamadı: %s", exc)

    return _session_keys.get(provider_id)


def delete_key(provider_id: str) -> None:
    """API anahtarını siler."""
    _session_keys.pop(provider_id, None)
    if _keyring_ok():
        try:
            import keyring
            import keyring.errors

            keyring.delete_password(_SERVICE, provider_id)
        except Exception:
            pass


def keyring_available() -> bool:
    """Sistem anahtar kasasının kullanılabilir olup olmadığını döner."""
    return _keyring_ok()
