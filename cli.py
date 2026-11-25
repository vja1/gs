"""Command line lookup helper.

    python cli.py 27AAACT2727Q1ZW
    python cli.py 27AAACT2727Q1ZW --source gst --attempts 12
"""

import argparse
import json
import sys

import gstin_utils
import lookup_service
from http_client import SourceError


def _format_place(place) -> str | None:
    if isinstance(place, dict):
        return place.get("address")
    if isinstance(place, str):
        return place or None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Look up GSTIN taxpayer details")
    parser.add_argument("gstin")
    parser.add_argument("--source", default="auto", choices=("auto", "ewaybill", "gst"))
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--raw", action="store_true", help="include raw portal payload if available")
    parser.add_argument("--quiet", action="store_true", help="print only the JSON body")
    args = parser.parse_args()

    valid, reason = gstin_utils.validate(args.gstin)
    if not valid:
        print("invalid GSTIN: %s" % reason)
        return 2

    gstin = gstin_utils.normalise(args.gstin)
    try:
        data = lookup_service.lookup(gstin, source=args.source, attempts=args.attempts)
    except SourceError as exc:
        print("lookup failed (%s)" % exc.kind)
        if exc.detail:
            print(exc.detail)
        return 1

    if not args.quiet:
        print("GSTIN      :", gstin)
        print("Source     :", data.get("source"), "after", data.get("attempts"), "attempt(s)")
        for key in ("legal_name", "trade_name", "status", "registration_date", "constitution"):
            if data.get(key):
                print("%-11s:" % key.replace("_", " ").title(), data[key])
        address = _format_place(data.get("principal_place"))
        if address:
            print("Address    :", address)
        if data.get("nature_of_business"):
            print("Business   :", ", ".join(data["nature_of_business"]))

    output = {
        k: v for k, v in data.items()
        if not k.startswith("_") and (args.raw or k != "raw")
    }
    print(json.dumps(output, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
