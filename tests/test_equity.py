"""Official numeric examples are kept distinct from synthetic boundary cases."""

import copy
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import json
from pathlib import Path
import unittest

from borderbucks.common import TaxInputError
from borderbucks.equity import calculate


ROOT = Path(__file__).resolve().parents[1]


def run(document):
    with localcontext(Context(prec=60, rounding=ROUND_HALF_EVEN)):
        return calculate(document)


def values(result):
    return {item["id"]: item["value"] for item in result["facts"]}


def synthetic(award="RSU"):
    lot = {
        "lot_id": "lot", "award_type": award, "acquired": "2024-01-15",
        "shares": "100", "cost_per_share": "0" if award == "RSU" else "20",
        "shares_are_gross": True, "all_disposals_included": True,
        "unadjusted_basis": True, "unrestricted_at_acquisition": True,
        "source_ids": ["award"],
    }
    if award in ("RSU", "NSO"):
        lot.update(compensation_per_share="23" if award == "RSU" else "3",
                   wages_included=True)
    if award != "RSU":
        lot.update(grant="2022-07-15", exercise_fmv_per_share="23")
    if award == "NSO":
        lot["grant_value_not_determinable"] = True
    if award in ("ISO", "ESPP"):
        lot["statutory_plan_confirmed"] = True
    if award == "ISO":
        lot["prior_amt_adjustment_per_share"] = "3"
    if award == "ESPP":
        lot.update(grant_fmv_per_share="22", grant_option_price_per_share="20")
    return {
        "schema_version": "1", "tax_year": 2025, "kind": "equity",
        "sources": [
            {"id": "award", "document": "synthetic award", "locator": "all lot assertions"},
            {"id": "sale", "document": "synthetic broker", "locator": "sale and scope assertions"},
        ],
        "lots": [lot],
        "sales": [{"sale_id": "sale", "lot_id": "lot", "shares": "100", "date": "2025-06-15",
                   "proceeds": "3000", "fees": "0", "reported_basis": "2000",
                   "arm_length": True, "at_fair_market_value": True, "source_ids": ["sale"]}],
    }


class OfficialPublication525Tests(unittest.TestCase):
    def test_official_numeric_examples(self):
        fixtures = sorted((ROOT / "fixtures" / "official").glob("p525*.json"))
        self.assertEqual(len(fixtures), 3)
        for path in fixtures:
            with self.subTest(fixture=path.name):
                fixture = json.loads(path.read_text())
                provenance = fixture["provenance"]
                self.assertEqual(provenance["url"], "https://www.irs.gov/pub/irs-prior/p525--2025.pdf")
                self.assertIn(f"Example {provenance['example_number']}", provenance["locator"])
                self.assertTrue(provenance["quote"])
                actual = values(run(fixture["document"]))
                for key, expected in fixture["official_expected_facts"].items():
                    self.assertEqual(actual[key], expected, key)
                for key, expected in fixture["derived_expected_facts"].items():
                    self.assertEqual(actual[key], expected, key)
                if provenance["example_number"] in (10, 11):
                    self.assertIsNone(provenance["original_years"])
                    self.assertTrue(provenance["adapted"])
                else:
                    self.assertEqual(provenance["original_years"], [2023, 2024, 2025])
                    self.assertFalse(provenance["adapted"])


