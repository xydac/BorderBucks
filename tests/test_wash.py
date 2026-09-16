"""Verified P550 numbers and separately identified synthetic regressions."""

import copy
from datetime import date, timedelta
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import json
from pathlib import Path
import unittest

from borderbucks.common import TaxInputError
from borderbucks.wash import calculate


ROOT = Path(__file__).resolve().parents[1]


def run(document):
    with localcontext(Context(prec=60, rounding=ROUND_HALF_EVEN)):
        return calculate(document)


def values(result):
    return {item["id"]: item["value"] for item in result["facts"]}


def synthetic():
    return json.loads((ROOT / "examples/wash.json").read_text())


class OfficialWashTests(unittest.TestCase):
    def test_p550_verified_example(self):
        fixture = json.loads((ROOT / "fixtures/official/p550-wash.json").read_text())
        self.assertEqual(fixture["provenance"]["url"],
                         "https://www.irs.gov/pub/irs-prior/p550--2025.pdf")
        self.assertIn("$1,050", fixture["provenance"]["quote"])
        self.assertTrue(fixture["provenance"]["adapted"])
        self.assertIsNone(fixture["provenance"]["original_years"])
        actual = values(run(fixture["document"]))
        for group in ("official_expected_facts", "derived_expected_facts"):
            for key, expected in fixture[group].items():
                with self.subTest(key=key):
                    self.assertEqual(actual[key], expected)


