"""One-page district profile (Markdown) that users can download and share."""

from src import data
from src.indicators import REGISTRY

READING = {
    "positive": "higher = more inclusion/resilience",
    "negative": "higher = more vulnerability",
    "neutral": "neither good nor bad on its own",
}


def district_brief(name, frame, national, barriers=None, priority=None):
    """Build a Markdown profile for one district.

    frame     - district table (all indicator columns + 'Valid respondents')
    national  - {national indicator label: estimate}
    barriers  - district barrier table (optional)
    priority  - dict with keys score, rank, total, robust_text, drivers (optional)
    """
    row = frame.loc[frame["District"].eq(name)].iloc[0]
    n = int(row["Valid respondents"])
    lines = [
        f"# {name} District: financial inclusion profile",
        "",
        "Source: FinScope Rwanda 2024 (weighted survey estimates). Survey-based, not a live measurement.",
        f"Respondents in this district: {n:,}.",
        "",
        "## Indicators compared with the national estimate",
        "",
        "| Indicator | District | National | Difference (pp) | Indicative margin (±pp) | Rank of 30 | How to read |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in REGISTRY:
        col = item["column"]
        if col not in frame.columns or item["national"] not in national:
            continue
        value = float(row[col])
        nat = float(national[item["national"]])
        rank = int(frame[col].rank(ascending=False, method="min")[frame["District"].eq(name)].iloc[0])
        lines.append(
            f"| {item['label']} | {value:.1f}% | {nat:.1f}% | {value - nat:+.1f} | "
            f"{data.moe_pp(value, n):.1f} | {rank} | {READING[item['polarity']]} |"
        )

    if priority:
        lines += [
            "",
            "## Priority screening (exploratory)",
            "",
            f"- Relative priority score: **{priority['score']:.1f} / 100**, rank {priority['rank']} of {priority['total']}.",
            f"- {priority['robust_text']}",
        ]
        if priority.get("drivers"):
            lines.append(f"- Largest contributors: {priority['drivers']}.")

    if barriers is not None and not barriers.empty:
        b = barriers.loc[barriers["District"].eq(name)]
        if not b.empty:
            base = int(b["District non-account respondents"].iloc[0])
            fam = (
                data.barrier_family_shares(b, by_district=False)
                .sort_values("Weighted share (%)", ascending=False)
            )
            lines += [
                "",
                "## Why people without a bank account say they have none",
                "",
                f"Base: {base:,} respondents without an account in this district (weighted shares).",
                "",
            ]
            for _, r in fam.iterrows():
                lines.append(f"- {r['Barrier family']}: {r['Weighted share (%)']:.1f}%")

    lines += [
        "",
        "## Read with care",
        "",
        "- Margins assume simple random sampling; the survey's design information is not available, "
        "so true margins are larger. Differences smaller than the margin should not be treated as real.",
        "- Differences describe gaps; they do not explain causes.",
        "- Mobile-money figures count registered users who describe themselves as current users, "
        "so they are lower than the headline for registered wallets.",
    ]
    return "\n".join(lines) + "\n"
