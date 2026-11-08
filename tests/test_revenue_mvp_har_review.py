import base64
import copy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revenue_mvp_har_review as subject


class HarReviewTests(unittest.TestCase):
    def setUp(self):
        self.body = b"<html>synthetic only</html>\n"
        self.digest = sha256(self.body).hexdigest()
        self.now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        self.pin = patch.object(subject.display, "CANDIDATE", self.digest)
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.entry = dict(startedDateTime=(self.now-timedelta(seconds=2)).isoformat(), time=1000,
                          request=dict(method="GET", url=subject.display.URL, headers=[], cookies=[], queryString=[]),
                          response=dict(status=200, redirectURL="", cookies=[],
                                        headers=[dict(name="Content-Type", value="text/html; charset=utf-8")],
                                        content=dict(size=len(self.body), mimeType="text/html; charset=utf-8", text=self.body.decode())),
                          cache={}, timings=dict(send=0, wait=500, receive=500))

    def payload(self, entry=None):
        return json.dumps(dict(log=dict(version="1.2", creator=dict(name="synthetic", version="1"),
                                        entries=[self.entry if entry is None else entry]))).encode()

    def review(self, payload=None):
        return subject.review(self.payload() if payload is None else payload,
                              expected_sha256=self.digest, evaluated_at=self.now)

    def test_match_remains_blocked(self):
        result = self.review()
        self.assertTrue(result.supplied_content_match)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.reason_code, "HAR_PROVENANCE_UNCONFIRMED")
        for name in ("trusted_public_capture", "current_eligibility_verified", "publication_allowed",
                     "gate_mutation_allowed", "database_write_performed"):
            self.assertFalse(getattr(result, name))

    def test_base64_and_gzip_header_does_not_double_decode(self):
        self.entry["response"]["headers"].append(dict(name="Content-Encoding", value="gzip"))
        self.entry["response"]["content"].update(encoding="base64", text=base64.b64encode(self.body).decode())
        self.assertTrue(self.review().supplied_content_match)

    def test_bad_json_limits_and_duplicates(self):
        for payload in (b"", b"x"*(subject.MAX_HAR+1), b"["*17+b"]"*17,
                        b'{"log":{},"log":{}}', b'{"log":NaN}', b"\xff", b'{"log":Infinity}'):
            self.assertEqual(self.review(payload).reason_code, "HAR_INPUT_INVALID")

    def test_sensitive_and_unknown_fields_never_echoed(self):
        secret = "SYNTHETIC_SECRET_DO_NOT_ECHO"
        for area in ("headers", "postData", "comment", "_serviceWorker"):
            entry = copy.deepcopy(self.entry)
            entry["request"][area] = secret
            stream = io.StringIO()
            with redirect_stdout(stream), redirect_stderr(stream):
                result = self.review(self.payload(entry))
            self.assertFalse(result.supplied_content_match)
            self.assertNotIn(secret, repr(result)+stream.getvalue())

    def test_invalid_response_and_times(self):
        variants = []
        for container, key, value in (("request", "url", subject.display.URL+"?x=secret"),
                                      ("response", "status", 304), ("response", "status", True),
                                      ("response", "redirectURL", subject.display.URL)):
            entry = copy.deepcopy(self.entry)
            entry[container][key] = value
            variants.append(entry)
        for stamp in (self.now.isoformat(), self.now.replace(tzinfo=None).isoformat(),
                      (self.now-timedelta(minutes=16)).isoformat()):
            entry = copy.deepcopy(self.entry)
            entry["startedDateTime"] = stamp
            variants.append(entry)
        for entry in variants:
            self.assertFalse(self.review(self.payload(entry)).supplied_content_match)

    def test_body_mismatch_invalid_encoding_and_duplicate_headers(self):
        for key, value in (("text", "changed"), ("text", "\ud800"), ("encoding", "gzip"),
                           ("size", True), ("size", 0)):
            entry = copy.deepcopy(self.entry)
            entry["response"]["content"][key] = value
            self.assertFalse(self.review(self.payload(entry)).supplied_content_match)
        self.entry["response"]["headers"] *= 2
        self.assertFalse(self.review().supplied_content_match)

    def test_existing_gate_rejects_har_receipt(self):
        old = '<p>1円</p>'.encode()*100
        new = old.replace('円</p>'.encode(), '円〜</p>'.encode())
        receipt = self.review()
        with patch.object(subject.display, "BASELINE", sha256(old).hexdigest()), \
                patch.object(subject.display, "CANDIDATE", sha256(new).hexdigest()):
            result = subject.display.review(old, new,
                {"items_artifact_sha256": sha256(old).hexdigest()}, observation=receipt)
        self.assertEqual(result.reason_code, "TRUSTED_PUBLIC_CAPTURE_REQUIRED")

    def test_cache_multiple_entries_and_invalid_base64(self):
        entry = copy.deepcopy(self.entry)
        entry["cache"] = {"afterRequest": {}}
        self.assertFalse(self.review(self.payload(entry)).supplied_content_match)
        document = json.loads(self.payload())
        document["log"]["entries"] *= 2
        self.assertFalse(self.review(json.dumps(document).encode()).supplied_content_match)
        self.entry["response"]["content"].update(encoding="base64", text="%%%")
        self.assertFalse(self.review().supplied_content_match)

    def test_secret_bearing_fields_at_every_envelope_level(self):
        secret = "SYNTHETIC_PRIVATE_VALUE"
        for path, key in (((), "comment"), (("log",), "comment"),
                          (("log", "creator"), "_private"),
                          (("log", "entries", 0), "serverIPAddress"),
                          (("log", "entries", 0, "response"), "comment"),
                          (("log", "entries", 0, "response", "content"), "comment")):
            document = json.loads(self.payload())
            target = document
            for part in path:
                target = target[part]
            target[key] = secret
            stream = io.StringIO()
            with redirect_stdout(stream), redirect_stderr(stream):
                result = self.review(json.dumps(document).encode())
            self.assertEqual(result.reason_code, "HAR_INPUT_INVALID")
            self.assertNotIn(secret, repr(result)+stream.getvalue())

    def test_cookies_authorization_and_case_insensitive_header_duplicates(self):
        for field, value in (("cookies", [{"name": "session", "value": "SYNTHETIC"}]),
                             ("headers", [{"name": "Authorization", "value": "SYNTHETIC"}])):
            for side in ("request", "response"):
                entry = copy.deepcopy(self.entry)
                entry[side][field] = value
                self.assertFalse(self.review(self.payload(entry)).supplied_content_match)
        self.entry["response"]["headers"].append(
            dict(name="CONTENT-TYPE", value="text/html; charset=utf-8"))
        self.assertFalse(self.review().supplied_content_match)

    def test_time_numeric_and_evaluation_boundaries(self):
        for value in (True, -1, 900001, float("inf"), float("nan"), "1000", None, 10**1000):
            entry = copy.deepcopy(self.entry)
            entry["time"] = value
            self.assertFalse(self.review(self.payload(entry)).supplied_content_match)
        for now in (None, self.now.replace(tzinfo=None), "2026-10-15"):
            self.assertFalse(subject.review(self.payload(), expected_sha256=self.digest,
                                            evaluated_at=now).supplied_content_match)
        self.entry["startedDateTime"] = (self.now-timedelta(minutes=15)).isoformat()
        self.assertTrue(self.review().supplied_content_match)
        self.entry["startedDateTime"] = (self.now-timedelta(minutes=15, microseconds=1)).isoformat()
        self.assertFalse(self.review().supplied_content_match)

    def test_timings_and_future_completion(self):
        for value in (True, -1, 1001, float("inf"), "500", None):
            entry = copy.deepcopy(self.entry)
            entry["timings"]["wait"] = value
            self.assertFalse(self.review(self.payload(entry)).supplied_content_match)
        self.entry["timings"] = dict(send=500, wait=500, receive=500)
        self.assertFalse(self.review().supplied_content_match)
        self.entry["timings"] = dict(send=0, wait=500, receive=500)
        self.entry["startedDateTime"] = (self.now-timedelta(milliseconds=999)).isoformat()
        self.assertFalse(self.review().supplied_content_match)

    def test_depth_scanner_strings_escapes_and_duplicate_nested_keys(self):
        document = json.loads(self.payload())
        document["log"]["creator"]["name"] = 'brackets[{]} quote" slash\\'
        self.assertTrue(self.review(json.dumps(document).encode()).supplied_content_match)
        self.assertEqual(subject._bounded_json(b"["*16+b"0"+b"]"*16),
                         json.loads(b"["*16+b"0"+b"]"*16))
        for payload in (b'{"log":{"version":"1.2","version":"1.2"}}',
                        b'{"log":{"\\u0076ersion":1,"version":2}}',
                        b'{"log":"unterminated}', b"{} trailing", b"["*17+b"]"*17):
            self.assertFalse(self.review(payload).supplied_content_match)

    def test_payload_and_decoded_body_limits(self):
        for payload in (None, "{}", bytearray(b"{}")):
            self.assertEqual(self.review(payload if payload is not None else b"null").status, "BLOCKED")
        # Exercise exact size boundaries cheaply, without allocating production data.
        with patch.object(subject, "MAX_HAR", len(self.payload())):
            self.assertTrue(self.review().supplied_content_match)
            self.assertFalse(self.review(self.payload()+b" ").supplied_content_match)
        with patch.object(subject.display, "MAX_BYTES", len(self.body)-1):
            self.assertFalse(self.review().supplied_content_match)
        with patch.object(subject.display, "MAX_BYTES", len(self.body)):
            self.assertTrue(self.review().supplied_content_match)

    def test_base64_truncation_and_utf8_fail_closed(self):
        for text in ("%%%", "YQ", "YQ===", " YQ==", "/w=="):
            entry = copy.deepcopy(self.entry)
            entry["response"]["content"].update(encoding="base64", text=text, size=1)
            self.assertFalse(self.review(self.payload(entry)).supplied_content_match)

    def test_crlf_and_replay_do_not_grant_authority(self):
        body = self.body.replace(b"\n", b"\r\n")
        self.entry["response"]["content"].update(text=body.decode(), size=len(body))
        for _ in range(2):
            result = self.review()
            self.assertTrue(result.supplied_content_match)
            self.assertEqual(result.status, "BLOCKED")
            self.assertFalse(result.trusted_public_capture)
        result = subject.review(self.payload(), expected_sha256=self.digest,
                                evaluated_at=self.now+timedelta(minutes=16))
        self.assertFalse(result.supplied_content_match)

    def test_body_mismatch_never_exports_unknown_digest(self):
        self.entry["response"]["content"].update(text="different", size=9)
        result = self.review()
        self.assertEqual(result.reason_code, "HAR_CONTENT_MISMATCH")
        self.assertIsNone(result.artifact_sha256)

    def test_duplicate_key_in_otherwise_valid_har(self):
        payload = self.payload()
        old = b'"version": "1.2"'
        self.assertEqual(payload.count(old), 1)
        self.assertTrue(self.review(payload).supplied_content_match)
        duplicate = payload.replace(old, b'"version": "1.2", "version": "1.2"', 1)
        result = self.review(duplicate)
        self.assertEqual(result.reason_code, "HAR_INPUT_INVALID")
        self.assertFalse(result.supplied_content_match)

    def test_parser_has_no_file_network_or_database_effects(self):
        payload = self.payload()
        with patch("builtins.open", side_effect=AssertionError("NO_FILE_IO")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("NO_NETWORK")), \
                patch("sqlite3.connect", side_effect=AssertionError("NO_DATABASE")):
            self.assertTrue(self.review(payload).supplied_content_match)
            self.assertFalse(self.review(b"{}").supplied_content_match)


if __name__ == "__main__":
    unittest.main()
