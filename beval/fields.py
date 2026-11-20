"""Single source of truth for what the models must extract and how it is scored.

Units are fixed so scoring is mechanical:
  money_mm   US dollars in millions          tolerance +/-0.5% (min $0.5M)
  ratio_pct  percent, e.g. 3.12 for 3.12%     tolerance +/-0.01 (1 basis point)
  per_share  US dollars per share             tolerance +/-$0.005
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    key: str
    group: str
    kind: str          # money_mm | ratio_pct | per_share
    label: str
    definition: str


FIELDS: list[Field] = [
    Field("eps_reported", "Earnings", "per_share", "Diluted EPS (reported, GAAP)",
          "GAAP diluted earnings per common share for the quarter."),
    Field("eps_adjusted", "Earnings", "per_share", "Adjusted diluted EPS",
          "The bank's own adjusted / ex-notable-items diluted EPS. null if the release gives none."),
    Field("net_income_common", "Earnings", "money_mm", "Net income to common",
          "Net income available to common shareholders, GAAP."),
    Field("notable_items_eps", "Earnings", "per_share", "Notable items, EPS impact",
          "Total after-tax EPS impact of items the bank calls notable/significant. Negative if they reduced EPS. null if none disclosed."),
    Field("nii", "Revenue", "money_mm", "Net interest income",
          "GAAP net interest income (not FTE)."),
    Field("nim", "Revenue", "ratio_pct", "Net interest margin",
          "Headline NIM as the bank reports it; declare the basis (FTE or GAAP) in nim_basis."),
    Field("nonint_income", "Revenue", "money_mm", "Noninterest income",
          "GAAP noninterest income, including any securities gains/losses."),
    Field("nonint_expense", "Expense", "money_mm", "Noninterest expense",
          "GAAP noninterest expense."),
    Field("efficiency_ratio", "Expense", "ratio_pct", "Efficiency ratio",
          "The bank's headline (reported, not adjusted) efficiency ratio, using its own definition."),
    Field("provision", "Credit", "money_mm", "Provision for credit losses",
          "Total provision for credit losses for the quarter."),
    Field("nco", "Credit", "money_mm", "Net charge-offs",
          "Net charge-offs in dollars for the quarter."),
    Field("nco_ratio", "Credit", "ratio_pct", "NCO ratio (annualized)",
          "Annualized net charge-offs to average loans."),
    Field("acl_ratio", "Credit", "ratio_pct", "ACL to loans",
          "Allowance for credit losses to period-end total loans (use the bank's headline ACL ratio)."),
    Field("avg_loans", "Balance sheet", "money_mm", "Average loans",
          "Average total loans (and leases) for the quarter."),
    Field("avg_deposits", "Balance sheet", "money_mm", "Average deposits",
          "Average total deposits for the quarter."),
    Field("eop_deposits", "Balance sheet", "money_mm", "Period-end deposits",
          "Total deposits at quarter end."),
    Field("cet1", "Capital and returns", "ratio_pct", "CET1 ratio",
          "Common equity tier 1 ratio at quarter end (estimated/preliminary is fine, as reported)."),
    Field("tbvps", "Capital and returns", "per_share", "Tangible book value per share",
          "Tangible book value per common share at quarter end."),
    Field("rotce", "Capital and returns", "ratio_pct", "ROTCE",
          "Headline return on average tangible common equity, as reported (annualized)."),
    Field("buybacks", "Capital and returns", "money_mm", "Share repurchases",
          "Dollar amount of common shares repurchased in the quarter. 0 if the release says none; null if not disclosed."),
]

# Prior-quarter values the model must also report (period-mismatch trap + arithmetic check).
PRIOR_Q_FIELDS = ["eps_reported", "nii", "nim", "nonint_expense", "provision"]

FIELD_BY_KEY = {f.key: f for f in FIELDS}

TOLERANCE = {
    "money_mm": ("rel", 0.005, 0.5),   # 0.5%, but never tighter than $0.5M
    "ratio_pct": ("abs", 0.0501, None),  # 1 bp (+ float slack)
    "per_share": ("abs", 0.0051, None),  # half a cent (+ float slack)
}


def within_tolerance(kind: str, truth: float, value: float) -> bool:
    mode, tol, floor = TOLERANCE[kind]
    if mode == "rel":
        return abs(value - truth) <= max(abs(truth) * tol, floor)
    return abs(value - truth) <= tol
