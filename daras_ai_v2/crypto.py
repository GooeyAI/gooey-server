"""
Stolen code from https://docs.djangoproject.com/en/3.2/_modules/django/contrib/auth/hashers/
"""

import base64
import hashlib
import secrets
import string

RANDOM_STRING_CHARS = string.ascii_letters + string.digits


class PBKDF2PasswordHasher:
    """
    Secure password hashing using the PBKDF2 algorithm (recommended)

    Configured to use PBKDF2 + HMAC + SHA256.
    The result is a 64 byte binary string.  Iterations may be changed
    safely but you must rename the algorithm if you change SHA256.
    """

    algorithm = "pbkdf2_sha256"
    iterations = 260000
    digest = hashlib.sha256
    salt_entropy = 128

    # salt is not needed for api keys - https://security.stackexchange.com/questions/180345/do-i-need-to-hash-or-encrypt-api-keys-before-storing-them-in-a-database/180348
    def encode(self, password, salt="", iterations=None):
        assert password is not None
        # assert salt and "$" not in salt
        iterations = iterations or self.iterations
        hash = pbkdf2(password, "", iterations, digest=self.digest)
        hash = base64.b64encode(hash).decode("ascii").strip()
        return "%s$%d$%s$%s" % (self.algorithm, iterations, salt, hash)

    def decode(self, encoded):
        preview, algorithm, iterations, salt, hash = encoded.split("$", 4)
        assert algorithm == self.algorithm
        return {
            "algorithm": algorithm,
            "hash": hash,
            "iterations": int(iterations),
            "salt": salt,
        }


def pbkdf2(password: str, salt: str, iterations: int, dklen=0, digest=None):
    """Return the hash of password using pbkdf2."""
    if digest is None:
        digest = hashlib.sha256
    dklen = dklen or None
    password = password.encode()
    salt = salt.encode()
    return hashlib.pbkdf2_hmac(digest().name, password, salt, iterations, dklen)


def safe_preview(password: str) -> str:
    """Generate a safe preview of the password"""
    if len(password) < 20:
        return "****"
    else:
        # e.g. sk-4QB...mvo
        return password[:6] + "..." + password[-3:]


def get_random_doc_id() -> str:
    return get_random_string(
        length=8, allowed_chars=string.ascii_lowercase + string.digits
    )


def get_random_api_key() -> str:
    return "sk-" + get_random_string(length=48, allowed_chars=RANDOM_STRING_CHARS)


def get_random_string(length: int, allowed_chars: str) -> str:
    return "".join(secrets.choice(allowed_chars) for _ in range(length))