class SyntheticWashTests(unittest.TestCase):
    def test_example_fees_partial_and_ira(self):
        actual = values(run(synthetic()))
        for key, expected in {
            "wash.total_loss": "500", "wash.disallowed_loss": "300",
            "wash.deferred_loss": "200", "wash.permanent_loss": "100",
            "wash.allowed_loss": "200", "wash.recognized_gain": "-200",
            "replacement.taxable-buy.adjusted_basis": "820",
            "replacement.ira-buy.basis_increase": "0",
            "replacement.ira-buy.carried_holding_days": "0",
        }.items():
            self.assertEqual(actual[key], expected, key)
        self.assertNotIn("replacement.ira-buy.adjusted_basis", actual)

    def test_inclusive_window_30_and_exclusive_31_both_sides(self):
        for offset, expected in [(-31, "0"), (-30, "200"), (0, "200"),
                                 (30, "200"), (31, "0")]:
            document = synthetic()
            document["scope"].update(reviewed_from="2025-11-19", reviewed_through="2026-01-20")
            document["replacements"] = document["replacements"][:1]
            document["replacements"][0]["acquired"] = (
                date(2025, 12, 20) + timedelta(days=offset)).isoformat()
            with self.subTest(offset=offset):
                self.assertEqual(values(run(document))["wash.disallowed_loss"], expected)

    def test_complete_window_requires_january_and_start(self):
        for changes in [{"reviewed_through": "2025-12-31"},
                        {"reviewed_through": "2026-01-18"},
                        {"reviewed_from": "2025-11-21"}]:
            document = synthetic()
            document["scope"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(TaxInputError):
                run(document)

    def test_chronological_matching_partial_full_lot_basis(self):
        document = synthetic()
        first, second = document["replacements"]
        first.update(shares="75", purchase_basis="600")
        second.update(shares="75", purchase_basis="900", account_type="taxable")
        original = copy.deepcopy(document)
        result = run(document)
        document["replacements"].reverse()
        self.assertEqual(result, run(document))
        actual = values(result)
        self.assertEqual(actual["replacement.taxable-buy.matched_shares"], "75")
        self.assertEqual(actual["replacement.ira-buy.matched_shares"], "25")
        self.assertEqual(actual["replacement.ira-buy.adjusted_basis"], "1025")
        self.assertEqual(actual["wash.disallowed_loss"], "500")
        self.assertEqual(actual["wash.allowed_loss"], "0")
        self.assertEqual(result["replacements"][1]["unmatched_shares"], "50")
        self.assertEqual(original["replacements"][1]["shares"], "75")

    def test_same_day_order_is_explicit_not_id_or_list_order(self):
        document = synthetic()
        first, second = document["replacements"]
        first.update(shares="100", acquisition_order=2)
        second.update(shares="100", acquired=first["acquired"], acquisition_order=1)
        actual = values(run(document))
        self.assertEqual(actual["wash.permanent_loss"], "500")
        self.assertEqual(actual["wash.deferred_loss"], "0")
        second["acquisition_order"] = 2
        with self.assertRaisesRegex(TaxInputError, "ambiguous"):
            run(document)

    def test_fractional_shares(self):
        document = synthetic()
        document["sale"].update(shares="1.25", basis="20", proceeds="10", fees="0")
        document["replacements"][0].update(shares="0.4", purchase_basis="4")
        document["replacements"][1].update(shares="0.35", purchase_basis="3.5")
        actual = values(run(document))
        self.assertEqual(actual["wash.disallowed_loss"], "6")
        self.assertEqual(actual["wash.permanent_loss"], "2.8")
        self.assertEqual(actual["replacement.taxable-buy.adjusted_basis"], "7.2")

    def test_no_replacements_or_only_outside_window(self):
        document = synthetic()
        for lots in ([], [dict(document["replacements"][0], acquired="2025-11-19")]):
            document["replacements"] = lots
            actual = values(run(document))
            self.assertEqual(actual["wash.allowed_loss"], "500")
            self.assertEqual(actual["wash.disallowed_loss"], "0")

    def test_holding_period_is_carried_only_for_matched_taxable_shares(self):
        document = synthetic()
        document["replacements"][0]["shares"] = "120"
        result = run(document)
        carry = result["replacements"][0]["holding_period_carry"]
        self.assertEqual(carry["applies_to_shares"], "100")
        self.assertEqual(carry["sold_lot_acquired"], "2024-06-01")
        self.assertEqual(carry["days"], str((date(2025, 12, 20) - date(2024, 6, 1)).days))
        self.assertEqual(result["replacements"][0]["acquired"], "2025-12-22")
        self.assertEqual(result["replacements"][0]["unmatched_shares"], "20")
        self.assertEqual(result["replacements"][1]["holding_period_carry"]["applies_to_shares"], "0")

    def test_repeating_divisions_exact_fractions_and_residual_conservation(self):
        for count in (3, 7, 97):
            document = synthetic()
            document["sale"].update(shares=str(count), basis="1", proceeds="0", fees="0")
            template = document["replacements"][0]
            document["replacements"] = [dict(template, lot_id=f"r{i}", shares="1",
                                              acquisition_order=i + 1,
                                              account_type="ira" if i % 2 else "taxable")
                                        for i in range(count)]
            result = run(document)
            actual = values(result)
            amounts = [Fraction(item["value"]) for item in result["facts"]
                       if item["id"].startswith("replacement.")
                       and item["id"].endswith(".disallowed_loss")]
            self.assertEqual(sum(amounts), 1)
            self.assertEqual(actual["wash.allowed_loss"], "0")
            self.assertEqual(Fraction(actual["wash.deferred_loss"]) +
                             Fraction(actual["wash.permanent_loss"]), 1)
            for lot, amount in zip(result["replacements"], amounts):
                exact = lot["exact_loss_fraction"]
                self.assertEqual(Fraction(int(exact["numerator"]), int(exact["denominator"])),
                                 Fraction(1, count))
                self.assertLess(abs(amount - Fraction(1, count)), Fraction(1, 10 ** 40))
            document["replacements"].pop()
            partial = values(run(document))
            self.assertLessEqual(Fraction(partial["wash.disallowed_loss"]), Fraction(count - 1, count))
            self.assertEqual(Fraction(partial["wash.disallowed_loss"]) +
                             Fraction(partial["wash.allowed_loss"]), 1)

    def test_large_basis_keeps_tiny_allocation_at_context_60(self):
        document = synthetic()
        document["sale"].update(shares="3", basis="0.000000000001", proceeds="0", fees="0")
        document["replacements"] = [dict(document["replacements"][0], shares="1",
                                          purchase_basis="999999999999999999.999999999999")]
        with localcontext() as ambient:
            ambient.prec = 3
            actual = values(run(document))
            self.assertEqual(ambient.prec, 3)
        self.assertEqual(Fraction(actual["replacement.taxable-buy.adjusted_basis"]) -
                         Fraction(document["replacements"][0]["purchase_basis"]),
                         Fraction(actual["wash.disallowed_loss"]))

    def test_unknown_and_missing_fields_every_level(self):
        for section in ("top", "sources", "scope", "sale", "replacements"):
            base = synthetic()
            target = base if section == "top" else base[section]
            if isinstance(target, list):
                target = target[0]
            for key in [None] + list(target):
                document = copy.deepcopy(base)
                changed = document if section == "top" else document[section]
                if isinstance(changed, list):
                    changed = changed[0]
                if key is None:
                    changed["unexpected"] = True
                else:
                    del changed[key]
                with self.subTest(section=section, key=key), self.assertRaises(TaxInputError):
                    run(document)

    def test_assertions_are_literal_true_and_not_missing_defaults(self):
        for section in ("scope", "sale", "replacements"):
            base = synthetic()
            target = base[section][0] if section == "replacements" else base[section]
            for key, value in target.items():
                if value is not True:
                    continue
                for invalid in (False, 1, "true", None, [], {}):
                    document = copy.deepcopy(base)
                    changed = document[section][0] if section == "replacements" else document[section]
                    changed[key] = invalid
                    with self.subTest(section=section, key=key, invalid=invalid), self.assertRaises(TaxInputError):
                        run(document)

    def test_invalid_numbers_on_all_financial_fields(self):
        for section, keys in (("sale", ("shares", "basis", "proceeds", "fees")),
                              ("replacements", ("shares", "purchase_basis"))):
            for key in keys:
                for invalid in (1, 1.5, True, "NaN", "Infinity", "1e2", "-1",
                                "1000000000000000000", "0.1234567890123"):
                    document = synthetic()
                    target = document[section][0] if section == "replacements" else document[section]
                    target[key] = invalid
                    with self.subTest(section=section, key=key, invalid=invalid), self.assertRaises(TaxInputError):
                        run(document)

    def test_reject_bad_dates_accounts_quantities_and_reuse(self):
        cases = [
            ("sale", "date", "2024-12-20"), ("sale", "date", "2026-01-01"),
            ("sale", "date", "2025-02-29"), ("sale", "acquired", "2025-12-21"),
            ("sale", "date", "2025-1-01"), ("sale", "acquired", 20240101),
            ("sale", "account_type", "ira"), ("sale", "shares", "0"),
            ("sale", "basis", "0"), ("sale", "proceeds", "3000"),
            ("sale", "proceeds", "2005"), ("sale", "fees", "2000"),
            ("replacements", "shares", "0"), ("replacements", "lot_id", "sold"),
            ("replacements", "acquired", "2026-01-20"),
            ("replacements", "account_type", "401k"),
            ("replacements", "account_type", []),
        ]
        cases += [("replacements", "acquisition_order", value)
                  for value in (True, "1", 0, -1, 10001, None)]
        for section, key, invalid in cases:
            document = synthetic()
            target = document[section][0] if section == "replacements" else document[section]
            target[key] = invalid
            with self.subTest(section=section, key=key, invalid=invalid), self.assertRaises(TaxInputError):
                run(document)
        document = synthetic()
        document["replacements"].append(copy.deepcopy(document["replacements"][0]))
        with self.assertRaises(TaxInputError):
            run(document)

    def test_invalid_top_shapes_and_multi_sale_chain(self):
        for key, invalid in [("schema_version", 1), ("tax_year", "2025"),
                             ("tax_year", 2025.0), ("kind", "equity"),
                             ("sources", {}), ("scope", []), ("sale", []),
                             ("replacements", {}), ("replacements", [None])]:
            document = synthetic()
            document[key] = invalid
            with self.subTest(key=key, invalid=invalid), self.assertRaises(TaxInputError):
                run(document)
        document = synthetic()
        document["sales"] = [document["sale"], document["sale"]]
        with self.assertRaises(TaxInputError):
            run(document)

    def test_identity_is_explicit_not_guessed_from_labels(self):
        document = synthetic()
        document["replacements"][0]["security"] = "Different descriptive label, user confirms identity"
        self.assertEqual(values(run(document))["wash.disallowed_loss"], "300")
        document["replacements"][0]["substantially_identical"] = False
        with self.assertRaises(TaxInputError):
            run(document)

    def test_source_id_shapes_and_dependency_provenance(self):
        for section in ("scope", "sale", "replacements"):
            for invalid in ([], "synthetic", [1], ["synthetic", "synthetic"]):
                document = synthetic()
                target = document[section][0] if section == "replacements" else document[section]
                target["source_ids"] = invalid
                with self.subTest(section=section, invalid=invalid), self.assertRaises(TaxInputError):
                    run(document)
        document = synthetic()
        document["sources"].append({"id": "review", "document": "Synthetic review", "locator": "scope"})
        document["scope"]["source_ids"] = ["review"]
        for item in run(document)["facts"]:
            self.assertEqual(item["source_ids"], ["review", "synthetic"])
            self.assertTrue(item["formula"])
            self.assertTrue(item["inputs"])
            self.assertIn(item["rule_ids"][0], ("wash.sale.2025", "wash.ira.2025", "wash.holding.2025"))
            Decimal(item["value"])

    def test_pure_repeatable_calculation(self):
        document = synthetic()
        before = copy.deepcopy(document)
        result = run(document)
        self.assertEqual(document, before)
        self.assertEqual(run(document), result)
        scenario = copy.deepcopy(document)
        scenario["replacements"] = []
        self.assertNotEqual(run(scenario), result)
        self.assertIn("not filing-ready", " ".join(result["warnings"]))


if __name__ == "__main__":
    unittest.main()
