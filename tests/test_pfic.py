"""Synthetic section 1296 regressions, not official worked examples."""

import copy
from decimal import Decimal, localcontext
import json
from pathlib import Path
import unittest

from borderbucks.common import TaxInputError
from borderbucks.pfic import calculate


class PficTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(
            (Path(__file__).resolve().parents[1] / "examples" / "pfic.json").read_text()
        )

    def run_document(self, document=None):
        with localcontext() as context:
            context.prec = 60
            return calculate(self.document if document is None else document)

    def values(self, result):
        return {item["id"]: Decimal(item["value"]) for item in result["facts"]}

    def test_synthetic_example_limits_loss_and_preserves_basis(self):
        result = self.run_document()
        values = self.values(result)
        prefix = "pfic.synthetic-fund."
        self.assertEqual(values[prefix + "fmv_change_usd"], -3000)
        self.assertEqual(values[prefix + "ordinary_income_usd"], 0)
        self.assertEqual(values[prefix + "deductible_ordinary_loss_usd"], 1000)
        self.assertEqual(values[prefix + "unallowed_loss_usd"], 2000)
        self.assertEqual(values[prefix + "ending_basis_usd"], 9000)
        self.assertEqual(values[prefix + "ending_unreversed_inclusions_usd"], 0)
        self.assertEqual(result["method"], "mtm")
        self.assertTrue(result["warnings"])
        self.assertEqual(len(values), len(result["facts"]))
        for item in result["facts"]:
            self.assertEqual(item["source_ids"], ["election", "history", "position"])
            self.assertEqual(item["rule_ids"], ["pfic.mtm.2025"])
            self.assertEqual(item["unit"], "USD")
            self.assertTrue(item["formula"])
            self.assertTrue(item["inputs"])

    def test_gain_loss_zero_and_exact_cap_edges(self):
        for basis, fmv, prior, income, deduction, ending_basis, ending_prior in (
            ("10000", "13000", "1000", "3000", "0", "13000", "4000"),
            ("10000", "7000", "0", "0", "0", "10000", "0"),
            ("10000", "7000", "3000", "0", "3000", "7000", "0"),
            ("10000", "7000", "4000", "0", "3000", "7000", "1000"),
            ("10000", "10000", "1000", "0", "0", "10000", "1000"),
            ("0", "0", "0", "0", "0", "0", "0"),
            ("0", "1", "0", "1", "0", "1", "1"),
            ("10000", "0", "1000", "0", "1000", "9000", "0"),
            ("10000", "9999.999999999999", "1", "0", "0.000000000001", "9999.999999999999", "0.999999999999"),
            ("10000", "10000.000000000001", "0", "0.000000000001", "0", "10000.000000000001", "0.000000000001"),
            ("10000", "7000", "2999.999999999999", "0", "2999.999999999999", "7000.000000000001", "0"),
        ):
            with self.subTest(basis=basis, fmv=fmv, prior=prior):
                self.document["holdings"][0].update(
                    adjusted_basis_usd=basis, yearend_fmv_usd=fmv, prior_unreversed_inclusions_usd=prior)
                values = self.values(self.run_document())
                for field, expected in (
                    ("ordinary_income_usd", income), ("deductible_ordinary_loss_usd", deduction),
                    ("ending_basis_usd", ending_basis), ("ending_unreversed_inclusions_usd", ending_prior),
                ):
                    self.assertEqual(values[f"pfic.synthetic-fund.{field}"], Decimal(expected))

    def test_do_not_share_unreversed_inclusions_between_holdings(self):
        first = self.document["holdings"][0]
        first.update(yearend_fmv_usd="7000", prior_unreversed_inclusions_usd="0")
        second = copy.deepcopy(first)
        second.update(id="second-fund", yearend_fmv_usd="13000", prior_unreversed_inclusions_usd="5000")
        self.document["holdings"].append(second)
        values = self.values(self.run_document())
        self.assertEqual(values["pfic.synthetic-fund.deductible_ordinary_loss_usd"], 0)
        self.assertEqual(values["pfic.synthetic-fund.ending_basis_usd"], 10000)
        self.assertEqual(values["pfic.second-fund.ending_unreversed_inclusions_usd"], 8000)

    def test_election_from_acquisition(self):
        self.document["holdings"][0]["eligibility"]["election_start"] = "acquisition"
        self.assertEqual(self.run_document()["method"], "mtm")

    def test_every_eligibility_confirmation_is_explicit_true(self):
        eligibility = self.document["holdings"][0]["eligibility"]
        for field in eligibility:
            if field == "election_start":
                continue
            for value in (False, 0, 1, "true", "false", None, [], {}):
                document = copy.deepcopy(self.document)
                document["holdings"][0]["eligibility"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(TaxInputError):
                    self.run_document(document)

    def test_unsupported_elections_and_methods(self):
        for method in ("1291", "default1291", "section1291", "qef", "", None):
            document = copy.deepcopy(self.document)
            document["method"] = method
            with self.subTest(method=method), self.assertRaisesRegex(TaxInputError, "section 1291.*not implemented"):
                self.run_document(document)
        for start in ("current_year", "late", "purged", "", True, None):
            document = copy.deepcopy(self.document)
            document["holdings"][0]["eligibility"]["election_start"] = start
            with self.subTest(start=start), self.assertRaisesRegex(TaxInputError, "late/tainted"):
                self.run_document(document)

    def test_financial_numbers_must_be_nonnegative_decimal_strings(self):
        for field in ("adjusted_basis_usd", "yearend_fmv_usd", "prior_unreversed_inclusions_usd"):
            for value in (1, 1.5, True, None, "-1", "NaN", "Infinity", "1e3", "1,000", "+1", " 1",
                          "0.0000000000001", "1000000000000000000"):
                document = copy.deepcopy(self.document)
                document["holdings"][0][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(TaxInputError):
                    self.run_document(document)

    def test_unknown_and_missing_fields_at_every_object_level(self):
        for path in ((), ("sources", 0), ("holdings", 0), ("holdings", 0, "eligibility")):
            document = copy.deepcopy(self.document)
            target = document
            for key in path:
                target = target[key]
            target["unexpected"] = "no"
            with self.subTest(path=path, unknown=True), self.assertRaises(TaxInputError):
                self.run_document(document)
            del target["unexpected"]
            for field in list(target):
                value = target.pop(field)
                with self.subTest(path=path, missing=field), self.assertRaises(TaxInputError):
                    self.run_document(document)
                target[field] = value

    def test_duplicate_holdings_and_sources(self):
        for field in ("holdings", "sources"):
            document = copy.deepcopy(self.document)
            document[field].append(copy.deepcopy(document[field][0]))
            with self.subTest(field=field), self.assertRaisesRegex(TaxInputError, "duplicate"):
                self.run_document(document)

    def test_invalid_shared_fields_and_source_ids(self):
        invalid = (
            (("schema_version",), 1), (("tax_year",), "2025"), (("tax_year",), 2025.0),
            (("tax_year",), True), (("kind",), "foreign"), (("sources",), {}),
            (("sources", 0, "document"), ""), (("holdings",), []), (("holdings",), {}),
            (("holdings", 0, "id"), ""), (("holdings", 0, "description"), "\n"),
            (("holdings", 0, "source_ids"), []), (("holdings", 0, "source_ids"), "position"),
            (("holdings", 0, "source_ids"), ["position", "position"]),
            (("holdings", 0, "source_ids"), [1]), (("holdings", 0, "eligibility"), []),
        )
        for path, value in invalid:
            document = copy.deepcopy(self.document)
            target = document
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(TaxInputError):
                self.run_document(document)

    def test_large_values_retain_fractional_digits_in_engine_context(self):
        self.document["holdings"][0].update(
            adjusted_basis_usd="999999999999999998.999999999999",
            yearend_fmv_usd="999999999999999999.000000000001",
            prior_unreversed_inclusions_usd="0")
        values = self.values(self.run_document())
        self.assertEqual(values["pfic.synthetic-fund.ordinary_income_usd"], Decimal("0.000000000002"))
        self.assertEqual(values["pfic.synthetic-fund.ending_basis_usd"], Decimal("999999999999999999.000000000001"))

    def test_does_not_mutate_input(self):
        original = copy.deepcopy(self.document)
        self.run_document()
        self.assertEqual(self.document, original)


if __name__ == "__main__":
    unittest.main()
