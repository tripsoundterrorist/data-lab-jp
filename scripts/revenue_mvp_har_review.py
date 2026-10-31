"""Pure, bounded HAR content inspection. No supported live exporter profile yet.

No file, network, browser or Gate integration. A matching supplied body remains
BLOCKED for provenance; never constructs a trusted capture observation.
"""
import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math

import revenue_mvp_price_display_transition as display
import revenue_mvp_price_filter_copy_candidate as copy_candidate

MAX_HAR = 2 * 1024 * 1024


@dataclass(frozen=True)
class HarReview:
    status: str = "BLOCKED"
    reason_code: str = "HAR_INPUT_INVALID"
    schema_version: int = 1
    artifact_sha256: str | None = None
    supplied_content_match: bool = False
    trusted_public_capture: bool = False
    current_eligibility_verified: bool = False
    publication_allowed: bool = False
    gate_mutation_allowed: bool = False
    database_write_performed: bool = False


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _constant(_):
    raise ValueError


def _shape(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() <= set(required) | set(optional):
        raise ValueError


def _text(value, limit=256):
    if type(value) is not str or len(value) > limit:
        raise ValueError
    value.encode("utf-8", errors="strict")
    return value


def _bounded_json(payload):
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_HAR:
        raise ValueError
    text = payload.decode("utf-8", errors="strict")
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 16:
                raise ValueError
        elif char in "}]":
            depth -= 1
            if depth < 0:
                raise ValueError
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)


def _headers(value):
    if type(value) is not list or len(value) > 2:
        raise ValueError
    headers = {}
    for item in value:
        _shape(item, ("name", "value"))
        name = _text(item["name"]).lower()
        content = _text(item["value"])
        if name not in ("content-type", "content-encoding") or name in headers:
            raise ValueError
        headers[name] = content.lower()
    return headers


def review(payload, *, expected_sha256, evaluated_at):
    """Inspect a strict minimal HAR subset. All exporter provenance is unconfirmed.

Standard optional fields not explicitly supported here are rejected rather than
silently stripped. This is intentionally not a Chrome export compatibility claim.
"""
    try:
        if expected_sha256 not in (display.CANDIDATE, copy_candidate.CANDIDATE_SHA256):
            raise ValueError
        root = _bounded_json(payload)
        _shape(root, ("log",))
        log = root["log"]
        _shape(log, ("version", "creator", "entries"))
        if log["version"] != "1.2":
            raise ValueError
        _shape(log["creator"], ("name", "version"))
        for value in log["creator"].values():
            _text(value)
        if type(log["entries"]) is not list or len(log["entries"]) != 1:
            raise ValueError
        entry = log["entries"][0]
        _shape(entry, ("startedDateTime", "time", "request", "response", "cache", "timings"))
        request, response = entry["request"], entry["response"]
        _shape(request, ("method", "url", "headers", "cookies", "queryString"))
        if (request["method"] != "GET" or request["url"] != display.URL or
                request["headers"] != [] or request["cookies"] != [] or request["queryString"] != []):
            raise ValueError
        _shape(response, ("status", "redirectURL", "headers", "cookies", "content"))
        if (type(response["status"]) is not int or response["status"] != 200 or
                response["redirectURL"] != "" or response["cookies"] != [] or entry["cache"] != {}):
            raise ValueError
        headers = _headers(response["headers"])
        content = response["content"]
        _shape(content, ("size", "mimeType", "text"), ("encoding",))
        mime = _text(content["mimeType"]).lower()
        if (mime not in ("text/html; charset=utf-8", 'text/html; charset="utf-8"') or
                headers.get("content-type") != mime or
                headers.get("content-encoding", "") not in ("", "identity", "gzip", "br")):
            raise ValueError
        text = _text(content["text"], MAX_HAR)
        # HAR text is already HTTP decoded. Never decompress from retained headers.
        if "encoding" not in content:
            body = text.encode("utf-8")
        elif content["encoding"] == "base64":
            if len(text) > 4 * ((display.MAX_BYTES + 2) // 3):
                raise ValueError
            body = base64.b64decode(text, validate=True)
        else:
            raise ValueError
        if (not 0 < len(body) <= display.MAX_BYTES or type(content["size"]) is not int
                or content["size"] != len(body)):
            raise ValueError
        started = datetime.fromisoformat(_text(entry["startedDateTime"]))
        duration = entry["time"]
        if (type(duration) not in (int, float) or not math.isfinite(duration) or
                not 0 <= duration <= 900000 or not isinstance(evaluated_at, datetime) or
                started.tzinfo is None or evaluated_at.tzinfo is None or
                not timedelta(0) <= evaluated_at - started <= timedelta(minutes=15) or
                started + timedelta(milliseconds=duration) > evaluated_at):
            raise ValueError
        timings = entry["timings"]
        _shape(timings, ("send", "wait", "receive"))
        for value in timings.values():
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= duration:
                raise ValueError
        if sum(timings.values()) > duration:
            raise ValueError
        digest = sha256(display.canonical(body)).hexdigest()
        if digest != expected_sha256:
            return HarReview(reason_code="HAR_CONTENT_MISMATCH")
        return HarReview(reason_code="HAR_PROVENANCE_UNCONFIRMED",
                         artifact_sha256=digest, supplied_content_match=True)
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError, binascii.Error):
        return HarReview()
