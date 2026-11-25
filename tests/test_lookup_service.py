import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lookup_service
from http_client import SourceError


PAYLOAD = {
    "gstin": "27AAACT2727Q1ZW",
    "lgnm": "TATA MOTORS PASSENGER VEHICLES LIMITED",
    "tradeNam": "TATA MOTORS",
    "sts": "Active",
    "rgdt": "01/07/2017",
    "ctb": "Public Limited Company",
    "nba": ["Factory / Manufacturing", "Wholesale Business"],
    "pradr": {"adr": "Pune, Maharashtra", "addr": {"lt": "18.6", "lg": "73.8"}},
    "ctj": "CBIC",
    "stj": "Maharashtra",
}


class MappingTests(unittest.TestCase):
    def test_to_dict_maps_public_fields(self):
        import gst_source

        data = gst_source._to_dict(PAYLOAD)
        self.assertEqual(data["legal_name"], PAYLOAD["lgnm"])
        self.assertEqual(data["trade_name"], PAYLOAD["tradeNam"])
        self.assertEqual(data["principal_place"]["address"], "Pune, Maharashtra")
        self.assertEqual(data["principal_place"]["lat"], "18.6")
        self.assertEqual(data["nature_of_business"], PAYLOAD["nba"])
        self.assertEqual(data["raw"], PAYLOAD)

    def test_to_dict_handles_missing_address(self):
        import gst_source

        data = gst_source._to_dict({"gstin": "27AAACT2727Q1ZW"})
        self.assertIsNone(data["principal_place"]["address"])
        self.assertEqual(data["nature_of_business"], [])


class RetryTests(unittest.TestCase):
    def test_retries_captcha_failures_until_success(self):
        calls = []

        def fake(gstin):
            calls.append(gstin)
            if len(calls) < 3:
                raise SourceError("captcha", "captcha rejected")
            return {"gstin": gstin, "legal_name": "ACME"}

        with mock.patch.object(lookup_service, "_module", return_value=mock.Mock(lookup=fake)):
            with mock.patch.object(lookup_service.time, "sleep", return_value=None):
                data = lookup_service.lookup("27AAACT2727Q1ZW", source="gst", attempts=5)

        self.assertEqual(data["legal_name"], "ACME")
        self.assertEqual(data["attempts"], 3)
        self.assertEqual(data["source"], "gst")

    def test_site_error_breaks_out_early(self):
        calls = []

        def fake(gstin):
            calls.append(gstin)
            raise SourceError("site", "boom")

        with mock.patch.object(lookup_service, "_module", return_value=mock.Mock(lookup=fake)):
            with self.assertRaises(SourceError) as ctx:
                lookup_service.lookup("27AAACT2727Q1ZW", source="ewaybill", attempts=5)

        self.assertEqual(len(calls), 1)
        self.assertEqual(ctx.exception.kind, "failed")

    def test_unknown_gstin_propagates_without_retry_or_failover(self):
        calls = []

        def fake(gstin):
            calls.append(gstin)
            raise SourceError("unknown-gstin", "Invalid GSTIN / UID")

        fallback = mock.Mock()
        modules = {"ewaybill": mock.Mock(lookup=fake), "gst": fallback}
        with mock.patch.object(lookup_service, "_module", side_effect=lambda n: modules[n]):
            with self.assertRaises(SourceError) as ctx:
                lookup_service.lookup("27AAACT2727Q1ZW", source="auto", attempts=5)

        self.assertEqual(ctx.exception.kind, "unknown-gstin")
        self.assertEqual(len(calls), 1)
        fallback.lookup.assert_not_called()

    def test_cache_hit_and_refresh(self):
        lookup_service.clear_cache()
        calls = []

        def fake(gstin):
            calls.append(gstin)
            return {"gstin": gstin, "legal_name": f"ACME-{len(calls)}"}

        with mock.patch.object(lookup_service, "_module", return_value=mock.Mock(lookup=fake)):
            first = lookup_service.lookup("27AAACT2727Q1ZW", source="gst", use_cache=True, cache_ttl=60)
            second = lookup_service.lookup("27AAACT2727Q1ZW", source="gst", use_cache=True, cache_ttl=60)
            refreshed = lookup_service.lookup("27AAACT2727Q1ZW", source="gst", use_cache=True, cache_ttl=60, refresh=True)

        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["legal_name"], "ACME-1")
        self.assertFalse(refreshed["cached"])
        self.assertEqual(refreshed["legal_name"], "ACME-2")
        self.assertEqual(len(calls), 2)

    def test_auto_mode_falls_back_to_second_source(self):
        def broken(gstin):
            raise SourceError("site", "server error page")

        def good(gstin):
            return {"gstin": gstin, "legal_name": "ACME"}

        modules = {"ewaybill": mock.Mock(lookup=broken), "gst": mock.Mock(lookup=good)}
        with mock.patch.object(lookup_service, "_module", side_effect=lambda n: modules[n]):
            data = lookup_service.lookup("27AAACT2727Q1ZW", source="auto", attempts=3)

        self.assertEqual(data["source"], "gst")
        self.assertEqual(data["legal_name"], "ACME")

    def test_bad_source_name(self):
        with self.assertRaises(ValueError):
            lookup_service.lookup("27AAACT2727Q1ZW", source="nope")


if __name__ == "__main__":
    unittest.main()
