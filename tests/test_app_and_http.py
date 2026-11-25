import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as flask_app
import cli
import http_client
import lookup_service
from http_client import SourceError


class AppTests(unittest.TestCase):
    def setUp(self):
        lookup_service.clear_cache()
        with flask_app._rate_lock:
            flask_app._rate_buckets.clear()
        self.client = flask_app.app.test_client()

    def test_health_and_index(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})

        idx = self.client.get("/")
        self.assertEqual(idx.status_code, 200)
        self.assertEqual(idx.get_json()["service"], "gstin-lookup")

    def test_invalid_gstin_returns_400(self):
        resp = self.client.get("/lookup/INVALID")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "invalid_gstin")

    def test_unknown_gstin_returns_404(self):
        with mock.patch.object(
            lookup_service,
            "lookup",
            side_effect=SourceError("unknown-gstin", "GSTIN does not exist"),
        ):
            resp = self.client.get("/lookup/27AAACT2727Q1ZW")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"], "unknown-gstin")

    def test_strips_internal_and_raw_fields_by_default(self):
        sample = {
            "gstin": "27AAACT2727Q1ZW",
            "legal_name": "ACME",
            "source": "gst",
            "attempts": 2,
            "cached": False,
            "_captcha": "123456",
            "raw": {"lgnm": "ACME"},
        }
        with mock.patch.object(lookup_service, "lookup", return_value=dict(sample)):
            resp = self.client.get("/lookup/27AAACT2727Q1ZW")
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["source"], "gst")
        self.assertEqual(body["attempts"], 2)
        self.assertNotIn("_captcha", body["data"])
        self.assertNotIn("raw", body["data"])
        self.assertNotIn("source", body["data"])

        with mock.patch.object(lookup_service, "lookup", return_value=dict(sample)):
            resp_raw = self.client.get("/lookup/27AAACT2727Q1ZW?raw=1")
        self.assertEqual(resp_raw.get_json()["data"]["raw"], {"lgnm": "ACME"})

    def test_api_key_protection(self):
        with mock.patch.dict(os.environ, {"API_KEY": "secret123"}):
            unauth = self.client.get("/lookup/27AAACT2727Q1ZW")
            self.assertEqual(unauth.status_code, 401)
            health = self.client.get("/health")
            self.assertEqual(health.status_code, 200)
            with mock.patch.object(
                lookup_service,
                "lookup",
                return_value={"gstin": "27AAACT2727Q1ZW", "source": "gst", "attempts": 1, "cached": False},
            ):
                auth = self.client.get("/lookup/27AAACT2727Q1ZW", headers={"X-API-Key": "secret123"})
            self.assertEqual(auth.status_code, 200)

    def test_rate_limiting(self):
        with mock.patch.dict(os.environ, {"RATE_LIMIT_PER_MIN": "2"}):
            with mock.patch.object(
                lookup_service,
                "lookup",
                return_value={"gstin": "27AAACT2727Q1ZW", "source": "gst", "attempts": 1, "cached": False},
            ):
                self.assertEqual(self.client.get("/lookup/27AAACT2727Q1ZW").status_code, 200)
                self.assertEqual(self.client.get("/lookup/27AAACT2727Q1ZW").status_code, 200)
                limited = self.client.get("/lookup/27AAACT2727Q1ZW")
                self.assertEqual(limited.status_code, 429)
                self.assertEqual(limited.get_json()["error"], "rate_limited")


class CliAndHttpTests(unittest.TestCase):
    def test_cli_format_place_handles_dict_and_str(self):
        self.assertEqual(cli._format_place({"address": "Pune"}), "Pune")
        self.assertEqual(cli._format_place("Pune"), "Pune")
        self.assertIsNone(cli._format_place(None))

    def test_http_client_retries_5xx_then_succeeds(self):
        resp_503 = mock.Mock(status_code=503)
        resp_200 = mock.Mock(status_code=200)
        session = mock.Mock()
        session.request.side_effect = [resp_503, resp_200]
        with mock.patch.object(http_client.time, "sleep", return_value=None):
            result = http_client.request(session, "GET", "https://example.invalid")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(session.request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
