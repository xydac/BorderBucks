"""Versioned rule locators, bundled locally; URLs are never fetched at runtime."""

P525 = "https://www.irs.gov/pub/irs-prior/p525--2025.pdf"
P550 = "https://www.irs.gov/pub/irs-prior/p550--2025.pdf"
I8938 = "https://www.irs.gov/pub/irs-prior/i8938--2025.pdf"


def _rule(title, url, locator, authority, revision="2025"):
    return dict(title=title, url=url, locator=locator, authority=authority, revision=revision)


RULES = {
    "equity.rsu.2025": _rule("Publication 525", P525,
        "Employee Compensation; Restricted Property", "26 USC 83(a); 26 CFR 1.83-4(b)"),
    "equity.nso.2025": _rule("Publication 525", P525,
        "Nonstatutory Stock Options: option without readily determinable value; sale of stock", "26 USC 83"),
    "equity.iso.2025": _rule("Publication 525", P525,
        "Statutory Stock Options: ISOs; Alternative minimum tax; Example 8", "26 USC 421, 422(c)(2), 56(b)(3)"),
    "equity.espp.2025": _rule("Publication 525", P525,
        "Employee stock purchase plan: holding period satisfied/not satisfied; Examples 10-11", "26 USC 421, 423(c)"),
    "equity.basis.2025": _rule("Publication 525 and Form 8949 instructions", P525,
        "Stock Options: sale of stock; Restricted Property; Form 8949 column (g), code B",
        "26 CFR 1.83-4(b); 26 USC 1012"),
    "equity.holding.2025": _rule("Publications 525 and 550", P525,
        "Statutory Stock Options: holding period requirement; Pub. 550 Holding Period", "26 USC 422(a)(1), 423(a)(1), 1222"),
    "wash.sale.2025": _rule("Publication 550", P550,
        "Wash Sales: Example 1; More or less stock bought than sold", "26 USC 1091(a), (d)"),
    "wash.holding.2025": _rule("Publication 550", P550,
        "Wash Sales: replacement stock holding period", "26 USC 1223(3)"),
    "wash.ira.2025": _rule("Revenue Ruling 2008-5",
        "https://www.irs.gov/irb/2008-03_IRB#RR-2008-5", "Holding: IRA or Roth IRA replacement acquisition",
        "Rev. Rul. 2008-5", "2008-5; applicable 2025"),
    "foreign.fbar.2025": _rule("Comparison of Form 8938 and FBAR requirements",
        "https://www.irs.gov/businesses/comparison-of-form-8938-and-fbar-requirements",
        "Reporting threshold; maximum account values; reviewed 2025-09-18", "31 CFR 1010.350"),
    "foreign.fatca.2025": _rule("Instructions for Form 8938", I8938,
        "Reporting Thresholds; Joint Interest Valuation; Valuing Specified Foreign Financial Assets", "26 USC 6038D"),
    "foreign.fx.2025": _rule("Comparison of Form 8938 and FBAR requirements",
        "https://www.irs.gov/businesses/comparison-of-form-8938-and-fbar-requirements",
        "How are maximum account or asset values determined and reported? Yearend conversion; reviewed 2025-09-18",
        "Form 8938 instructions; FinCEN Form 114 instructions"),
    "pfic.mtm.2025": _rule("Instructions for Form 8621",
        "https://www.irs.gov/pub/irs-prior/i8621--2025.pdf",
        "Mark-to-Market Election: Tax Consequences; Basis adjustment; Part IV lines 10a-12", "26 USC 1296"),
}
RULES["equity.basis.2025"]["additional_urls"] = ["https://www.irs.gov/pub/irs-prior/i8949--2025.pdf"]
RULES["equity.holding.2025"]["additional_urls"] = [P550]
