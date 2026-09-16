"""Public-pipeline contracts; mutated examples are synthetic regressions, not IRS facts."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from decimal import Context, Decimal, Inexact, Rounded, ROUND_UP, getcontext, localcontext
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from borderbucks import __version__
from borderbucks.common import TaxInputError
from borderbucks.engine import MAX_BYTES, calculate, explain, loads, scenario
from borderbucks.rules import RULES


ROOT = Path(__file__).resolve().parents[1]
KINDS = ("equity", "foreign", "pfic", "wash")


def example(kind):
    return loads((ROOT / "examples" / f"{kind}.json").read_bytes())


def objects(value, path=()):
    """Walk all input objects, including records unused by arithmetic."""
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from objects(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from objects(child, path + (index,))


def at(value, path):
    for key in path:
        value = value[key]
    return value


def digest(document):
    # Independent oracle: do not use the production canonical() helper.
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def context_state(context):
    return (context.prec, context.rounding, context.Emax, context.Emin,
            context.capitals, context.clamp, dict(context.traps), dict(context.flags))


class EngineTests(unittest.TestCase):
    def assert_rejected(self, document, pattern=None):
        original = deepcopy(document)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            with self.assertRaisesRegex(TaxInputError, pattern or ".+") as caught:
                calculate(document)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(document, original)
        self.assertFalse(hasattr(caught.exception, "facts"))
        self.assertFalse(hasattr(caught.exception, "report"))

    def assert_report(self, document, report):
        self.assertEqual(report["inputs"], document)
        self.assertEqual(report["input_sha256"], digest(document))
        self.assertEqual(report["schema_version"], "1")
        self.assertEqual(report["engine_version"], __version__)
        self.assertEqual(report["tax_year"], 2025)
        self.assertEqual(report["kind"], document["kind"])
        self.assertEqual(report["status"], "needs_professional_review")
        self.assertIn("not tax advice or filing-ready", report["disclaimer"])
        self.assertTrue(report["warnings"])
        self.assertEqual(loads(json.dumps(report, allow_nan=False)), report)
        known = {source["id"] for source in document["sources"]}
        ids, used_rules = set(), set()
        self.assertTrue(report["facts"])
        for fact in report["facts"]:
            self.assertEqual(set(fact), {
                "id", "value", "unit", "formula", "inputs", "source_ids", "rule_ids",
            })
            self.assertNotIn(fact["id"], ids)
            ids.add(fact["id"])
            self.assertTrue(fact["formula"])
            self.assertIsInstance(fact["inputs"], dict)
            self.assertIsInstance(fact["value"], str)
            self.assertRegex(fact["value"], r"^-?\d+(?:\.\d+)?$")
            self.assertTrue(Decimal(fact["value"]).is_finite())
            self.assertIn(fact["unit"], ("USD", "shares", "days", "boolean"))
            self.assertTrue(fact["source_ids"])
            self.assertEqual(fact["source_ids"], sorted(set(fact["source_ids"])))
            self.assertLessEqual(set(fact["source_ids"]), known)
            self.assertTrue(fact["rule_ids"])
            for rule_id in fact["rule_ids"]:
                self.assertTrue(rule_id.endswith(".2025"))
                self.assertIn(rule_id, RULES)
                self.assertEqual(report["rules"][rule_id], RULES[rule_id])
                for key in ("title", "url", "locator", "authority", "revision"):
                    self.assertTrue(report["rules"][rule_id][key])
                self.assertTrue(RULES[rule_id]["url"].startswith("https://www.irs.gov/"))
                used_rules.add(rule_id)
        self.assertEqual(list(report["rules"]), sorted(used_rules))

    def test_all_synthetic_examples_through_public_dispatch(self):
        expected = {
            "equity": {"lot.rsu-2025.acquisition_compensation": "5000",
                       "sale.cover.capital_gain_before_wash": "0",
                       "sale.later.capital_gain_before_wash": "395",
                       "lot.rsu-2025.remaining_shares": "30"},
            "foreign": {"foreign.fbar.maximum_upper_bound_usd": "80000",
                        "foreign.form8938.yearend_usd": "45000"},
            "pfic": {"pfic.synthetic-fund.deductible_ordinary_loss_usd": "1000",
                     "pfic.synthetic-fund.unallowed_loss_usd": "2000",
                     "pfic.synthetic-fund.ending_basis_usd": "9000"},
            "wash": {"wash.total_loss": "500", "wash.disallowed_loss": "300",
                     "wash.deferred_loss": "200", "wash.permanent_loss": "100",
                     "wash.allowed_loss": "200"},
        }
        self.assertEqual({path.stem for path in (ROOT / "examples").glob("*.json")}, set(KINDS))
        for kind in KINDS:
            with self.subTest(kind=kind):
                document = example(kind)
                report = calculate(document)
                self.assert_report(document, report)
                facts = {fact["id"]: fact["value"] for fact in report["facts"]}
                for fact_id, value in expected[kind].items():
                    self.assertEqual(facts[fact_id], value)

    def test_all_official_fixtures_through_loads_and_public_dispatch(self):
        paths = sorted((ROOT / "fixtures" / "official").glob("*.json"))
        self.assertGreaterEqual(len(paths), 4)
        for path in paths:
            with self.subTest(fixture=path.name):
                fixture = loads(path.read_bytes())
                provenance = fixture["provenance"]
                self.assertTrue(provenance["quote"])
                self.assertIn(f"Example {provenance['example_number']}", provenance["locator"])
                self.assertTrue(provenance["adaptation"])
                document = loads(json.dumps(fixture["document"]))
                self.assertIn(provenance["url"], [s["document"] for s in document["sources"]])
                report = calculate(document)
                self.assert_report(document, report)
                facts = {fact["id"]: fact for fact in report["facts"]}
                official, derived = fixture["official_expected_facts"], fixture["derived_expected_facts"]
                self.assertTrue(official)
                self.assertTrue(derived)
                self.assertTrue(set(official).isdisjoint(derived))
                for group in ("official_expected_facts", "derived_expected_facts"):
                    for fact_id, expected in fixture[group].items():
                        with self.subTest(group=group, fact_id=fact_id):
                            self.assertEqual(facts[fact_id]["value"], expected)
                for fact_id in facts:
                    detail = explain(document, fact_id)
                    self.assertEqual(detail["fact"], facts[fact_id])
                    self.assertEqual(detail["sources"], [s for s in document["sources"]
                                     if s["id"] in facts[fact_id]["source_ids"]])
                    self.assertEqual(detail["rules"], {key: RULES[key]
                                     for key in facts[fact_id]["rule_ids"]})

    def check_ambient_context(self, **settings):
        documents = [example(kind) for kind in KINDS]
        documents[0]["lots"][0]["compensation_per_share"] = "123456789012345678.123456789012"
        documents[1]["fx_rates"][0]["local_per_usd"] = "3"
        documents[1]["assets"][0].update(maximum_local="1", yearend_local="1")
        documents[2]["holdings"][0].update(
            adjusted_basis_usd="999999999999999998.999999999999",
            yearend_fmv_usd="999999999999999999.000000000001")
        documents[3]["sale"].update(shares="3", basis="1", proceeds="0", fees="0")
        documents[3]["replacements"][0]["shares"] = "1"
        documents[3]["replacements"][1]["shares"] = "1"
        outside = context_state(getcontext())
        for document in documents:
            with self.subTest(kind=document["kind"], settings=settings):
                with localcontext(Context(prec=60)):
                    expected = calculate(document)
                with localcontext(Context()) as caller:
                    for key, value in settings.items():
                        if key == "trap":
                            caller.traps[value] = True
                        else:
                            setattr(caller, key, value)
                    caller.flags[Rounded] = True
                    before = context_state(caller)
                    self.assertEqual(calculate(document), expected)
                    self.assertEqual(context_state(caller), before)
                    self.assertIs(getcontext(), caller)
                    invalid = deepcopy(document)
                    invalid["unexpected"] = True
                    self.assert_rejected(invalid)
                    self.assertEqual(context_state(caller), before)
        self.assertEqual(context_state(getcontext()), outside)

    def test_ambient_precision_two_is_independently_isolated(self):
        self.check_ambient_context(prec=2)

    def test_ambient_round_up_is_independently_isolated(self):
        self.check_ambient_context(rounding=ROUND_UP)

    def test_ambient_exponent_limits_are_independently_isolated(self):
        self.check_ambient_context(Emax=2, Emin=-2, clamp=1, capitals=0)

    def test_ambient_inexact_trap_is_independently_isolated(self):
        self.check_ambient_context(trap=Inexact)

    def test_ambient_rounded_trap_is_independently_isolated(self):
        self.check_ambient_context(trap=Rounded)

    def test_hash_ignores_object_order_and_json_whitespace_not_array_order(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                document = example(kind)
                document["sources"][0]["locator"] += " synthetic \u00e9"
                original = calculate(document)
                reordered = deepcopy(document)
                for _, record in list(objects(reordered)):
                    items = list(record.items())[::-1]
                    record.clear()
                    record.update(items)
                reparsed = loads(json.dumps(reordered, indent=4, ensure_ascii=False))
                self.assertEqual(calculate(reparsed), original)
                self.assertEqual(original["input_sha256"], digest(document))
                if len(reordered["sources"]) == 1:
                    reordered["sources"].append({"id": "unused", "document": "Synthetic",
                                                  "locator": "Not used in facts"})
                baseline = calculate(reordered)
                reordered["sources"].reverse()
                reversed_report = calculate(reordered)
                self.assertNotEqual(baseline["input_sha256"], reversed_report["input_sha256"])
                self.assertEqual(baseline["facts"], reversed_report["facts"])

    def test_hash_preserves_decimal_spelling_and_source_metadata(self):
        document = example("equity")
        baseline = calculate(document)
        document["sales"][0]["proceeds"] = "1500.00"
        changed = calculate(document)
        self.assertNotEqual(changed["input_sha256"], baseline["input_sha256"])
        self.assertEqual(changed["facts"], baseline["facts"])
        self.assertEqual(changed["inputs"]["sales"][0]["proceeds"], "1500.00")
        document["sources"][0]["locator"] += "; synthetic correction"
        self.assertNotEqual(calculate(document)["input_sha256"], changed["input_sha256"])

    def test_inputs_reports_rules_and_repeated_calls_do_not_alias(self):
        rules_before = deepcopy(RULES)
        for kind in KINDS:
            with self.subTest(kind=kind):
                document = example(kind)
                original = deepcopy(document)
                report = calculate(document)
                expected = deepcopy(report)
                self.assertEqual(document, original)
                for path, record in objects(document):
                    self.assertIsNot(at(report["inputs"], path), record)
                report["inputs"]["sources"][0]["locator"] = "changed report"
                report["facts"][0]["inputs"]["changed"] = "0"
                report["facts"][0]["source_ids"].clear()
                report["warnings"].clear()
                for rule in report["rules"].values():
                    rule["locator"] = "changed report"
                    if "additional_urls" in rule:
                        rule["additional_urls"].clear()
                self.assertEqual(document, original)
                self.assertEqual(RULES, rules_before)
                self.assertEqual(calculate(document), expected)
                fresh = calculate(document)
                document["sources"][0]["locator"] = "changed caller"
                self.assertEqual(fresh, expected)

    def test_every_fact_has_exact_dependency_sources_not_entire_manifest(self):
        for kind in KINDS:
            document = example(kind)
            refs = {}
            for index, (path, record) in enumerate(objects(document)):
                if "source_ids" in record:
                    source_id = f"record-{index}"
                    record["source_ids"] = [source_id]
                    refs[path] = source_id
            document["sources"] = [{"id": value, "document": "Synthetic per-record evidence",
                                     "locator": repr(path)} for path, value in refs.items()]
            document["sources"].append({"id": "unused", "document": "Synthetic unused source",
                                         "locator": "Must not enter any fact"})
            report = calculate(document)
            for fact in report["facts"]:
                fact_id = fact["id"]
                if kind == "wash":
                    expected = set(refs.values())
                elif kind == "pfic":
                    expected = {refs[("holdings", 0)]}
                elif kind == "foreign":
                    if fact_id.startswith("foreign.asset."):
                        index = next(i for i, asset in enumerate(document["assets"])
                                     if fact_id.startswith(f"foreign.asset.{asset['id']}."))
                        currency = document["assets"][index]["currency"]
                        rate = next(i for i, r in enumerate(document["fx_rates"])
                                    if r["currency"] == currency)
                        expected = {refs[("assets", index)], refs[("fx_rates", rate)]}
                    elif "threshold" in fact_id:
                        expected = {refs[()]}
                    else:
                        expected = {refs[()], refs[("assets", 0)], refs[("assets", 1)],
                                    refs[("fx_rates", 0)], refs[("fx_rates", 1)]}
                else:
                    expected = {refs[("lots", 0)]}
                    if fact_id.startswith("sale.cover."):
                        expected.add(refs[("sales", 0)])
                    if fact_id.startswith("sale.later."):
                        expected.add(refs[("sales", 1)])
                    if fact_id in ("sale.later.remaining_shares", "lot.rsu-2025.remaining_shares"):
                        expected.update((refs[("sales", 0)], refs[("sales", 1)]))
                with self.subTest(kind=kind, fact_id=fact_id):
                    self.assertEqual(fact["source_ids"], sorted(expected))

    def test_source_references_are_validated_on_every_record(self):
        for kind in KINDS:
            base = example(kind)
            for path, record in objects(base):
                if "source_ids" not in record:
                    continue
                known = record["source_ids"][0]
                for invalid in ([], None, known, [1], [None], [{}], [known, known],
                                [""], ["missing"], [known, "missing"]):
                    document = deepcopy(base)
                    at(document, path)["source_ids"] = invalid
                    with self.subTest(kind=kind, path=path, invalid=invalid):
                        self.assert_rejected(document)

    def test_unused_rates_excluded_assets_unsold_lots_and_outside_window_refs_fail(self):
        foreign = example("foreign")
        foreign["assets"] = foreign["assets"][:1]
        foreign["fx_rates"][1]["source_ids"] = ["missing"]
        excluded = example("foreign")
        excluded["assets"][2]["source_ids"] = ["missing"]
        equity = example("equity")
        equity["sales"] = []
        equity["lots"][0]["source_ids"] = ["missing"]
        wash = example("wash")
        wash["replacements"][0].update(acquired="2025-11-19", source_ids=["missing"])
        for document in (foreign, excluded, equity, wash):
            with self.subTest(kind=document["kind"], document=document):
                self.assert_rejected(document, "unresolved source reference")

    def test_manifest_duplicates_malformed_and_unused_entries_fail(self):
        for kind in KINDS:
            base = example(kind)
            duplicate = deepcopy(base)
            duplicate["sources"].append(dict(duplicate["sources"][0], locator="Different locator"))
            with self.subTest(kind=kind, duplicate=True):
                self.assert_rejected(duplicate, "duplicate source manifest ID")
            for invalid in (None, {}, [], "source", [None], ["source"],
                            [{"id": "only-id"}]):
                document = deepcopy(base)
                document["sources"] = invalid
                with self.subTest(kind=kind, invalid=invalid):
                    self.assert_rejected(document)
            for key in ("id", "document", "locator"):
                for invalid in (None, True, 1, [], {}, "", " ", "\n", "x" * 501):
                    document = deepcopy(base)
                    source = {"id": "unused", "document": "Synthetic", "locator": "Unused"}
                    source[key] = invalid
                    document["sources"].append(source)
                    with self.subTest(kind=kind, key=key, invalid=invalid):
                        self.assert_rejected(document)

    def test_unknown_fields_and_malformed_objects_at_every_level(self):
        for kind in KINDS:
            base = example(kind)
            for path, _ in objects(base):
                document = deepcopy(base)
                at(document, path)["unexpected"] = "synthetic"
                with self.subTest(kind=kind, path=path, unknown=True):
                    self.assert_rejected(document, "unknown fields")
                for invalid in (None, [], "object", 1, True):
                    document = deepcopy(base)
                    if path:
                        at(document, path[:-1])[path[-1]] = invalid
                    else:
                        document = invalid
                    with self.subTest(kind=kind, path=path, invalid=invalid):
                        self.assert_rejected(document)
            for path, record in objects(base):
                for key, value in record.items():
                    if not isinstance(value, list):
                        continue
                    for invalid in (None, {}, "list", 1, True):
                        document = deepcopy(base)
                        at(document, path)[key] = invalid
                        with self.subTest(kind=kind, path=path, key=key, invalid=invalid):
                            self.assert_rejected(document)

    def test_missing_required_fields_and_scope_flags_fail_publicly(self):
        for kind in KINDS:
            base = example(kind)
            for path, record in objects(base):
                for key, value in record.items():
                    if key == "included_in_account_id":
                        continue  # Optional relationship, not an eligibility default.
                    document = deepcopy(base)
                    del at(document, path)[key]
                    with self.subTest(kind=kind, path=path, missing=key):
                        self.assert_rejected(document)
                    if type(value) is bool:
                        for invalid in (None, 0, 1, "true", [], {}):
                            document = deepcopy(base)
                            at(document, path)[key] = invalid
                            with self.subTest(kind=kind, path=path, key=key, invalid=invalid):
                                self.assert_rejected(document)
                        if value is True and key not in ("include_fbar", "include_form8938"):
                            document = deepcopy(base)
                            at(document, path)[key] = False
                            with self.subTest(kind=kind, path=path, false_flag=key):
                                self.assert_rejected(document)

    def test_only_integer_tax_year_2025_and_string_schema_one(self):
        for kind in KINDS:
            for key, values in (
                ("tax_year", (2024, 2026, "2025", 2025.0, True, None, [], {})),
                ("schema_version", (1, 1.0, True, "2", None, [], {})),
                ("kind", ("unknown", "", True, None, [], {})),
            ):
                for value in values:
                    document = example(kind)
                    document[key] = value
                    with self.subTest(kind=kind, key=key, value=value):
                        self.assert_rejected(document)

    def test_all_financial_fields_reject_nondecimal_and_nonfinite_inputs(self):
        for kind in KINDS:
            base = example(kind)
            for path, record in objects(base):
                for key, value in record.items():
                    if key == "schema_version" or not isinstance(value, str):
                        continue
                    if not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
                        continue
                    for invalid in (1, 1.5, True, None, [], {}, "NaN", "sNaN", "Infinity",
                                    "-Infinity", "1e2", " 1", "+1", "1,000", "1.", "",
                                    "1000000000000000000", "0.0000000000001",
                                    float("nan"), float("inf"), float("-inf")):
                        document = deepcopy(base)
                        at(document, path)[key] = invalid
                        with self.subTest(kind=kind, path=path, key=key, invalid=invalid):
                            self.assert_rejected(document)

    def test_late_invalid_records_never_emit_partial_results_or_damage_baseline(self):
        for kind, collection, field in (("equity", "sales", "proceeds"),
                                         ("foreign", "assets", "maximum_local"),
                                         ("pfic", "holdings", "yearend_fmv_usd"),
                                         ("wash", "replacements", "purchase_basis")):
            document = example(kind)
            baseline = calculate(document)
            invalid = deepcopy(document)
            last = deepcopy(invalid[collection][-1])
            id_field = "sale_id" if kind == "equity" else "lot_id" if kind == "wash" else "id"
            last[id_field] = "late-invalid-record"
            if kind == "wash":
                last["acquisition_order"] = 2
            if kind == "equity":
                last["shares"] = "1"
            last[field] = "not-a-number"
            invalid[collection].append(last)
            with self.subTest(kind=kind):
                self.assert_rejected(invalid, "decimal string")
                self.assertEqual(calculate(document), baseline)

    def test_pfic_unsupported_methods_and_tainted_elections_fail_publicly(self):
        for method in ("1291", "default1291", "section1291", "qef", "", None, [], {}):
            document = example("pfic")
            document["method"] = method
            with self.subTest(method=method):
                self.assert_rejected(document, "section 1291.*not implemented")
        for start in ("late", "purged", "current_year", True, None):
            document = example("pfic")
            document["holdings"][0]["eligibility"]["election_start"] = start
            with self.subTest(start=start):
                self.assert_rejected(document, "late/tainted")
        document = loads((ROOT / "fixtures/official/p525_iso_example8.json").read_bytes())["document"]
        del document["sales"][0]["iso_sale_limitation_eligible"]
        self.assert_rejected(document, "sale-limitation eligibility")

    def test_dispatch_rejects_duplicate_facts_unresolved_rules_and_output_sources(self):
        document = example("pfic")
        valid = calculate(document)["facts"][0]
        for facts in ([valid, deepcopy(valid)], [dict(valid, source_ids=[])],
                      [dict(valid, source_ids=["missing"])], [dict(valid, rule_ids=[])],
                      [dict(valid, rule_ids=["pfic.mtm.2024"])]):
            with self.subTest(facts=facts):
                with patch.dict("borderbucks.engine.CALCULATORS", {
                    "pfic": lambda _: {"facts": deepcopy(facts), "warnings": []},
                }):
                    self.assert_rejected(document, "duplicate output fact ID|unresolved")

    def test_explain_returns_full_exact_sources_rules_and_warnings_for_every_fact(self):
        for kind in KINDS:
            document = example(kind)
            document["sources"].append({"id": "unused", "document": "Synthetic unused",
                                         "locator": "Should not appear in explanations"})
            original = deepcopy(document)
            report = calculate(document)
            for fact in report["facts"]:
                with self.subTest(kind=kind, fact_id=fact["id"]):
                    detail = explain(document, fact["id"])
                    self.assertEqual(detail, {
                        "disclaimer": report["disclaimer"], "input_sha256": report["input_sha256"],
                        "fact": fact, "sources": [s for s in document["sources"]
                                                  if s["id"] in fact["source_ids"]],
                        "rules": {key: RULES[key] for key in fact["rule_ids"]},
                        "warnings": report["warnings"],
                    })
                    self.assertEqual(document, original)
            for invalid in ("missing", "", " ", None, 1, [], {}, "x" * 501):
                with self.subTest(kind=kind, fact_id=invalid), self.assertRaises(TaxInputError):
                    explain(document, invalid)
        detail = explain(example("equity"), "sale.later.actual_basis")
        self.assertEqual(detail["rules"]["equity.basis.2025"]["additional_urls"],
                         ["https://www.irs.gov/pub/irs-prior/i8949--2025.pdf"])
        detail["rules"]["equity.basis.2025"]["additional_urls"].clear()
        self.assertTrue(RULES["equity.basis.2025"]["additional_urls"])

    def test_scenario_replaces_only_target_sale_and_preserves_baseline(self):
        for date_override in (None, "2025-07-01"):
            document = example("equity")
            original = deepcopy(document)
            baseline = calculate(document)
            result = scenario(document, "later", "1900.125", date_override)
            expected = deepcopy(document)
            assumption = {"id": "scenario-assumption", "document": "User-supplied hypothetical",
                          "locator": "Scenario proceeds/date override; not a statement transaction"}
            expected["sources"].append(assumption)
            expected["sales"][1]["source_ids"].append(assumption["id"])
            expected["sales"][1]["proceeds"] = "1900.125"
            if date_override is not None:
                expected["sales"][1]["date"] = date_override
            with self.subTest(date=date_override):
                self.assert_report(expected, result)
                self.assertEqual(result["scenario"], {"baseline_input_sha256": baseline["input_sha256"],
                                                     "sale_id": "later", "hypothetical": True})
                self.assertNotEqual(result["input_sha256"], baseline["input_sha256"])
                self.assertEqual(result["facts"], calculate(expected)["facts"])
                facts = {fact["id"]: fact for fact in result["facts"]}
                self.assertEqual(facts["sale.later.capital_gain_before_wash"]["value"], "-104.875")
                self.assertEqual(facts["sale.later.capital_gain_before_wash"]["source_ids"],
                                 ["award", "broker", "scenario-assumption"])
                self.assertNotIn("scenario-assumption", facts["sale.cover.actual_basis"]["source_ids"])
                self.assertIn("scenario-assumption", facts["lot.rsu-2025.remaining_shares"]["source_ids"])
                self.assertIn("Hypothetical", result["warnings"][-1])
                self.assertEqual(document, original)
                self.assertEqual(calculate(document), baseline)
                self.assertEqual(scenario(document, "later", "1900.125", date_override), result)

    def test_scenario_source_collisions_and_identical_proceeds_remain_hypothetical(self):
        document = example("equity")
        for source_id in ("scenario-assumption", "scenario-assumption-new"):
            document["sources"].append({"id": source_id, "document": "Synthetic existing source",
                                         "locator": "Must not be overwritten"})
        original = deepcopy(document)
        baseline = calculate(document)
        result = scenario(document, "later", "2400")
        self.assertEqual(result["inputs"]["sources"][:-1], document["sources"])
        self.assertEqual(result["inputs"]["sources"][-1]["id"], "scenario-assumption-new-new")
        self.assertEqual(result["inputs"]["sales"][1]["source_ids"],
                         ["broker", "scenario-assumption-new-new"])
        self.assertNotEqual(result["input_sha256"], baseline["input_sha256"])
        self.assertEqual([f["value"] for f in result["facts"]], [f["value"] for f in baseline["facts"]])
        self.assertEqual(document, original)

    def test_invalid_scenarios_fail_without_mutation_or_output(self):
        cases = [(kind, "later", "1", None) for kind in KINDS if kind != "equity"]
        cases += [("equity", sale_id, "1", None) for sale_id in ("missing", None, [], {}, 1)]
        cases += [("equity", "later", value, None)
                  for value in ("NaN", "Infinity", 1.5, None, "-1", "1e2")]
        cases += [("equity", "later", "1", date)
                  for date in ("2024-12-31", "2026-01-01", "2025-01-01", "2025-02-29", 1)]
        for kind, sale_id, proceeds, date in cases:
            document = example(kind)
            original = deepcopy(document)
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(kind=kind, sale_id=sale_id, proceeds=proceeds, date=date):
                with redirect_stdout(out), redirect_stderr(err), self.assertRaises(TaxInputError):
                    scenario(document, sale_id, proceeds, date)
                self.assertEqual(document, original)
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(err.getvalue(), "")
        document = example("equity")
        document["sales"][1]["proceeds"] = "invalid-baseline"
        with self.assertRaises(TaxInputError):
            scenario(document, "later", "2400")

    def test_foreign_recurring_presentations_keep_exact_rational_operands(self):
        document = example("foreign")
        template = document["assets"][0]
        template.update(maximum_local="50000", yearend_local="50000")
        document["fx_rates"][0]["local_per_usd"] = "90"
        document["assets"] = [dict(template, id=f"synthetic-{i}") for i in range(18)]
        report = calculate(document)
        facts = {fact["id"]: fact for fact in report["facts"]}
        aggregate = facts["foreign.fbar.yearend_usd"]
        self.assertEqual(aggregate["value"], "10000")
        self.assertEqual(report["screening"]["fbar"],
                         {"status": "known_not_exceeded", "filing_eligibility_determined": False})
        self.assertEqual(len(aggregate["inputs"]), 18)
        self.assertEqual(sum(Fraction(value) for value in aggregate["inputs"].values()), 10000)
        for fact_id, operand in aggregate["inputs"].items():
            self.assertIn(fact_id, facts)
            self.assertEqual(operand, "5000/9")
            self.assertEqual(facts[fact_id]["inputs"], {"local_value": "50000", "local_per_usd": "90"})
            self.assertEqual(facts[fact_id]["value"], "555." + "5" * 56 + "6")
        document["assets"][0]["maximum_local"] = "50000.000000000001"
        crossed = calculate(document)
        self.assertEqual(crossed["screening"]["fbar"]["status"], "potential_threshold_crossed_review")

    def test_wash_floor40_telescopes_and_does_not_apply_filing_rounding(self):
        document = example("wash")
        document["sale"].update(shares="3", basis="1", proceeds="0", fees="0")
        template = document["replacements"][0]
        document["replacements"] = [dict(template, lot_id=f"third-{i}", shares="1",
                                           acquisition_order=i + 1,
                                           account_type="ira" if i == 1 else "taxable")
                                    for i in range(3)]
        report = calculate(document)
        self.assertEqual(report["allocation_decimal_places"], 40)
        facts = {fact["id"]: fact for fact in report["facts"]}
        allocations = []
        for i, replacement in enumerate(report["replacements"]):
            fact = facts[f"replacement.third-{i}.disallowed_loss"]
            expected = "0." + "3" * 39 + ("4" if i == 2 else "3")
            self.assertEqual(fact["value"], expected)
            self.assertIn("floor40", fact["formula"])
            self.assertEqual(fact["inputs"]["exact_allocation_numerator"], "1")
            self.assertEqual(fact["inputs"]["exact_allocation_denominator"], "3")
            self.assertEqual(replacement["exact_loss_fraction"], {"numerator": "1", "denominator": "3"})
            allocations.append(Fraction(fact["value"]))
        self.assertEqual(sum(allocations), 1)
        self.assertEqual(facts["wash.allowed_loss"]["value"], "0")
        self.assertEqual(Fraction(facts["wash.deferred_loss"]["value"]) +
                         Fraction(facts["wash.permanent_loss"]["value"]), 1)
        document["replacements"].pop()
        partial = {f["id"]: f for f in calculate(document)["facts"]}
        self.assertEqual(partial["wash.disallowed_loss"]["value"], "0." + "6" * 40)
        self.assertLess(Fraction(partial["wash.disallowed_loss"]["value"]), Fraction(2, 3))


class BoundedJSONTests(unittest.TestCase):
    def test_loads_accepts_text_and_bytes_without_financial_number_coercion(self):
        raw = '{"amount":"0001.2300","label":"synthetic \\u00e9"}'
        expected = {"amount": "0001.2300", "label": "synthetic \u00e9"}
        self.assertEqual(loads(raw), expected)
        self.assertEqual(loads(raw.encode("utf-8")), expected)
        self.assertEqual(loads("1.5"), 1.5)  # Financial schema validation belongs to calculate().
        for value in (None, 1, {}, [], bytearray(b"{}")):
            with self.subTest(value=value), self.assertRaises(TaxInputError):
                loads(value)

    def test_duplicate_keys_at_all_depths_including_escaped_equivalents(self):
        for raw in ('{"kind":"equity","kind":"pfic"}',
                    '{"sources":[{"id":"one","id":"two"}]}',
                    '{"a":{"b":{"amount":"1","amount":"2"}}}',
                    '{"id":"one","\\u0069d":"two"}'):
            for data in (raw, raw.encode("utf-8")):
                with self.subTest(raw=raw, type=type(data)), self.assertRaisesRegex(TaxInputError, "duplicate JSON key"):
                    loads(data)

    def test_malformed_json_and_nonjson_constants_do_not_leak_raw_values(self):
        marker = "SYNTHETIC-PRIVATE-VALUE-NOT-REAL-DATA"
        cases = [f'{{"note":"{marker}",}}', f'{{"note":"{marker}"}} trailing',
                 f'{{"note":"{marker}","amount":NaN}}',
                 f'{{"note":"{marker}","amount":Infinity}}',
                 f'{{"note":"{marker}","amount":-Infinity}}',
                 f'{{"note":"{marker}","note":"other"}}',
                 f'{{"note":"{marker}', b'{"note":"\xff"}', ""]
        for raw in cases:
            out, err = io.StringIO(), io.StringIO()
            with self.subTest(raw=raw):
                with redirect_stdout(out), redirect_stderr(err), self.assertRaises(TaxInputError) as caught:
                    loads(raw)
                self.assertNotIn(marker, str(caught.exception))
                self.assertEqual(out.getvalue(), "")
                self.assertEqual(err.getvalue(), "")

    def test_duplicate_key_diagnostic_does_not_disclose_user_controlled_key(self):
        marker = "SYNTHETIC-PRIVATE-KEY-NOT-REAL-DATA"
        raw = json.dumps({marker: "first"})[:-1] + f',"{marker}":"second"}}'
        with self.assertRaises(TaxInputError) as caught:
            loads(raw)
        self.assertNotIn(marker, str(caught.exception))

    def test_loads_two_mib_boundary_counts_utf8_bytes(self):
        self.assertEqual(MAX_BYTES, 2 * 1024 * 1024)
        for raw in (" " * (MAX_BYTES - 2) + "{}", b" " * (MAX_BYTES - 2) + b"{}"):
            self.assertEqual(loads(raw), {})
            with self.assertRaisesRegex(TaxInputError, "2 MiB"):
                loads(raw + raw[:1])
        unicode_raw = '"' + "\u00e9" * (MAX_BYTES // 2 - 1) + '"'
        self.assertEqual(len(unicode_raw.encode("utf-8")), MAX_BYTES)
        self.assertEqual(loads(unicode_raw), "\u00e9" * (MAX_BYTES // 2 - 1))
        with self.assertRaisesRegex(TaxInputError, "2 MiB"):
            loads(unicode_raw + " ")

    def test_calculate_bounds_canonical_input_and_nesting_before_dispatch(self):
        for padding in ("x" * MAX_BYTES, "\u00e9" * (MAX_BYTES // 6)):
            document = example("pfic")
            document["padding"] = padding
            with self.subTest(unicode=not padding.isascii()), self.assertRaisesRegex(TaxInputError, "2 MiB"):
                calculate(document)
        for depth, message in ((29, "unknown fields"), (30, "nesting exceeds 30")):
            document = example("pfic")
            nested = "synthetic"
            for _ in range(depth):
                nested = [nested]
            document["unexpected"] = nested
            with self.subTest(depth=depth), self.assertRaisesRegex(TaxInputError, message):
                calculate(document)
        raw = "[" * 2000 + "0" + "]" * 2000
        with self.assertRaises(TaxInputError):
            loads(raw)
        document = example("pfic")
        document["cycle"] = document
        with self.assertRaisesRegex(TaxInputError, "bounded JSON"):
            calculate(document)
        document = example("pfic")
        document["unexpected"] = Decimal("1")
        with self.assertRaisesRegex(TaxInputError, "bounded JSON"):
            calculate(document)


if __name__ == "__main__":
    unittest.main()
