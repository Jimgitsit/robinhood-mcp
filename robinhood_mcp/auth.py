"""
Robinhood authentication with session caching and MFA support.

Credentials are read from environment variables:
  ROBINHOOD_USERNAME      — Robinhood account email
  ROBINHOOD_PASSWORD      — Robinhood account password
  ROBINHOOD_TOTP_SECRET   — (optional) base32 TOTP secret; enables automatic
                            TOTP-based 2FA so no mobile push notification is needed.

If ROBINHOOD_TOTP_SECRET is not set, the login flow polls Robinhood's challenge
endpoint every 5 seconds (up to 2 minutes) waiting for the user to approve the
mobile push notification.  robin_stocks' built-in _validate_sherrif_id is NOT
used because it calls input(), which corrupts the stdio JSON-RPC transport.
"""

import os
import pickle
import sys
import threading
import time
from contextlib import contextmanager
from io import StringIO
from pathlib import Path

import pyotp
import requests
from dotenv import load_dotenv

load_dotenv()

_PICKLE_PATH = Path.home() / ".tokens" / "robinhood.pickle"
_CHALLENGE_POLL_INTERVAL = 5   # seconds between polls
_CHALLENGE_TIMEOUT = 120        # seconds before giving up

_lock = threading.Lock()
_logged_in = False


# ---------------------------------------------------------------------------
# Stdout suppression — prevents robin_stocks login noise from corrupting
# the stdio JSON-RPC stream.
# ---------------------------------------------------------------------------

@contextmanager
def _suppress_stdout():
    old = sys.stdout
    sys.stdout = StringIO()
    try:
        yield
    finally:
        sys.stdout = old


# ---------------------------------------------------------------------------
# Challenge (push-notification) polling
# ---------------------------------------------------------------------------

def _poll_challenge(challenge_id: str, device_token: str) -> bool:
    """
    Poll Robinhood's challenge endpoint until the user approves the push
    notification on their phone (or until we time out).

    Returns True if approved, False otherwise.
    """
    url = f"https://api.robinhood.com/challenge/{challenge_id}/respond/"
    deadline = time.monotonic() + _CHALLENGE_TIMEOUT
    print(
        f"[robinhood-mcp] Waiting for mobile push notification approval "
        f"(up to {_CHALLENGE_TIMEOUT}s)...",
        file=sys.stderr,
    )
    while time.monotonic() < deadline:
        try:
            resp = requests.get(
                f"https://api.robinhood.com/challenge/{challenge_id}/",
                headers={"X-Robinhood-API-Version": "1.431.4"},
                timeout=10,
            )
            data = resp.json()
            status = data.get("status", "")
            if status == "validated":
                print("[robinhood-mcp] Push notification approved.", file=sys.stderr)
                return True
            if status in ("expired", "invalidated"):
                print(f"[robinhood-mcp] Challenge {status}.", file=sys.stderr)
                return False
        except Exception:
            pass
        time.sleep(_CHALLENGE_POLL_INTERVAL)
    print("[robinhood-mcp] Challenge timed out.", file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# Core login
# ---------------------------------------------------------------------------

def _do_login() -> None:
    """Perform a fresh login and cache the session pickle."""
    import robin_stocks.robinhood as rh

    username = os.environ.get("ROBINHOOD_USERNAME")
    password = os.environ.get("ROBINHOOD_PASSWORD")
    totp_secret = os.environ.get("ROBINHOOD_TOTP_SECRET", "").strip()

    if not username or not password:
        raise RuntimeError(
            "ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD must be set."
        )

    mfa_code = pyotp.TOTP(totp_secret).now() if totp_secret else None

    _PICKLE_PATH.parent.mkdir(parents=True, exist_ok=True)

    with _suppress_stdout():
        result = rh.login(
            username=username,
            password=password,
            mfa_code=mfa_code,
            store_session=True,
            pickle_path=str(_PICKLE_PATH.parent),
            pickle_name=_PICKLE_PATH.name,
        )

    # robin_stocks returns None on success; a dict with an 'access_token' key.
    # If it came back with a challenge required, result will contain detail.
    if isinstance(result, dict):
        challenge_id = result.get("challenge", {}).get("id")
        if challenge_id:
            if not totp_secret:
                approved = _poll_challenge(challenge_id, device_token="")
                if not approved:
                    raise RuntimeError("Robinhood challenge not approved in time.")
                # Retry login — by now the challenge is validated
                with _suppress_stdout():
                    rh.login(
                        username=username,
                        password=password,
                        store_session=True,
                        pickle_path=str(_PICKLE_PATH.parent),
                        pickle_name=_PICKLE_PATH.name,
                    )
            else:
                raise RuntimeError(
                    "Robinhood returned a challenge even though TOTP was provided. "
                    "Check that ROBINHOOD_TOTP_SECRET is correct."
                )


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
        # Inject token into robin_stocks session headers
        rh.helper.set_login_state(True)
        rh.helper.update_session("Authorization", f"Bearer {token}")
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
