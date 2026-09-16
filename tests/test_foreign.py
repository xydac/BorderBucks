"""Synthetic threshold and validation regressions, not IRS worked examples."""

import copy
from decimal import Decimal, localcontext
from fractions import Fraction
import json
from pathlib import Path
import unittest

from borderbucks.common import TaxInputError
from borderbucks.foreign import calculate


class ForeignTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(
            (Path(__file__).resolve().parents[1] / "examples" / "foreign.json").read_text()
        )

    def run_document(self, document=None):
        with localcontext() as context:
            context.prec = 60
            return calculate(self.document if document is None else document)

    def one_account(self, maximum, yearend, currency="USD"):
        account = self.document["assets"][0]
        account.update(currency=currency, maximum_local=maximum, yearend_local=yearend)
        self.document["assets"] = [account]
        return account

    def values(self, result):
        return {item["id"]: Decimal(item["value"]) for item in result["facts"]}

    def test_synthetic_example_and_provenance(self):
        result = self.run_document()
        values = self.values(result)
        self.assertEqual(values["foreign.asset.india-bank.maximum_usd"], Decimal("10000"))
        self.assertEqual(values["foreign.fbar.maximum_upper_bound_usd"], Decimal("80000"))
        self.assertEqual(values["foreign.form8938.yearend_usd"], Decimal("45000"))
        self.assertEqual(result["screening"]["fbar"]["status"], "yearend_threshold_crossed")
        self.assertEqual(result["screening"]["form8938"]["status"], "potential_threshold_crossed_review")
        self.assertTrue(result["warnings"])
        self.assertEqual(len(values), len(result["facts"]))
        for item in result["facts"]:
            self.assertEqual(item["unit"], "USD")
            self.assertTrue(item["formula"])
            self.assertTrue(item["source_ids"])
            self.assertIn(item["rule_ids"][0], ("foreign.fx.2025", "foreign.fbar.2025", "foreign.fatca.2025"))
        converted = next(item for item in result["facts"]
                         if item["id"] == "foreign.asset.india-bank.maximum_usd")
        self.assertEqual(converted["source_ids"], ["bank", "fx"])
        aggregate = next(item for item in result["facts"]
                         if item["id"] == "foreign.form8938.yearend_usd")
        self.assertEqual(aggregate["source_ids"], ["bank", "broker", "fx", "inventory"])
        self.assertNotIn("foreign.asset.underlying-pfic.yearend_usd", aggregate["inputs"])
        self.assertEqual(aggregate["inputs"], {
            "foreign.asset.india-bank.yearend_usd": "5000/1",
            "foreign.asset.foreign-brokerage.yearend_usd": "40000/1",
        })

    def test_fbar_strict_unrounded_threshold(self):
        for maximum, yearend, expected in (
            ("9999.999999999999", "0", "known_not_exceeded"),
            ("10000", "10000", "known_not_exceeded"),
            ("10000.000000000001", "10000", "potential_threshold_crossed_review"),
            ("10000.000000000001", "10000.000000000001", "yearend_threshold_crossed"),
        ):
            with self.subTest(maximum=maximum, yearend=yearend):
                self.one_account(maximum, yearend)
                screen = self.run_document()["screening"]["fbar"]
                self.assertEqual(screen["status"], expected)
                self.assertIs(screen["filing_eligibility_determined"], False)

    def test_all_fatca_thresholds_and_strict_edges(self):
        for residence, filing_status, yearend_limit, maximum_limit in (
            ("us", "single", 50000, 75000),
            ("us", "married_separate", 50000, 75000),
            ("us", "married_joint", 100000, 150000),
            ("abroad", "single", 200000, 300000),
            ("abroad", "married_separate", 200000, 300000),
            ("abroad", "married_joint", 400000, 600000),
        ):
            self.document.update(residence=residence, filing_status=filing_status,
                                 qualifying_abroad_confirmed=residence == "abroad")
            for maximum, yearend, expected in (
                (str(maximum_limit), str(yearend_limit), "known_not_exceeded"),
                (f"{maximum_limit}.000000000001", str(yearend_limit), "potential_threshold_crossed_review"),
                (str(maximum_limit), f"{yearend_limit}.000000000001", "yearend_threshold_crossed"),
            ):
                with self.subTest(residence=residence, filing_status=filing_status,
                                  maximum=maximum, yearend=yearend):
                    self.one_account(maximum, yearend)
                    result = self.run_document()
                    self.assertEqual(result["screening"]["form8938"]["status"], expected)
                    values = self.values(result)
                    self.assertEqual(values["foreign.form8938.yearend_threshold_usd"], yearend_limit)
                    self.assertEqual(values["foreign.form8938.maximum_threshold_usd"], maximum_limit)

    def test_sum_of_noncontemporaneous_maxima_is_only_potential(self):
        account = self.one_account("6000", "4000")
        second = copy.deepcopy(account)
        second["id"] = "other-account"
        self.document["assets"].append(second)
        result = self.run_document()
        self.assertEqual(result["screening"]["fbar"]["status"], "potential_threshold_crossed_review")
        self.assertEqual(self.values(result)["foreign.fbar.yearend_usd"], 8000)

    def test_separate_inclusion_flags_and_direct_assets(self):
        asset = self.one_account("80000", "60000")
        asset.update(asset_type="asset", include_fbar=False)
        result = self.run_document()
        self.assertEqual(result["screening"]["fbar"]["status"], "known_not_exceeded")
        self.assertEqual(result["screening"]["form8938"]["status"], "yearend_threshold_crossed")
        asset.update(asset_type="account", include_fbar=True, include_form8938=False)
        result = self.run_document()
        self.assertEqual(self.values(result)["foreign.form8938.maximum_upper_bound_usd"], 0)
        self.assertEqual(result["screening"]["fbar"]["status"], "yearend_threshold_crossed")

    def test_fx_direction_and_no_rounding_before_comparison(self):
        self.one_account("800000.000000000001", "800000", currency="INR")
        result = self.run_document()
        self.assertEqual(self.values(result)["foreign.fbar.maximum_upper_bound_usd"],
                         Decimal("10000.0000000000000125"))
        self.assertEqual(result["screening"]["fbar"]["status"], "potential_threshold_crossed_review")

    def test_empty_confirmed_inventory(self):
        self.document.update(assets=[], fx_rates=[])
        result = self.run_document()
        self.assertEqual(self.values(result)["foreign.fbar.maximum_upper_bound_usd"], 0)
        self.assertEqual(result["screening"]["form8938"]["status"], "known_not_exceeded")

    def test_recurring_fx_exact_thresholds_and_nearby_crossings(self):
        for regime, yearend_limit, maximum_limit in (
            ("fbar", 10000, 10000),
            ("form8938", 50000, 75000),
        ):
            for maximum_delta, yearend_delta, status in (
                ("0", "0", "known_not_exceeded"),
                ("-0.000000000001", "-0.000000000001", "known_not_exceeded"),
                ("0.000000000001", "0", "potential_threshold_crossed_review"),
                ("0.000000000001", "0.000000000001", "yearend_threshold_crossed"),
            ):
                with self.subTest(regime=regime, maximum_delta=maximum_delta, yearend_delta=yearend_delta):
                    # Eighteen INR 50,000 accounts at 90 INR/USD total exactly USD 10,000.
                    # Scale the same recurring quotients to the two Form 8938 thresholds.
                    account = self.one_account(str(maximum_limit * 5), str(yearend_limit * 5), "INR")
                    self.document["fx_rates"][0]["local_per_usd"] = "90"
                    self.document["assets"] = [dict(account, id=f"synthetic-{i}") for i in range(18)]
                    with localcontext() as context:
                        context.prec = 60
                        self.document["assets"][0].update(
                            maximum_local=str(Decimal(maximum_limit * 5) + Decimal(maximum_delta)),
                            yearend_local=str(Decimal(yearend_limit * 5) + Decimal(yearend_delta)))
                    result = self.run_document()
                    self.assertEqual(result["screening"][regime]["status"], status)
                    facts = {item["id"]: item for item in result["facts"]}
                    for period, suffix, limit, delta in (
                        ("maximum", "maximum_upper_bound_usd", maximum_limit, maximum_delta),
                        ("yearend", "yearend_usd", yearend_limit, yearend_delta),
                    ):
                        aggregate = facts[f"foreign.{regime}.{suffix}"]
                        exact_total = Fraction(limit) + Fraction(delta) / 90
                        self.assertEqual(len(aggregate["inputs"]), 18)
                        self.assertEqual(sum(Fraction(value) for value in aggregate["inputs"].values()), exact_total)
                        for asset in self.document["assets"]:
                            operand = aggregate["inputs"][f"foreign.asset.{asset['id']}.{period}_usd"]
                            self.assertIsInstance(operand, str)
                            self.assertIn("/", operand)
                            self.assertEqual(Fraction(operand), Fraction(asset[f"{period}_local"]) / 90)
                        with localcontext() as context:
                            context.prec = 60
                            expected = Decimal(exact_total.numerator) / Decimal(exact_total.denominator)
                        self.assertEqual(Decimal(aggregate["value"]), expected)

    def test_same_valuation_confirmation_must_be_explicit_true(self):
        field = "same_valuation_for_both_regimes_confirmed"
        for filing_status in ("single", "married_separate", "married_joint"):
            for value in (False, 0, 1, "true", "false", None, [], {}):
                document = copy.deepcopy(self.document)
                document.update(filing_status=filing_status)
                document[field] = value
                with self.subTest(filing_status=filing_status, value=value):
                    with self.assertRaisesRegex(TaxInputError, field):
                        self.run_document(document)
            document = copy.deepcopy(self.document)
            document.update(filing_status=filing_status)
            del document[field]
            with self.subTest(filing_status=filing_status, missing=True):
                with self.assertRaisesRegex(TaxInputError, field):
                    self.run_document(document)

    def test_invalid_fields_and_ambiguous_booleans(self):
        invalid = (
            (("schema_version",), 1), (("tax_year",), "2025"), (("tax_year",), 2025.0),
            (("tax_year",), True), (("kind",), "pfic"), (("filing_status",), "head_of_household"),
            (("residence",), "india"), (("qualifying_abroad_confirmed",), True),
            (("qualifying_abroad_confirmed",), 0), (("qualifying_abroad_confirmed",), "false"),
            (("inventory_complete",), False), (("inventory_complete",), 1),
            (("inventory_complete",), "true"), (("no_double_counting_confirmed",), False),
            (("no_double_counting_confirmed",), 1), (("no_double_counting_confirmed",), "true"),
            (("sources",), {}), (("sources", 0, "locator"), ""), (("source_ids",), []),
            (("source_ids",), ["inventory", "inventory"]), (("source_ids",), "inventory"),
            (("fx_rates",), {}), (("assets",), {}),
            (("fx_rates", 0, "currency"), "EUR"), (("fx_rates", 0, "date"), "2025-12-30"),
            (("fx_rates", 0, "local_per_usd"), "0"), (("fx_rates", 0, "local_per_usd"), "-80"),
            (("fx_rates", 0, "local_per_usd"), 80), (("fx_rates", 0, "source_ids"), []),
            (("fx_rates", 1, "local_per_usd"), "2"),
            (("assets", 0, "currency"), "EUR"), (("assets", 0, "asset_type"), "mutual_fund"),
            (("assets", 0, "asset_type"), "asset"), (("assets", 0, "id"), ""),
            (("assets", 0, "yearend_local"), "800001"),
            (("assets", 0, "include_fbar"), 1), (("assets", 0, "include_form8938"), "false"),
            (("assets", 0, "include_fbar"), None), (("assets", 0, "source_ids"), []),
            (("assets", 2, "included_in_account_id"), "missing"),
            (("assets", 2, "included_in_account_id"), "underlying-pfic"),
            (("assets", 2, "included_in_account_id"), None),
            (("assets", 2, "include_form8938"), True),
            (("assets", 1, "included_in_account_id"), "india-bank"),
        )
        for path, value in invalid:
            with self.subTest(path=path, value=value):
                document = copy.deepcopy(self.document)
                target = document
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(TaxInputError):
                    self.run_document(document)

    def test_numbers_fail_closed(self):
        for field in ("maximum_local", "yearend_local"):
            for value in (1, 1.5, True, None, "NaN", "Infinity", "1e3", "-1", " 1", "+1",
                          "1,000", "0.0000000000001", "1000000000000000000"):
                with self.subTest(field=field, value=value):
                    document = copy.deepcopy(self.document)
                    document["assets"][0][field] = value
                    with self.assertRaises(TaxInputError):
                        self.run_document(document)

    def test_unknown_and_missing_fields_at_every_object_level(self):
        for path in ((), ("sources", 0), ("fx_rates", 0), ("assets", 0)):
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

    def test_duplicate_ids_and_currencies(self):
        for field in ("sources", "fx_rates", "assets"):
            document = copy.deepcopy(self.document)
            document[field].append(copy.deepcopy(document[field][0]))
            with self.subTest(field=field), self.assertRaises(TaxInputError):
                self.run_document(document)

    def test_missing_fx_and_unconfirmed_abroad(self):
        self.document["fx_rates"] = self.document["fx_rates"][1:]
        with self.assertRaisesRegex(TaxInputError, "explicit yearend FX"):
            self.run_document()
        self.setUp()
        self.document["residence"] = "abroad"
        with self.assertRaisesRegex(TaxInputError, "qualifying abroad"):
            self.run_document()

    def test_does_not_mutate_input(self):
        original = copy.deepcopy(self.document)
        self.run_document()
        self.assertEqual(self.document, original)


if __name__ == "__main__":
    unittest.main()
