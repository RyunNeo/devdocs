import hashlib
import secrets

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()
# Check unknown accounts against a real hash to avoid an immediate timing difference.
dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    return password_hasher.verify(password, stored_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
