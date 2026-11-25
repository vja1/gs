import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ewaybill_source


RESULT_HTML = """
<html><body>
<table class="table">
  <tr><th>GSTIN/UIN</th><th>Legal Name</th><th>Trade Name</th><th>Registration Date</th></tr>
  <tr>
    <td>27AAACT2727Q1ZW</td>
    <td>TATA MOTORS PASSENGER VEHICLES LIMITED</td>
    <td>TATA MOTORS</td>
    <td>01/07/2017</td>
  </tr>
  <tr>
    <th>Constitution of Business</th><td>Public Limited Company</td>
    <th>Principal Place of Business</th><td>Pune, Maharashtra</td>
  </tr>
  <tr>
    <th>Nature of Business Activity</th><td>Factory / Manufacturing, Wholesale Business</td>
    <th>GSTIN Status</th><td>Active</td>
  </tr>
</table>
</body></html>
"""

SINGLE_CELL_HTML = """
<html><body><div>Legal Name : ACME PRIVATE LIMITED</div>
<div>GSTIN Status : Active</div></body></html>
"""


class ParseResultTests(unittest.TestCase):
    def test_maps_label_value_table(self):
        data = ewaybill_source.parse_result(RESULT_HTML)
        self.assertEqual(data["gstin"], "27AAACT2727Q1ZW")
        self.assertEqual(data["legal_name"], "TATA MOTORS PASSENGER VEHICLES LIMITED")
        self.assertEqual(data["trade_name"], "TATA MOTORS")
        self.assertEqual(data["status"], "Active")
        self.assertEqual(data["principal_place"], {"address": "Pune, Maharashtra", "lat": None, "lng": None})
        self.assertEqual(data["nature_of_business"],
                         ["Factory / Manufacturing", "Wholesale Business"])

    def test_single_cell_fallback(self):
        data = ewaybill_source.parse_result(SINGLE_CELL_HTML)
        self.assertEqual(data["legal_name"], "ACME PRIVATE LIMITED")
        self.assertEqual(data["status"], "Active")

    def test_empty_without_result(self):
        self.assertEqual(ewaybill_source.parse_result("<html><body><p>hi</p></body></html>"), {})

    def test_hidden_field_parsing(self):
        html = ('<input name="__VIEWSTATE" value="a" />'
                '<input value="b" name="__VIEWSTATEGENERATOR" />'
                "<input name='__EVENTVALIDATION' value='c' />")
        self.assertEqual(ewaybill_source._hidden(html),
                         {"__VIEWSTATE": "a", "__VIEWSTATEGENERATOR": "b",
                          "__EVENTVALIDATION": "c"})


if __name__ == "__main__":
    unittest.main()
