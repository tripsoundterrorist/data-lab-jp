"""Fail-closed runtime sender for Pushover-safe notification contracts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping
from urllib import parse, request

import pushover_notification_adapter as adapter


SENDER_VERSION = "0.1"
ENDPOINT = "https://api.pushover.net/1/messages.json"
TIMEOUT_SECONDS = 10
MODES = frozenset({"DRY_RUN", "MOCK_SEND", "LIVE_SEND"})
INPUT_FIELDS = adapter.OUTPUT_FIELDS
OUTPUT_FIELDS = frozenset({
    "sender_version", "sender_mode", "sender_status", "delivery_attempted",
    "delivery_succeeded", "suppressible_skipped", "emergency_blocked",
    "credential_presence_ok", "reason_codes",
})
SAFE_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
UNSAFE_TEXT = re.compile(
    r"(?i)(?:https?|ftp|file)://|www\.|[a-z]:[\\/]|^/|^\\\\|"
    r"credential|password|secret|token|user[_ -]?key|raw[_ -]?(?:event|response|exception)|"
    r"traceback|content[_ -]?id|product[_ -]?id"
)


@dataclass(frozen=True)
class SenderResult:
    sender_version: str
    sender_mode: str
    sender_status: str
    delivery_attempted: bool
    delivery_succeeded: bool
    suppressible_skipped: bool
    emergency_blocked: bool
    credential_presence_ok: bool
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in self.__dict__.items() if key != "reason_codes"},
            "reason_codes": list(self.reason_codes),
        }


CredentialLoader = Callable[[], tuple[str | None, str | None]]
Transport = Callable[[str, Mapping[str, Any], int], Any]


def _result(mode: Any, status: str, *, attempted: bool = False,
            succeeded: bool = False, skipped: bool = False,
            emergency: bool = False, credentials: bool = False,
            reasons: tuple[str, ...]) -> SenderResult:
    safe_mode = mode if mode in MODES else "DRY_RUN"
    return SenderResult(
        SENDER_VERSION, safe_mode, status, attempted, succeeded, skipped,
        emergency, credentials, tuple(sorted(set(reasons))),
    )


def load_credentials(env_path: Path | None = None) -> tuple[str | None, str | None]:
    """Read only the two required values without logging or returning metadata."""

    path = env_path if env_path is not None else Path(__file__).resolve().parents[1] / ".env"
    found: dict[str, str] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                name = name.strip()
                if name in {"PUSHOVER_USER_KEY", "PUSHOVER_APP_TOKEN"}:
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        value = value[1:-1]
                    found[name] = value
    except (OSError, UnicodeError):
        return None, None
    return found.get("PUSHOVER_USER_KEY"), found.get("PUSHOVER_APP_TOKEN")


def _default_transport(endpoint: str, payload: Mapping[str, Any], timeout: int) -> Any:
    encoded = parse.urlencode(payload).encode("utf-8")
    outbound = request.Request(endpoint, data=encoded, method="POST")
    with request.urlopen(outbound, timeout=timeout) as response:
        if response.status != 200:
            return {"status": 0}
        return json.loads(response.read().decode("utf-8"))


def _contract(value: Any) -> tuple[Mapping[str, Any] | None, tuple[str, ...]]:
    if isinstance(value, adapter.PushoverNotification):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        return None, ("NOTIFICATION_CONTRACT_INVALID",)
    if set(value) != INPUT_FIELDS:
        return None, ("NOTIFICATION_SCHEMA_INVALID",)
    if value["adapter_version"] != adapter.ADAPTER_VERSION:
        return None, ("ADAPTER_VERSION_UNSUPPORTED",)
    if value["notification_status"] != adapter.READY:
        return None, ("NOTIFICATION_NOT_READY",)
    priority = value["pushover_priority"]
    if not isinstance(priority, int) or isinstance(priority, bool) or priority not in {-1, 0, 1, 2}:
        return None, ("PRIORITY_INVALID",)
    if not isinstance(value["emergency_candidate"], bool) or value["emergency_candidate"] != (priority == 2):
        return None, ("EMERGENCY_FLAG_MISMATCH",)
    if value["delivery_class"] not in {"IMMEDIATE", "NORMAL", "SUPPRESSIBLE"}:
        return None, ("DELIVERY_CLASS_INVALID",)
    if not isinstance(value["approval_required"], bool):
        return None, ("APPROVAL_FLAG_INVALID",)
    title, message = value["title"], value["message"]
    if (not isinstance(title, str) or not title or len(title) > adapter.TITLE_LIMIT
            or not isinstance(message, str) or not message or len(message) > adapter.MESSAGE_LIMIT
            or UNSAFE_TEXT.search(title) or UNSAFE_TEXT.search(message)):
        return None, ("NOTIFICATION_TEXT_UNSAFE",)
    reasons = value["reason_codes"]
    if (not isinstance(reasons, (tuple, list)) or not reasons
            or any(not isinstance(code, str) or SAFE_REASON.fullmatch(code) is None for code in reasons)):
        return None, ("NOTIFICATION_REASONS_INVALID",)
    return value, ()


def _send(notification: Any, *, sender_version: Any, mode: Any,
          live_send_confirmed: Any, send_suppressible: Any,
          credential_loader: CredentialLoader | None,
          transport: Transport | None) -> SenderResult:
    if sender_version != SENDER_VERSION:
        return _result(mode, "INVALID_INPUT", reasons=("SENDER_VERSION_UNSUPPORTED",))
    if mode not in MODES:
        return _result(mode, "INVALID_INPUT", reasons=("SENDER_MODE_INVALID",))
    if not isinstance(live_send_confirmed, bool) or not isinstance(send_suppressible, bool):
        return _result(mode, "INVALID_INPUT", reasons=("SENDER_FLAG_INVALID",))
    value, reasons = _contract(notification)
    if value is None:
        return _result(mode, "INVALID_INPUT", reasons=reasons)
    loader = credential_loader or load_credentials
    user_key, app_token = loader()
    credentials_ok = bool(user_key) and bool(app_token)
    if not credentials_ok:
        return _result(mode, "CREDENTIAL_MISSING", reasons=("CREDENTIAL_PRESENCE_REQUIRED",))
    if value["emergency_candidate"]:
        return _result(mode, "EMERGENCY_SEND_BLOCKED", emergency=True,
                       credentials=True, reasons=("EMERGENCY_POLICY_UNDEFINED",))
    if value["delivery_class"] == "SUPPRESSIBLE" and not send_suppressible:
        return _result(mode, "SUPPRESSED", skipped=True, credentials=True,
                       reasons=("SUPPRESSIBLE_DEFAULT_SKIP",))
    if mode == "DRY_RUN":
        return _result(mode, "DRY_RUN_READY", credentials=True,
                       reasons=("NOTIFICATION_VALIDATED",))
    if mode == "LIVE_SEND" and not live_send_confirmed:
        return _result(mode, "LIVE_SEND_NOT_CONFIRMED", credentials=True,
                       reasons=("EXPLICIT_LIVE_CONFIRMATION_REQUIRED",))
    if mode == "MOCK_SEND" and transport is None:
        return _result(mode, "INVALID_INPUT", credentials=True,
                       reasons=("MOCK_TRANSPORT_REQUIRED",))
    payload = {
        "token": app_token, "user": user_key, "title": value["title"],
        "message": value["message"], "priority": value["pushover_priority"],
    }
    chosen_transport = transport or _default_transport
    try:
        response = chosen_transport(ENDPOINT, payload, TIMEOUT_SECONDS)
        if not isinstance(response, Mapping) or response.get("status") != 1:
            return _result(mode, "SEND_FAILED_SAFE", attempted=True,
                           credentials=True, reasons=("RESPONSE_NOT_SUCCESSFUL",))
        return _result(mode, "SEND_SUCCEEDED", attempted=True, succeeded=True,
                       credentials=True, reasons=("DELIVERY_CONFIRMED",))
    except Exception:
        return _result(mode, "SEND_FAILED_SAFE", attempted=True,
                       credentials=True, reasons=("TRANSPORT_FAILURE",))


def send_notification(
    notification: Any, *, sender_version: Any = SENDER_VERSION,
    mode: Any = "DRY_RUN", live_send_confirmed: Any = False,
    send_suppressible: Any = False,
    credential_loader: CredentialLoader | None = None,
    transport: Transport | None = None,
) -> SenderResult:
    """Validate and optionally send once; never retries and never exposes secrets."""

    try:
        return _send(
            notification, sender_version=sender_version, mode=mode,
            live_send_confirmed=live_send_confirmed,
            send_suppressible=send_suppressible,
            credential_loader=credential_loader, transport=transport,
        )
    except Exception:
        return _result(mode, "SEND_FAILED_SAFE", reasons=("INTERNAL_SENDER_ERROR",))


__all__ = [
    "ENDPOINT", "INPUT_FIELDS", "MODES", "OUTPUT_FIELDS", "SENDER_VERSION",
    "SenderResult", "TIMEOUT_SECONDS", "load_credentials", "send_notification",
]
