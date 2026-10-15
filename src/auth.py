import hashlib
import hmac
import os
import secrets
import sys
import time

ITERATIONS = 310_000
SESSION_SECONDS = 12 * 60 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


def check_credentials(username: str, password: str) -> bool:
    expected_user = os.getenv("APP_USERNAME", "")
    stored = os.getenv("APP_PASSWORD_HASH", "")
    if not expected_user or not stored:
        return False
    user_ok = hmac.compare_digest(username.encode(), expected_user.encode())
    return user_ok and verify_password(password, stored)


def _sign(payload: str) -> str:
    return hmac.new(os.environ["SESSION_SECRET"].encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(username: str) -> str:
    payload = f"{username}|{int(time.time()) + SESSION_SECONDS}"
    return f"{payload}|{_sign(payload)}"


def verify_token(token: str | None) -> str | None:
    if not token or not os.getenv("SESSION_SECRET"):
        return None
    try:
        username, expires, signature = token.split("|")
    except ValueError:
        return None
    payload = f"{username}|{expires}"
    if not hmac.compare_digest(_sign(payload), signature) or int(expires) < time.time():
        return None
    return username


if __name__ == "__main__":
    print(hash_password(sys.argv[1]))
