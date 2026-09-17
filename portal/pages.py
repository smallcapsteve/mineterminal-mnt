"""Navigation and data-page specs for the MNT portal (MNT_NAV_V2, 2026-09-16).

Step 1a of the revised extraction plan
(claude/MNT_INGESTION_PIPELINE_PLAN_REVISED_2026-09-16.md).

One list drives the two-row nav in base.html (via templates/_nav.html), and
PageSpec objects drive templates/data_page.html. Adding a page means adding it
here, not hand-editing base.html and writing a template.

Pages with no href are shown in the nav as greyed "coming" tabs (Justin,
2026-09-16). Give a page an href and a key the day its page ships.

Nothing in this module touches the database.
"""
from dataclasses import dataclass, field


# ---------------------------------------------------------------- navigation
# key must equal the "page" value the route passes to its template.
MNT_NAV = [
    {
        "id": "geology",
        "label": "Exploration & Geology",
        "pages": [
            {"label": "Drill Results", "href": "/drills", "key": "drills"},
            {"label": "Resource Estimates", "href": "/resources", "key": "resources"},
            {"label": "Production Results", "href": "/production-results", "key": "production"},
            {"label": "Economic Studies", "href": "/economic-studies", "key": "economic"},
            {"label": "Exploration", "href": "/exploration-programs", "key": "exploration"},
            {"label": "Permits", "href": "/permits-approvals", "key": "permits"},
            {"label": "Metallurgy & Processing"},
            {"label": "Technical Reports"},
        ],
    },
    {
        "id": "deals",
        "label": "Deals & Capital",
        "pages": [
            {"label": "Financings", "href": "/financings", "key": "financings"},
            {"label": "Share Capital", "href": "/share-capital", "key": "sharecap"},
            {"label": "Mergers & Acquisitions", "href": "/mergers-acquisitions", "key": "mna"},
            {"label": "Debt & Credit"},
            {"label": "Royalties & Streams"},
            {"label": "Partnerships & JV"},
            {"label": "Property Options"},
            {"label": "Financials"},
        ],
    },
    {
        "id": "corporate",
        "label": "Corporate",
        "pages": [
            {"label": "Management Changes", "href": "/management-changes", "key": "management"},
            {"label": "Corporate Actions"},
            {"label": "Listings & Exchange"},
            {"label": "Shareholder Meetings"},
            {"label": "Regulatory & Compliance"},
        ],
    },
]

for _g in MNT_NAV:
    # A group tab opens the first page in it that exists.
    _g["href"] = next(p["href"] for p in _g["pages"] if p.get("href"))
    _g["keys"] = [p["key"] for p in _g["pages"] if p.get("key")]


def nav_group_for(page_key):
    for g in MNT_NAV:
        if page_key and page_key in g["keys"]:
            return g
    return None


# ---------------------------------------------------------------- data pages
@dataclass
class Col:
    key: str
    label: str
    width: int                      # percent of table width
    kind: str = "text"              # ticker | plain | date | text | strong | release
    td_class: str = ""
    mtp: str = "mining"             # MineTerminalPro section for kind="ticker"
    mtp_title: str = "mining data"  # link title: "Open TICKER <mtp_title> on MineTerminalPro"


@dataclass
class PageSpec:
    key: str
    url: str
    title: str
    tag: str
    describe: str
    empty_text: str
    columns: list
    table_class: str = ""
    filters: list = field(default_factory=lambda: ["company", "window", "has_data"])
    windows: list = field(default_factory=list)
    # DATA_PAGE_DETAIL_V1 (2026-09-17): optional expandable rows. The route puts a list of dicts
    # under row[detail]; a toggle is drawn in the detail_anchor column when the list has at least
    # detail_min entries, and the list is laid out with detail_columns in a row below.
    detail: str = ""
    detail_anchor: str = ""
    detail_min: int = 2
    detail_noun: str = "rows"
    detail_columns: list = field(default_factory=list)


PAGE_SPECS = {
    "drills": PageSpec(
        key="drills",
        url="/drills",
        title="Drill Results",
        tag="Drill Results",
        describe=("The best new assay intercept from each news release tagged Drill Results. "
                  "Open a row for every interval the release reports; figures are read from the release text."),
        empty_text="No drill results in this window.",
        table_class="drill-table",
        windows=[(0, "All time"), (7, "Last 7 days"), (30, "Last 30 days"),
                 (90, "Last 90 days"), (365, "Last year")],
        columns=[
            Col("ticker", "Ticker", 9, kind="ticker"),
            Col("company_name", "Company", 17, kind="plain"),
            Col("published_at", "Date", 9, kind="date"),
            Col("project", "Project", 20),
            Col("top_summary", "Top Intercept", 23, kind="strong", td_class="drill-intercept"),
            Col("top_hole_id", "Hole", 14, td_class="fin-kind"),
            Col("url", "Release", 8, kind="release"),
        ],
        detail="intervals",
        detail_anchor="top_summary",
        detail_noun="intervals",
        detail_columns=[
            Col("hole_id", "Hole", 22),
            Col("summary", "Interval", 38, kind="strong"),
            Col("from_m", "From (m)", 13, kind="num"),
            Col("to_m", "To (m)", 13, kind="num"),
            Col("note", "", 14, kind="plain"),
        ],
    ),
}


def register(templates):
    """Expose the nav to every template. Called once from app.py."""
    templates.env.globals["MNT_NAV"] = MNT_NAV
    templates.env.globals["mnt_nav_group_for"] = nav_group_for
