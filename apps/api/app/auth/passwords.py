from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def hash_password(raw: str) -> str:
    return _ph.hash(raw)


def verify_password(stored: str, raw: str) -> bool:
    try:
        return _ph.verify(stored, raw)
    except VerifyMismatchError:
        return False