class SyntheticEquityTests(unittest.TestCase):
    def test_rsu_wages_not_counted_twice_and_basis_sign(self):
        document = synthetic()
        document["sales"][0].update(fees="7", reported_basis="0")
        actual = values(run(document))
        self.assertEqual(actual["lot.lot.acquisition_compensation"], "2300")
        self.assertEqual(actual["sale.sale.disposition_compensation"], "0")
        self.assertEqual(actual["sale.sale.actual_basis"], "2300")
        self.assertEqual(actual["sale.sale.reported_basis_correction"], "-2300")
        self.assertEqual(actual["sale.sale.capital_gain_before_wash"], "693")
        document["sales"][0]["reported_basis"] = "2500"
        self.assertEqual(values(run(document))["sale.sale.reported_basis_correction"], "200")

    def test_example_includes_sell_to_cover_and_remaining_gross_shares(self):
        document = json.loads((ROOT / "examples" / "equity.json").read_text())
        actual = values(run(document))
        self.assertEqual(actual["lot.rsu-2025.acquisition_compensation"], "5000")
        self.assertEqual(actual["sale.cover.capital_gain_before_wash"], "0")
        self.assertEqual(actual["sale.later.capital_gain_before_wash"], "395")
        self.assertEqual(actual["lot.rsu-2025.remaining_shares"], "30")

    def test_nso_explicit_wages_and_basis(self):
        actual = values(run(synthetic("NSO")))
        self.assertEqual(actual["lot.lot.acquisition_compensation"], "300")
        self.assertEqual(actual["sale.sale.actual_basis"], "2300")
        self.assertEqual(actual["sale.sale.disposition_compensation"], "0")
        self.assertEqual(actual["sale.sale.capital_gain_before_wash"], "700")

    def test_qualifying_iso_regular_and_amt_basis_are_separate(self):
        actual = values(run(synthetic("ISO")))
        self.assertEqual(actual["sale.sale.disposition_compensation"], "0")
        self.assertEqual(actual["sale.sale.actual_basis"], "2000")
        self.assertEqual(actual["sale.sale.amt_basis"], "2300")
        self.assertEqual(actual["sale.sale.capital_gain_before_wash"], "1000")
        self.assertEqual(actual["lot.lot.current_year_amt_exercise_adjustment"], "0")

    def test_iso_disqualified_sale_price_limitation_and_loss(self):
        for proceeds, fees, wages, basis, gain in [
            ("3000", "0", "300", "2300", "700"),
            ("2150", "10", "140", "2140", "0"),
            ("1900", "10", "0", "2000", "-110"),
        ]:
            with self.subTest(proceeds=proceeds):
                document = synthetic("ISO")
                document["lots"][0]["grant"] = "2023-07-15"
                document["sales"][0].update(proceeds=proceeds, fees=fees,
                                             iso_sale_limitation_eligible=True)
                actual = values(run(document))
                self.assertEqual(actual["sale.sale.disposition_compensation"], wages)
                self.assertEqual(actual["sale.sale.actual_basis"], basis)
                self.assertEqual(actual["sale.sale.capital_gain_before_wash"], gain)
                self.assertEqual(actual["sale.sale.amt_basis"], "2300")
                self.assertEqual(actual["sale.sale.long_term"], "1")
                self.assertEqual(actual["sale.sale.qualified"], "0")

    def test_iso_same_year_sale_and_remaining_amt_adjustment(self):
        document = synthetic("ISO")
        document["lots"][0].update(acquired="2025-01-15", prior_amt_adjustment_per_share="0")
        document["sales"][0].update(shares="40", proceeds="1000", reported_basis="800",
                                     iso_sale_limitation_eligible=True)
        actual = values(run(document))
        self.assertEqual(actual["sale.sale.actual_basis"], "920")
        self.assertEqual(actual["sale.sale.amt_basis"], "920")
        self.assertEqual(actual["lot.lot.current_year_amt_exercise_adjustment"], "180")
        self.assertEqual(actual["lot.lot.remaining_amt_basis"], "1380")
        document["sales"][0].update(proceeds="780")
        actual = values(run(document))
        self.assertEqual(actual["sale.sale.amt_basis"], "800")
        self.assertEqual(actual["sale.sale.disposition_compensation"], "0")

    def test_iso_prior_amt_assertion_cannot_be_inferred(self):
        for prior in (None, "0", "2", "4"):
            document = synthetic("ISO")
            if prior is None:
                del document["lots"][0]["prior_amt_adjustment_per_share"]
            else:
                document["lots"][0]["prior_amt_adjustment_per_share"] = prior
            with self.subTest(prior=prior), self.assertRaises(TaxInputError):
                run(document)

    def test_espp_qualified_lesser_of_discount_or_gain_and_loss(self):
        for proceeds, wages, gain in [("3000", "200", "800"),
                                      ("2100", "100", "0"),
                                      ("1900", "0", "-100")]:
            document = synthetic("ESPP")
            document["sales"][0]["proceeds"] = proceeds
            actual = values(run(document))
            with self.subTest(proceeds=proceeds):
                self.assertEqual(actual["sale.sale.disposition_compensation"], wages)
                self.assertEqual(actual["sale.sale.capital_gain_before_wash"], gain)

    def test_espp_qualifying_disposal_fmv_is_before_fees(self):
        document = synthetic("ESPP")
        document["sales"][0].update(proceeds="2100", fees="110")
        actual = values(run(document))
        self.assertEqual(actual["sale.sale.disposition_compensation"], "100")
        self.assertEqual(actual["sale.sale.capital_gain_before_wash"], "-110")

    def test_espp_disqualified_loss_does_not_limit_spread(self):
        document = synthetic("ESPP")
        document["lots"][0]["acquired"] = "2025-01-15"
        document["sales"][0].update(proceeds="1900", fees="5")
        actual = values(run(document))
        self.assertEqual(actual["sale.sale.disposition_compensation"], "300")
        self.assertEqual(actual["sale.sale.actual_basis"], "2300")
        self.assertEqual(actual["sale.sale.capital_gain_before_wash"], "-405")

    def test_espp_lookback_uses_grant_hypothetical_price(self):
        document = synthetic("ESPP")
        document["lots"][0].update(grant_fmv_per_share="100", grant_option_price_per_share="85",
                                    cost_per_share="68", exercise_fmv_per_share="80")
        document["sales"][0]["proceeds"] = "10000"
        actual = values(run(document))
        self.assertEqual(actual["sale.sale.disposition_compensation"], "1500")
        self.assertEqual(actual["sale.sale.actual_basis"], "8300")
        self.assertEqual(actual["sale.sale.capital_gain_before_wash"], "1700")

    def test_espp_no_grant_discount(self):
        document = synthetic("ESPP")
        document["lots"][0].update(grant_option_price_per_share="22")
        self.assertEqual(values(run(document))["sale.sale.disposition_compensation"], "0")

    def test_anniversaries_not_day_counts(self):
        cases = [
            ("2023-06-15", "2024-01-15", "2025-06-15", "0", "1"),
            ("2023-06-15", "2024-01-15", "2025-06-16", "1", "1"),
            ("2022-01-15", "2024-06-15", "2025-06-15", "0", "0"),
            ("2022-01-15", "2024-06-15", "2025-06-16", "1", "1"),
            ("2022-01-15", "2024-02-29", "2025-02-28", "0", "0"),
            ("2022-01-15", "2024-02-29", "2025-03-01", "1", "1"),
        ]
        for grant, acquired, sold, qualified, long_term in cases:
            document = synthetic("ESPP")
            document["lots"][0].update(grant=grant, acquired=acquired)
            document["sales"][0]["date"] = sold
            with self.subTest(grant=grant, acquired=acquired, sold=sold):
                actual = values(run(document))
                self.assertEqual(actual["sale.sale.qualified"], qualified)
                self.assertEqual(actual["sale.sale.long_term"], long_term)

    def test_partial_cumulative_and_fractional_shares(self):
        document = synthetic()
        document["lots"][0]["shares"] = "1.25"
        document["sales"][0].update(shares="0.4", proceeds="12", reported_basis="0")
        document["sales"].append(dict(document["sales"][0], sale_id="second", shares="0.35"))
        actual = values(run(document))
        self.assertEqual(actual["sale.sale.actual_basis"], "9.2")
        self.assertEqual(actual["sale.second.actual_basis"], "8.05")
        self.assertEqual(actual["sale.sale.remaining_shares"], "0.85")
        self.assertEqual(actual["sale.second.remaining_shares"], "0.5")
        self.assertEqual(actual["lot.lot.remaining_shares"], "0.5")
        document["sales"].append(dict(document["sales"][0], sale_id="third", shares="0.51"))
        with self.assertRaisesRegex(TaxInputError, "oversells"):
            run(document)

    def test_multiple_lots_consume_independently(self):
        document = synthetic()
        document["lots"].append(dict(document["lots"][0], lot_id="other"))
        document["sales"].append(dict(document["sales"][0], sale_id="other", lot_id="other",
                                      date="2025-02-01", shares="10"))
        actual = values(run(document))
        self.assertEqual(actual["lot.lot.remaining_shares"], "0")
        self.assertEqual(actual["lot.other.remaining_shares"], "90")

    def test_sales_cannot_be_backdated_or_historical(self):
        for sold in ("2025-01-01", "2024-06-15", "2026-06-15"):
            document = synthetic()
            document["lots"][0]["acquired"] = "2025-01-15"
            document["sales"][0]["date"] = sold
            with self.subTest(sold=sold), self.assertRaises(TaxInputError):
                run(document)
        document = synthetic()
        document["sales"][0]["shares"] = "40"
        document["sales"].append(dict(document["sales"][0], sale_id="backdated", date="2025-01-15"))
        with self.assertRaisesRegex(TaxInputError, "chronological"):
            run(document)

    def test_unknown_and_missing_fields_at_every_level(self):
        for award in ("RSU", "NSO", "ISO", "ESPP"):
            base = synthetic(award)
            for section in ("top", "lots", "sales", "sources"):
                document = copy.deepcopy(base)
                target = document if section == "top" else document[section][0]
                target["unexpected"] = "1"
                with self.subTest(award=award, section=section), self.assertRaises(TaxInputError):
                    run(document)
            for section in ("lots", "sales"):
                for key in base[section][0]:
                    document = copy.deepcopy(base)
                    del document[section][0][key]
                    with self.subTest(award=award, missing=key), self.assertRaises(TaxInputError):
                        run(document)

    def test_scope_and_wages_must_be_explicit_true(self):
        for award in ("RSU", "NSO", "ISO", "ESPP"):
            base = synthetic(award)
            for section in ("lots", "sales"):
                assertions = [key for key, value in base[section][0].items() if value is True]
                for key in assertions:
                    for invalid in (False, 1, "true", None):
                        document = copy.deepcopy(base)
                        document[section][0][key] = invalid
                        with self.subTest(award=award, key=key, invalid=invalid), self.assertRaises(TaxInputError):
                            run(document)

    def test_iso_disqualification_requires_limitation_assertion(self):
        document = synthetic("ISO")
        document["lots"][0]["grant"] = "2023-07-15"
        for assertion in (None, False, 1, "true"):
            document["sales"][0]["iso_sale_limitation_eligible"] = assertion
            with self.subTest(assertion=assertion), self.assertRaises(TaxInputError):
                run(document)
        for award in ("RSU", "NSO", "ESPP", "ISO"):
            document = synthetic(award)
            document["sales"][0]["iso_sale_limitation_eligible"] = True
            with self.subTest(award=award), self.assertRaises(TaxInputError):
                run(document)

    def test_reject_inconsistent_award_amounts(self):
        for award, changes in [
            ("RSU", {"cost_per_share": "1"}), ("RSU", {"compensation_per_share": "0"}),
            ("NSO", {"compensation_per_share": "2"}), ("NSO", {"cost_per_share": "30"}),
            ("ESPP", {"grant_option_price_per_share": "18"}),
            ("ESPP", {"grant_option_price_per_share": "23"}),
            ("ESPP", {"cost_per_share": "10"}), ("ISO", {"cost_per_share": "30"}),
            ("ISO", {"grant": "2024-01-16"}),
        ]:
            document = synthetic(award)
            document["lots"][0].update(changes)
            with self.subTest(award=award, changes=changes), self.assertRaises(TaxInputError):
                run(document)

    def test_reject_invalid_numbers_dates_and_shapes(self):
        for invalid in (0, 1.2, "NaN", "Infinity", "1e2", "-1", True, "0.1234567890123"):
            document = synthetic()
            document["sales"][0]["shares"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(TaxInputError):
                run(document)
        for invalid in ("2025-02-29", "2025-2-01", 20250101):
            document = synthetic()
            document["sales"][0]["date"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(TaxInputError):
                run(document)
        for section, invalid in (("lots", []), ("lots", {}), ("sales", {}), ("sources", {}),
                                 ("schema_version", 1), ("tax_year", "2025"), ("kind", "wash")):
            document = synthetic()
            document[section] = invalid
            with self.subTest(section=section), self.assertRaises(TaxInputError):
                run(document)

    def test_duplicate_ids_unknown_lots_and_malformed_sources(self):
        for section in ("lots", "sales"):
            document = synthetic()
            document[section].append(copy.deepcopy(document[section][0]))
            with self.subTest(section=section), self.assertRaises(TaxInputError):
                run(document)
        document = synthetic()
        document["sales"][0]["lot_id"] = "missing"
        with self.assertRaises(TaxInputError):
            run(document)
        for ids in ([], "award", ["award", "award"], [1]):
            document = synthetic()
            document["lots"][0]["source_ids"] = ids
            with self.subTest(ids=ids), self.assertRaises(TaxInputError):
                run(document)
        for award in ("OTHER", [], None):
            document = synthetic()
            document["lots"][0]["award_type"] = award
            with self.subTest(award=award), self.assertRaises(TaxInputError):
                run(document)

    def test_source_provenance_carries_through_cumulative_consumption(self):
        document = synthetic()
        document["sources"].append({"id": "second", "document": "synthetic", "locator": "second sale"})
        document["sales"][0]["shares"] = "40"
        document["sales"].append(dict(document["sales"][0], sale_id="second", source_ids=["second"]))
        result = run(document)
        facts = {item["id"]: item for item in result["facts"]}
        self.assertEqual(facts["sale.second.remaining_shares"]["source_ids"], ["award", "sale", "second"])
        self.assertEqual(facts["lot.lot.remaining_shares"]["source_ids"], ["award", "sale", "second"])
        for item in result["facts"]:
            self.assertTrue(item["formula"])
            self.assertTrue(item["inputs"])
            self.assertTrue(item["source_ids"])
            self.assertTrue(item["rule_ids"][0].startswith("equity."))
            Decimal(item["value"])

    def test_stateless_scenarios_do_not_mutate_document(self):
        document = synthetic("ESPP")
        original = copy.deepcopy(document)
        result = run(document)
        scenario = copy.deepcopy(document)
        scenario["sales"][0]["proceeds"] = "1900"
        self.assertNotEqual(result, run(scenario))
        self.assertEqual(document, original)
        self.assertEqual(result, run(document))
        self.assertIn("wash", " ".join(result["warnings"]))

    def test_no_sales_and_fixed_context_contract(self):
        document = synthetic("ISO")
        document["sales"] = []
        document["lots"][0].update(acquired="2025-01-15", prior_amt_adjustment_per_share="0")
        with localcontext() as ambient:
            ambient.prec = 3
            actual = values(run(document))
            self.assertEqual(ambient.prec, 3)
        self.assertEqual(actual["lot.lot.remaining_shares"], "100")
        self.assertEqual(actual["lot.lot.current_year_amt_exercise_adjustment"], "300")
        self.assertEqual(actual["lot.lot.remaining_amt_basis"], "2300")

    def test_large_decimal_products_remain_unrounded_in_dispatcher_context(self):
        document = synthetic()
        document["lots"][0].update(shares="1.000000000001",
                                    compensation_per_share="123456789012345678.123456789012")
        document["sales"][0].update(shares="1.000000000001", reported_basis="0")
        with localcontext() as ambient:
            ambient.prec = 3
            actual = values(run(document))
        self.assertEqual(actual["sale.sale.actual_basis"],
                         "123456789012469134.912469134690123456789012")


if __name__ == "__main__":
    unittest.main()
