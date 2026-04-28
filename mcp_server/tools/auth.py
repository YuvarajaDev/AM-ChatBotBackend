"""
mcp_server/tools/auth.py
========================
Auth tool — authenticate with AllMasters API.
Encrypts password using CryptoJS-compatible AES (pycryptodome)
so AM backend can decrypt it with the same shared key.
"""

import os
import sys
import json
import base64
import requests
from dotenv import load_dotenv
from Crypto.Cipher import AES
from Crypto.Hash  import MD5
from .utils import decode_am_jwt, get_role_name, _auth_headers

load_dotenv()

AM_API_BASE_URL   = os.getenv("AM_API_BASE_URL", "http://localhost:3000")
AM_ENCRYPTION_KEY = os.getenv("AM_ENCRYPTION_KEY", "")


# ── AES encryption (CryptoJS compatible) ─────────────────────────────────────

def _encrypt(plain_text: str) -> str:
    """
    Encrypt using CryptoJS.AES.encrypt(text, key) equivalent.
    Output format: Base64("Salted__" + salt(8) + ciphertext)
    """
    secret = AM_ENCRYPTION_KEY.encode("utf-8")
    salt   = os.urandom(8)

    # OpenSSL EVP_BytesToKey — derives 32-byte key + 16-byte IV from passphrase
    d, d_i = b"", b""
    while len(d) < 48:
        d_i = MD5.new(d_i + secret + salt).digest()
        d  += d_i
    key, iv = d[:32], d[32:48]

    # PKCS7 padding
    data    = plain_text.encode("utf-8")
    pad_len = 16 - len(data) % 16
    data   += bytes([pad_len] * pad_len)

    encrypted = AES.new(key, AES.MODE_CBC, iv).encrypt(data)
    return base64.b64encode(b"Salted__" + salt + encrypted).decode("utf-8")


# ── AM Auth API call ──────────────────────────────────────────────────────────
def get_user_type(email: str, encrypted_password: str) -> int:
    """
    Fetch the user role from AM before login.
    Passes email + encrypted password because the same email can have
    multiple users with different roles/types.
    Returns role as int, or 3 as fallback.
    """
    r = requests.post(
        f"{AM_API_BASE_URL}/user/getUserRoles",
        json={"data": [{"email": email, "password": encrypted_password, "isEncryptionRequired": False}]},
        timeout=10
    )
    r.raise_for_status()
    body = r.json()
    userRole = (body.get("data") or {}).get("role", 3)
    if(userRole == 1):
        return 1
    elif(userRole in [6,7]):
        return 2
    elif(userRole in [2,3,4,5]):
        return 3
    else:
        return 0

def proceed_login(username: str, encrypted_password: str, user_type: int) -> dict:
    r = requests.post(
            f"{AM_API_BASE_URL}/user/login",
            json={"data":[{
                "email": username,
                "password": encrypted_password,
                "isEncryptionRequired": False,
                "type": user_type
            }]},
            timeout=10
        )
    r.raise_for_status()
    return r.json()

def proceed_logout(id: str, type: int, jwt: str) -> dict:
    r = requests.post(
        f"{AM_API_BASE_URL}/public/logout",
        headers=_auth_headers(jwt),
        json={"data": [{"id": id, "type": type, "isEncryptionRequired": False}]},
        timeout=10
    )
    r.raise_for_status()
    return r.json()
def authenticate_user(username: str, password: str) -> dict:
    try:
        encrypted_password = _encrypt(password)

        # Fetch user type dynamically before login
        user_type = get_user_type(username, encrypted_password)
        # print(f"  [Auth] User type for {username}: {user_type}", file=sys.stderr)

        # AM returns data as a JSON string — parse the inner object
        loginData = proceed_login(username, encrypted_password, user_type)
        # print(f"loginData {loginData}", file=sys.stderr)
        inner = json.loads(loginData.get("data", "{}"))
        userValues = decode_am_jwt(inner.get("token", ""))
        if loginData["status"] == 0 and loginData["response"].replace(" ", "") == "UserAlreadyLoggedIn":
            # Try to logout the existing session and login again
            # print(f"  [Auth] User already logged in. Attempting to logout existing session.", file=sys.stderr)
            existing_user_id = userValues["userId"]
            logoutRes = proceed_logout(existing_user_id, userValues["type"], inner["token"])
            # print(f"  [Auth] Logout response: {logoutRes}", file=sys.stderr)
            if(logoutRes.get("status") == 0):
                # print(f"  [Auth] Logout successful. Retrying login.", file=sys.stderr)
                return {
                    "success": False,
                    "message": "Facing issue logging in. Please try again."
                }
            
            # Retry login after logout
            loginData = proceed_login(username, encrypted_password, user_type)
            inner = json.loads(loginData.get("data", "{}"))
            userValues = decode_am_jwt(inner.get("token", ""))
            # print(f"  [Auth] Re Authentication successful for user_id={userValues['userId']}", file=sys.stderr)
            return {
                "success":  True,
                "jwt":      inner["token"],
                "user_id":  userValues["userId"],
                "username": username,
                "role": userValues["role"],
                "type": userValues["type"]
            }
        # print(f"  [Auth] Authentication successful for user_id={userValues['userId']}", file=sys.stderr)
        return {
            "success":  True,
            "jwt":      inner["token"],
            "user_id":  userValues["userId"],
            "username": username,
            "role": userValues["role"],
            "type": userValues["type"]
        }

    except requests.exceptions.RequestException as e:
        # print(f"  [Auth] API unreachable. Reason: {e}", file=sys.stderr)
        return {
            "success": False,
            "message": "Authentication service unreachable. Please try again later."
        }
    except (KeyError, json.JSONDecodeError, AttributeError, TypeError) as e:
        # print(f"  [Auth] Unexpected response format. Reason: {e}", file=sys.stderr)
        return {
            "success": False,
            "message": "Authentication failed. Please check your credentials."
        }
    except Exception as e:
        # print(f"  [Auth] Unexpected error during authentication. Reason: {e}", file=sys.stderr)
        return {
            "success": False,
            "message": "An unexpected error occurred. Please try again."
        }
