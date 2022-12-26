"""
Stolen code from https://docs.djangoproject.com/en/3.2/_modules/django/contrib/auth/hashers/
"""

import base64
import hashlib
import math
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

    def salt(self):
        """
        Generate a cryptographically secure nonce salt in ASCII with an entropy
        of at least `salt_entropy` bits.
        """
        # Each character in the salt provides
        # log_2(len(alphabet)) bits of entropy.
        char_count = math.ceil(self.salt_entropy / math.log2(len(RANDOM_STRING_CHARS)))
        return get_random_string(char_count, allowed_chars=RANDOM_STRING_CHARS)

    def encode(self, password, salt, iterations=None):
        assert password is not None
        assert salt and "$" not in salt
        iterations = iterations or self.iterations
        hash = pbkdf2(password, salt, iterations, digest=self.digest)
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

    def verify(self, password, encoded):
        decoded = self.decode(encoded)
        encoded_2 = self.encode(password, decoded["salt"], decoded["iterations"])
        return constant_time_compare(encoded, encoded_2)


def constant_time_compare(val1, val2):
    """Return True if the two strings are equal, False otherwise."""
    return secrets.compare_digest(val1.encode(), val2.encode())


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
        # e.g. gsk-4QB...mvo
        return password[:7] + "..." + password[-3:]


def get_random_string_lowercase(
    length=8, allowed_chars=string.ascii_lowercase + string.digits
):
    return "".join(secrets.choice(allowed_chars) for _ in range(length))


def get_random_string(length: int, allowed_chars: str):
    return "".join(secrets.choice(allowed_chars) for _ in range(length))
