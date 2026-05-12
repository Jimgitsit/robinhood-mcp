"""
Robinhood authentication with session caching and MFA support.

Credentials are read from environment variables:
  ROBINHOOD_USERNAME      — Robinhood account email
  ROBINHOOD_PASSWORD      — Robinhood account password
  ROBINHOOD_TOTP_SECRET   — base32 TOTP secret for automatic 2FA. Strongly
                            recommended; without it every login requires
                            manual approval from a push prompt.

Login flow:
  1. If ~/.tokens/robinhood.pickle exists, restore the cached session and skip
     the network round trip.
  2. Otherwise POST to /oauth2/token/ directly (bypassing robin_stocks.login,
     whose verification-workflow path silently fails to set the Authorization
     header). The pickle stores the access_token AND the device_token so
     subsequent logins reuse the verified device — the user only has to
     approve a push prompt the first time the pickle is missing.
"""

import os
import pickle
import sys
import threading
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pyotp
from dotenv import load_dotenv

load_dotenv()

_PICKLE_PATH = Path.home() / ".tokens" / "robinhood.pickle"

_lock = threading.Lock()
_logged_in = False


# Suppress stdout so robin_stocks' login prints don't corrupt the stdio JSON-RPC stream.
@contextmanager
def _suppress_stdout():
    old = sys.stdout
    sys.stdout = StringIO()
    try:
        yield
    finally:
        sys.stdout = old


def _do_login() -> None:
    """
    Direct OAuth2 login to Robinhood.

    Bypasses robin_stocks.login() because its verification-workflow handling
    is unreliable (silently fails to set the Authorization header and pickle).
    Persists the device_token in the pickle so subsequent logins are
    TOTP-only — only the first login from a given device requires the user
    to approve a push prompt on their phone.
    """
    import robin_stocks.robinhood as rh
    from robin_stocks.robinhood.authentication import (
        generate_device_token,
        _validate_sherrif_id,
    )

    username = os.environ.get("ROBINHOOD_USERNAME")
    password = os.environ.get("ROBINHOOD_PASSWORD")
    totp_secret = os.environ.get("ROBINHOOD_TOTP_SECRET", "").strip()

    if not username or not password:
        raise RuntimeError(
            "ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD must be set."
        )

    device_token = _load_device_token() or generate_device_token()

    payload = {
        "client_id": "c82SH0WZOsabOXGP2sxqcj34FxkvfnWRZBKlBjFS",
        "expires_in": 86400,
        "grant_type": "password",
        "password": password,
        "scope": "internal",
        "username": username,
        "device_token": device_token,
        "try_passkeys": False,
        "token_request_path": "/login",
        "create_read_only_secondary_token": True,
    }
    if totp_secret:
        payload["mfa_code"] = pyotp.TOTP(totp_secret).now()

    data = _post_login(payload)

    if "verification_workflow" in data:
        workflow_id = data["verification_workflow"]["id"]
        print(
            f"[robinhood-mcp] First-time device verification required. "
            f"Approve the push notification on your Robinhood app...",
            file=sys.stderr,
        )
        # _validate_sherrif_id polls until the user approves on their phone.
        with _suppress_stdout():
            _validate_sherrif_id(device_token, workflow_id)
        # Refresh the TOTP code (the workflow can take a minute or more).
        if totp_secret:
            payload["mfa_code"] = pyotp.TOTP(totp_secret).now()
        data = _post_login(payload)

    if "access_token" not in data:
        raise RuntimeError(f"Robinhood login failed: {data}")

    token = data["access_token"]
    token_type = data.get("token_type", "Bearer")
    rh.helper.update_session("Authorization", f"{token_type} {token}")
    rh.helper.set_login_state(True)

    _PICKLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_PICKLE_PATH, "wb") as f:
        pickle.dump(
            {"access_token": token, "token_type": token_type, "device_token": device_token},
            f,
        )


def _post_login(payload: dict) -> dict:
    """POST to the Robinhood OAuth endpoint and return the parsed body."""
    import robin_stocks.robinhood as rh

    resp = rh.helper.SESSION.post(
        "https://api.robinhood.com/oauth2/token/", data=payload, timeout=15
    )
    return resp.json() if resp.content else {}


def _load_device_token() -> str:
    """Return the device_token from the cached pickle, or '' if absent."""
    if not _PICKLE_PATH.exists():
        return ""
    try:
        with open(_PICKLE_PATH, "rb") as f:
            data = pickle.load(f)
        return data.get("device_token", "")
    except Exception:
        return ""


def _try_restore_session() -> bool:
    """
    Attempt to restore a cached session from the pickle file.
    Returns True if the session appears valid (has an access token).
    """
    import robin_stocks.robinhood as rh

    if not _PICKLE_PATH.exists():
        return False
    try:
        with open(_PICKLE_PATH, "rb") as f:
            data = pickle.load(f)
        token = data.get("access_token") or data.get("token")
        if not token:
            return False
        token_type = data.get("token_type", "Bearer")
        rh.helper.set_login_state(True)
        rh.helper.update_session("Authorization", f"{token_type} {token}")
        return True
    except Exception:
        return False


def _session_is_valid() -> bool:
    """Quick check: try a lightweight authenticated endpoint."""
    import robin_stocks.robinhood as rh

    try:
        profile = rh.load_account_profile(info="account_number")
        return profile is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ensure_logged_in() -> None:
    """
    Ensure a valid Robinhood session exists.  Thread-safe; called at startup
    and before any tool invocation that needs auth.
    """
    global _logged_in
    with _lock:
        if _logged_in:
            return
        if _try_restore_session() and _session_is_valid():
            _logged_in = True
            print("[robinhood-mcp] Restored cached Robinhood session.", file=sys.stderr)
            return
        # Cached session missing or stale — do a fresh login
        if _PICKLE_PATH.exists():
            _PICKLE_PATH.unlink(missing_ok=True)
        _do_login()
        _logged_in = True
        print("[robinhood-mcp] Logged in to Robinhood.", file=sys.stderr)


def logout() -> None:
    """Log out and remove cached session."""
    global _logged_in
    import robin_stocks.robinhood as rh

    with _lock:
        with _suppress_stdout():
            rh.logout()
        _PICKLE_PATH.unlink(missing_ok=True)
        _logged_in = False
        print("[robinhood-mcp] Logged out.", file=sys.stderr)


def force_relogin() -> None:
    """Discard the current session and login fresh."""
    global _logged_in
    with _lock:
        _logged_in = False
    ensure_logged_in()
