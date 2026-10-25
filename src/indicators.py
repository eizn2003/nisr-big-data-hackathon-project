"""Single source of truth for every indicator shown in the dashboard.

Pages read labels, colours, polarity and wording from here, so adding an
indicator means adding one entry (and the data column) rather than editing
every page.
"""

SCALES = {
    "teal":   ["#EAF6F3", "#A6D8CF", "#4BAE9F", "#1A7F73", "#0E3F46"],
    "blue":   ["#EAF1FA", "#A9C6EA", "#5B93D3", "#2F6DB5", "#14315F"],
    "amber":  ["#FFF7E0", "#FBE19B", "#F2BE4A", "#C98F16", "#6F4B07"],
    "coral":  ["#FDEEE9", "#F7BFAE", "#EC8A70", "#C9533A", "#7A2616"],
    "violet": ["#F1EEFA", "#CBBFEA", "#9A85D4", "#6A4FB3", "#2E2063"],
    "green":  ["#EEF7EC", "#B8DDB2", "#74B86C", "#3E8F46", "#1B4D26"],
    "rose":   ["#FCEEF5", "#F1BDD7", "#DE7FAF", "#B8467F", "#661A41"],
    "olive":  ["#F5F7E9", "#D4DDA0", "#A9BB55", "#788E2A", "#3C4A12"],
}

# accent (graphics) and text_accent (readable on white) per hue
HUES = {
    "teal":   ("#1A8A7D", "#126B61"),
    "blue":   ("#2F6DB5", "#245A99"),
    "amber":  ("#E0A12F", "#8F6209"),
    "coral":  ("#DB6A4E", "#B04328"),
    "violet": ("#7B5EC2", "#5B3FA6"),
    "green":  ("#4C9A52", "#2F7338"),
    "rose":   ("#C0508A", "#99356B"),
    "olive":  ("#8DA03A", "#566D1D"),
}

_RAW = [
    dict(
        column="Owns a bank account (%)", short="Bank account",
        label="Bank-account ownership", kpi_label="Owns a bank account",
        national="Own bank account", variable="k1", role="core",
        family="Access & usage", polarity="positive", hue="teal",
        priority_candidate=True, priority_default=True,
        description="Percentage of respondents who own a bank account in their own name.",
        interpretation="Higher values indicate greater reported bank-account ownership. "
                       "Ownership does not necessarily indicate active account use.",
    ),
    dict(
        column="Registered mobile-money user (%)", short="Mobile money",
        label="Mobile-money registration", kpi_label="Active registered mobile-money user",
        national="Registered mobile-money user", variable="f5", role="core",
        family="Access & usage", polarity="positive", hue="blue",
        priority_candidate=True, priority_default=True,
        description="Percentage who describe themselves as a registered mobile-money user "
                    "(the first response option of question F5).",
        interpretation="Registered users who have never used the service, or who no longer use it, "
                       "are separate F5 categories and are not counted here. The figure is therefore "
                       "lower than the published headline for registered mobile wallets.",
    ),
    dict(
        column="Borrowed in the past 12 months (%)", short="Borrowing",
        label="Borrowing in the past 12 months", kpi_label="Borrowed in the past 12 months",
        national="Borrowed in the past 12 months", variable="h2_1", role="core",
        family="Credit", polarity="neutral", hue="amber",
        priority_candidate=False, priority_default=False,
        description="Percentage who reported borrowing money in the past 12 months.",
        interpretation="Measures recent borrowing activity from any source, not access to formal credit. "
                       "Borrowing is not automatically positive or negative.",
    ),
    dict(
        column="Does not save (%)", short="Doesn't save",
        label="Does not save", kpi_label="Does not save",
        national="Does not save", variable="g3a_17", role="core",
        family="Saving & resilience", polarity="negative", hue="coral",
        priority_candidate=True, priority_default=True,
        description="Percentage classified as not saving by any mechanism.",
        interpretation="A financial-vulnerability signal, not a direct measure of access to savings services.",
    ),
    dict(
        column="Has emergency funds (%)", short="Emergency funds",
        label="Has emergency funds", kpi_label="Has emergency funds",
        national="Has emergency funds", variable="e9b", role="supporting",
        family="Saving & resilience", polarity="positive", hue="violet",
        priority_candidate=True, priority_default=False,
        description="Percentage of respondents who report setting aside emergency or rainy-day funds.",
        interpretation="A financial-resilience signal. It does not measure the amount saved "
                       "or whether funds would cover a major emergency.",
    ),
    dict(
        column="Saves with a group (%)", short="Group saving",
        label="Saves with a group", kpi_label="Saves with a group",
        national="Saves with a group", variable="g3a_11", role="supporting",
        family="Saving & resilience", polarity="positive", hue="green",
        priority_candidate=False, priority_default=False,
        description="Percentage of respondents who report saving with a group, such as a "
                    "cooperative, VSLA, tontine, or ikibina.",
        interpretation="Measures participation in group-based saving, not the adequacy of savings "
                       "or overall financial inclusion.",
    ),
    dict(
        column="Currently uses Umurenge SACCO (%)", short="SACCO use",
        label="Currently uses an Umurenge SACCO", kpi_label="Currently uses an Umurenge SACCO",
        national="Currently uses Umurenge SACCO", variable="qf4_06", role="supporting",
        family="Institutions", polarity="positive", hue="rose",
        priority_candidate=False, priority_default=False,
        description="Percentage of all respondents who currently use an Umurenge SACCO. "
                    "Respondents who never used one are counted as non-users.",
        interpretation="Reflects use of the sector-level SACCO network in the full adult sample. "
                       "Ever-use is also available in the district table.",
    ),
    dict(
        column="Currently uses a savings group (%)", short="Savings-group use",
        label="Currently uses a savings group", kpi_label="Currently uses a savings group",
        national="Currently uses a savings group", variable="qf4_10", role="supporting",
        family="Institutions", polarity="positive", hue="olive",
        priority_candidate=False, priority_default=False,
        description="Percentage of all respondents who currently use a savings group they save "
                    "with or borrow from. Respondents who never used one are counted as non-users.",
        interpretation="Compare with 'Saves with a group', which comes from a different question "
                       "and gives a somewhat higher national figure.",
    ),
]


def _build():
    registry = []
    for raw in _RAW:
        item = dict(raw)
        accent, text_accent = HUES[item["hue"]]
        item["accent"] = accent
        item["text_accent"] = text_accent
        item["scale"] = SCALES[item["hue"]]
        registry.append(item)
    return registry


REGISTRY = _build()
BY_COLUMN = {item["column"]: item for item in REGISTRY}
BY_NATIONAL = {item["national"]: item for item in REGISTRY}
CORE = [item for item in REGISTRY if item["role"] == "core"]
PRIORITY_CANDIDATES = [item for item in REGISTRY if item["priority_candidate"]]

# Backwards-compatible mapping used by shared styling helpers.
INDICATOR_THEME = {item["column"]: item for item in REGISTRY}


def available(frame):
    """Registry entries whose column exists in the given dataframe."""
    return [item for item in REGISTRY if item["column"] in frame.columns]
