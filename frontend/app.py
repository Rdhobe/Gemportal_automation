"""Streamlit frontend for the GeM tender brain."""

from __future__ import annotations

import csv
import io
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.constants import (
    BID_TYPES,
    INDIAN_STATES,
    IT_CATEGORIES,
    OTHER_CATEGORIES,
)
from backend.models import Settings
from backend.utils import format_inr, format_lakh
from frontend.api_client import ApiError, BrainApi

st.set_page_config(
    page_title="GeM Tender Brain",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
  .block-container { padding-top: 2.2rem; padding-bottom: 3rem; }
  .hero {
      background: radial-gradient(circle at 15% 20%, #1d4ed8 0%, transparent 45%),
                  linear-gradient(120deg, #0b1220 0%, #132a4d 55%, #0b4f5c 100%);
      border: 1px solid rgba(148, 163, 184, .25);
      border-radius: 20px;
      padding: 26px 30px 24px 30px;
      color: #f8fafc;
      margin-bottom: 18px;
  }
  .hero-kicker {
      font-size: .72rem; letter-spacing: .22em; text-transform: uppercase;
      color: #7dd3fc; font-weight: 700; margin-bottom: 6px;
  }
  .hero h1 { font-size: 2rem; line-height: 1.15; margin: 0 0 8px 0; font-weight: 700; }
  .hero p { margin: 0; color: #cbd5e1; font-size: .98rem; max-width: 760px; }
  .pill {
      display: inline-block; padding: 3px 10px; border-radius: 999px;
      background: rgba(125, 211, 252, .13); color: #7dd3fc;
      border: 1px solid rgba(125, 211, 252, .35);
      font-size: .72rem; letter-spacing: .06em; text-transform: uppercase;
      margin-right: 6px; margin-top: 12px;
  }
  .detail-card {
      border: 1px solid rgba(148, 163, 184, .3); border-radius: 16px;
      padding: 18px 20px; background: rgba(15, 23, 42, .35);
  }
  div[data-testid="stMetricValue"] { font-size: 1.6rem; }
  .small-muted { color: #94a3b8; font-size: .82rem; }
  footer { visibility: hidden; }
  @media (max-width: 900px) {
      div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: .7rem; }
      div[data-testid="stColumn"] {
          flex: 1 1 45% !important;
          width: 45% !important;
          min-width: 45% !important;
      }
  }
</style>
"""


# --------------------------------------------------------------------------- helpers
def get_api() -> BrainApi:
    if "api" not in st.session_state:
        st.session_state.api = BrainApi()
    return st.session_state.api


def init_state() -> None:
    if "settings" not in st.session_state:
        st.session_state.settings = Settings().model_dump()
    if "meta" not in st.session_state:
        st.session_state.meta = {
            "groq_available": False,
            "google_available": False,
            "states": INDIAN_STATES,
        }
    if "active_run" not in st.session_state:
        st.session_state.active_run = None
    if "loaded_once" not in st.session_state:
        st.session_state.loaded_once = False
    if "flash" not in st.session_state:
        st.session_state.flash = None


def load_backend_state(api: BrainApi) -> bool:
    """Load settings/meta/latest run from the backend. Returns online status."""
    if not api.ping():
        return False
    try:
        st.session_state.settings = api.get_settings()
        st.session_state.meta = api.meta()
        if not st.session_state.loaded_once:
            st.session_state.active_run = api.latest_run()
            st.session_state.loaded_once = True
        return True
    except ApiError:
        return False


def group_label(value: str | None) -> str:
    return {"it": "IT", "other": "Other", "unknown": "—"}.get(value or "", "—")


def tender_rows(tenders: list[dict]) -> list[dict]:
    rows = []
    for tender in tenders:
        rows.append(
            {
                "Score": tender.get("score", 0),
                "Bid No": tender.get("bid_number", ""),
                "Title": tender.get("title", ""),
                "Group": group_label(tender.get("category_group")),
                "Category": tender.get("category", ""),
                "Buyer": tender.get("department", ""),
                "State": tender.get("state", ""),
                "Value": format_inr(tender.get("estimated_value")),
                "EMD": (
                    "Not listed"
                    if tender.get("emd") is None
                    else format_inr(tender.get("emd"))
                ),
                "Days left": tender.get("days_remaining"),
                "Closes": tender.get("end_date", ""),
                "Summary": tender.get("summary", ""),
            }
        )
    return rows


def rows_to_csv(tenders: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "score",
            "bid_number",
            "title",
            "category",
            "group",
            "buyer",
            "ministry",
            "state",
            "quantity",
            "start_date",
            "end_date",
            "days_remaining",
            "estimated_value",
            "emd",
            "offer_validity",
            "summary",
            "eligibility",
            "matched_keywords",
            "link",
            "pdf",
        ]
    )
    for tender in tenders:
        writer.writerow(
            [
                tender.get("score"),
                tender.get("bid_number"),
                tender.get("title"),
                tender.get("category"),
                tender.get("category_group"),
                tender.get("department"),
                tender.get("ministry"),
                tender.get("state"),
                tender.get("quantity"),
                tender.get("start_date"),
                tender.get("end_date"),
                tender.get("days_remaining"),
                tender.get("estimated_value"),
                tender.get("emd"),
                tender.get("offer_validity"),
                tender.get("summary"),
                " | ".join(tender.get("eligibility_flags") or []),
                ", ".join(tender.get("matched_keywords") or []),
                tender.get("link"),
                tender.get("pdf_url"),
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")


def run_scan(api: BrainApi, settings: dict, sample: bool) -> None:
    """Start a backend run and poll until it finishes."""
    try:
        api.start_run(settings, use_sample=sample)
    except ApiError as exc:
        st.error(str(exc))
        return

    bar = st.progress(0, text="Starting the scan…")
    details = st.empty()
    status: dict = {}
    deadline = time.time() + 15 * 60
    while time.time() < deadline:
        time.sleep(0.8)
        try:
            status = api.run_status()
        except ApiError as exc:
            bar.empty()
            details.empty()
            st.error(str(exc))
            return
        percent = int(status.get("progress", 0) or 0)
        bar.progress(
            min(max(percent, 0), 100) / 100,
            text=status.get("message") or "Working…",
        )
        details.caption(
            f"Stage: {status.get('stage', '—')}  •  fetched {status.get('fetched', 0)}  "
            f"•  matched {status.get('matched', 0)}"
        )
        if status.get("status") in {"done", "error"}:
            break

    bar.empty()
    details.empty()

    if status.get("status") == "error":
        st.error(f"Run failed: {status.get('error') or 'unknown error'}")
        return
    if status.get("status") != "done":
        st.warning("The scan is taking longer than expected. Refresh the page in a moment.")
        return

    try:
        st.session_state.active_run = api.latest_run()
    except ApiError as exc:
        st.error(str(exc))
        return
    st.session_state.flash = (
        f"Scan complete — {status.get('matched', 0)} matching tenders "
        f"from {status.get('fetched', 0)} bids."
    )
    st.rerun()


def render_tender_detail(tender: dict) -> None:
    st.markdown("---")
    header_left, header_right = st.columns([3, 1])
    with header_left:
        st.subheader(tender.get("title", "Tender"))
        st.caption(
            f"{tender.get('bid_number', '')}  •  {tender.get('department') or 'Buyer not listed'}"
            f"  •  {tender.get('state') or 'Location not listed'}"
        )
    with header_right:
        st.metric("Match score", f"{tender.get('score', 0):.1f}")

    st.markdown(tender.get("summary") or "_No summary generated._")

    metric_cols = st.columns(5)
    metric_cols[0].metric("Estimated value", format_lakh(tender.get("estimated_value")))
    metric_cols[1].metric(
        "EMD",
        "Not listed" if tender.get("emd") is None else format_lakh(tender.get("emd")),
    )
    metric_cols[2].metric(
        "Days left",
        "—" if tender.get("days_remaining") is None else tender.get("days_remaining"),
    )
    metric_cols[3].metric("Quantity", tender.get("quantity") or "—")
    metric_cols[4].metric("Offer validity", tender.get("offer_validity") or "—")

    link_cols = st.columns([1, 1, 1, 3])
    if tender.get("link"):
        link_cols[0].link_button("Open on GeM", tender["link"], width="stretch")
    if tender.get("pdf_url"):
        link_cols[1].link_button("Open PDF", tender["pdf_url"], width="stretch")
    link_cols[2].caption(
        "PDF parsed ✅" if tender.get("pdf_parsed") else "PDF not parsed"
    )

    left, right = st.columns([1.25, 1])
    with left:
        st.markdown("#### Eligibility points to check")
        flags = tender.get("eligibility_flags") or []
        if flags:
            for flag in flags:
                st.markdown(f"- ⚠️ {flag}")
        else:
            st.markdown("- No blocking eligibility points were extracted. Verify in the PDF.")

        eligibility = tender.get("eligibility") or {}
        if eligibility:
            st.dataframe(
                [{"Point": key, "Extracted detail": value} for key, value in eligibility.items()],
                hide_index=True,
                width="stretch",
            )

        keywords = tender.get("matched_keywords") or []
        if keywords:
            st.markdown("#### Matched keywords")
            st.markdown(" ".join(f"`{word}`" for word in keywords))

    with right:
        st.markdown("#### Why this score")
        breakdown = tender.get("score_breakdown") or []
        if breakdown:
            st.dataframe(
                [
                    {"Reason": item.get("reason", ""), "Points": item.get("points", 0)}
                    for item in breakdown
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "Points": st.column_config.NumberColumn(format="%+.1f")
                },
            )
        else:
            st.caption("No scoring detail available.")


def render_run_dashboard(run: dict, api: BrainApi) -> None:
    tenders = run.get("tenders") or []
    fetched = run.get("total_fetched", 0)
    source = run.get("source") or "unknown"
    avg_score = sum(t.get("score", 0) for t in tenders) / len(tenders) if tenders else 0
    it_count = sum(1 for t in tenders if t.get("category_group") == "it")
    urgent = sum(
        1
        for t in tenders
        if isinstance(t.get("days_remaining"), int) and t.get("days_remaining") <= 10
    )

    source_label = {
        "gem": "🟢 Live GeM",
        "playwright": "🟢 GeM via browser",
        "sample": "🟡 Sample data",
    }.get(source, source)

    st.markdown(
        f"<div class='small-muted'>Run <b>{run.get('run_id')}</b> • {source_label} • "
        f"finished {run.get('finished_at') or '—'} • "
        f"{run.get('duration_seconds') or 0}s</div>",
        unsafe_allow_html=True,
    )

    metrics = st.columns(5)
    metrics[0].metric("Matched", len(tenders))
    metrics[1].metric("Fetched", fetched)
    metrics[2].metric("Avg score", f"{avg_score:.1f}")
    metrics[3].metric("IT tenders", it_count)
    metrics[4].metric("Closing ≤10d", urgent)

    if run.get("errors"):
        with st.expander("Run notes"):
            for error in run["errors"]:
                st.markdown(f"- {error}")

    st.markdown("### Matching tenders")
    filter_cols = st.columns([2, 1, 1, 1])
    search = filter_cols[0].text_input(
        "Search", placeholder="Title, bid number, buyer or keyword"
    )
    groups = filter_cols[1].multiselect(
        "Group", ["IT", "Other"], default=["IT", "Other"]
    )
    states_available = sorted({t.get("state") for t in tenders if t.get("state")})
    state_filter = filter_cols[2].multiselect("State", states_available)
    max_score = max([t.get("score", 0) for t in tenders] + [100])
    min_score = filter_cols[3].slider(
        "Min score", 0, int(max_score) + 1, 0, help="Hide weaker matches"
    )

    filtered = []
    needle = search.strip().lower()
    for tender in tenders:
        if tender.get("score", 0) < min_score:
            continue
        if group_label(tender.get("category_group")) not in groups:
            continue
        if state_filter and tender.get("state") not in state_filter:
            continue
        if needle:
            haystack = " ".join(
                str(tender.get(field, ""))
                for field in ("title", "bid_number", "department", "category", "summary")
            ).lower()
            if needle not in haystack:
                continue
        filtered.append(tender)

    if not filtered:
        st.info("No tenders match the current filters.")
    else:
        st.dataframe(
            tender_rows(filtered),
            hide_index=True,
            width="stretch",
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=max(int(max_score) + 1, 50), format="%.1f"
                ),
                "Title": st.column_config.TextColumn("Title", width="large"),
                "Summary": st.column_config.TextColumn("Summary", width="large"),
                "Days left": st.column_config.NumberColumn("Days left", format="%d"),
            },
        )

    action_cols = st.columns([1.2, 1.2, 1.2, 2.4])
    action_cols[0].download_button(
        "⬇️ Download CSV",
        data=rows_to_csv(filtered),
        file_name=f"gem_tenders_{run.get('run_id', 'run')}.csv",
        mime="text/csv",
        width="stretch",
    )
    export_clicked = action_cols[1].button("📤 Export to Sheets", width="stretch")
    if export_clicked:
        with st.spinner("Writing to Google Sheets…"):
            try:
                result = api.export(run.get("run_id"))
            except ApiError as exc:
                st.error(str(exc))
            else:
                if result.get("status") == "ok":
                    st.success(f"Exported {result.get('rows_written')} rows.")
                    if result.get("spreadsheet_url"):
                        st.link_button("Open spreadsheet", result["spreadsheet_url"])
                else:
                    st.info(result.get("reason") or "Export skipped.")

    st.markdown("### Tender detail")
    if filtered:
        labels = {
            f"{t.get('score', 0):.1f}  |  {t.get('bid_number', '')}  |  {t.get('title', '')[:80]}": t
            for t in filtered
        }
        selected_label = st.selectbox("Inspect tender", list(labels.keys()))
        render_tender_detail(labels[selected_label])


# ----------------------------------------------------------------------------- app
st.markdown(CSS, unsafe_allow_html=True)
init_state()
api = get_api()
online = load_backend_state(api)
settings = st.session_state.settings
meta = st.session_state.meta

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

st.markdown(
    """
    <div class="hero">
      <div class="hero-kicker">GeM Tender Brain</div>
      <h1>Relevant tenders, scored and summarised.</h1>
      <p>Fetch bids from GeM, apply your value, EMD, location and keyword limits, read the
      tender PDFs, and export a clean sheet — all from one place.</p>
      <div>
        <span class="pill">Python backend</span>
        <span class="pill">Explainable scoring</span>
        <span class="pill">Groq summaries</span>
        <span class="pill">Google Sheets</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not online:
    st.warning(
        "The backend is offline. Start it in another terminal with "
        "`python run_backend.py`, then refresh this page."
    )

# ------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### Control room")
    st.markdown(
        f"{'🟢' if online else '🔴'} Backend "
        f"`{api.base_url.replace('http://', '')}`"
    )
    if online:
        try:
            health = api.health()
            st.caption(f"v{health.get('version')} • data: `{health.get('data_dir')}`")
        except ApiError:
            pass

    st.divider()
    sample_default = bool(settings.get("use_sample_data"))
    sample_mode = st.toggle(
        "Use sample tenders",
        value=sample_default,
        help="Runs instantly with realistic offline data. Turn off to fetch live GeM bids.",
    )
    if sample_mode != sample_default:
        st.session_state.settings["use_sample_data"] = sample_mode
        if online:
            try:
                api.save_settings(st.session_state.settings)
            except ApiError as exc:
                st.caption(f"Could not save: {exc}")
    if sample_mode:
        st.caption("Sample mode is on — results are demo data, not live GeM bids.")
    else:
        st.caption("Live mode fetches from bidplus.gem.gov.in and falls back to samples if blocked.")

    st.divider()
    st.markdown("**Capabilities**")
    st.markdown(
        f"- AI summaries: {'✅ Groq' if meta.get('groq_available') else '➖ rule-based'}\n"
        f"- Google Sheets: {'✅ configured' if meta.get('google_available') else '➖ local CSV only'}\n"
        f"- PDF reader: {'✅ pdfplumber' if settings.get('enable_pdf') else '➖ disabled'}"
    )
    st.caption("Credentials live in the project-root `.env` — never in the UI or repo.")

tab_dashboard, tab_settings, tab_history, tab_help = st.tabs(
    ["📊 Dashboard", "⚙️ Settings", "🕘 Run history", "📘 How it works"]
)

# ----------------------------------------------------------------------- dashboard
with tab_dashboard:
    controls = st.columns([1, 1])
    run_clicked = controls[0].button(
        "🚀 Run scan", type="primary", width="stretch", disabled=not online
    )
    refresh_clicked = controls[1].button("🔄 Refresh", width="stretch", disabled=not online)

    if refresh_clicked and online:
        try:
            st.session_state.active_run = api.latest_run()
            st.session_state.flash = "Loaded the latest saved run."
            st.rerun()
        except ApiError as exc:
            st.error(str(exc))

    if run_clicked and online:
        run_scan(api, st.session_state.settings, sample_mode)

    if online:
        try:
            live_status = api.run_status()
        except ApiError:
            live_status = {}
        if live_status.get("status") == "running":
            st.info(
                f"Scan in progress: {live_status.get('message', '')} "
                f"({live_status.get('progress', 0)}%). Refresh to update."
            )

    run = st.session_state.active_run
    if not run:
        st.markdown("### No results yet")
        st.markdown(
            "Press **Run scan** to fetch tenders. For a quick first look, leave "
            "*Use sample tenders* on in the sidebar."
        )
    else:
        render_run_dashboard(run, api)

# ------------------------------------------------------------------------ settings
with tab_settings:
    st.markdown("### Search settings")
    st.caption(
        "These settings are stored in `data/settings.json` and mirrored to the "
        "Settings tab when you export to Google Sheets."
    )
    states = meta.get("states") or INDIAN_STATES
    current_region = settings.get("region", "All India")
    region_options = ["All India"] + states
    region_index = region_options.index(current_region) if current_region in region_options else 0

    with st.form("settings_form"):
        st.markdown("#### Location & limits")
        loc_cols = st.columns(3)
        region = loc_cols[0].selectbox("Region", region_options, index=region_index)
        preferred_states = loc_cols[1].multiselect(
            "Preferred states (score bonus)",
            states,
            default=[s for s in settings.get("preferred_states", []) if s in states],
        )
        bid_types = loc_cols[2].multiselect(
            "Bid type", BID_TYPES, default=settings.get("bid_types", [])
        )

        value_cols = st.columns(4)
        max_value_it = value_cols[0].number_input(
            "Max IT value (₹)",
            min_value=0,
            step=50_000,
            value=int(settings.get("max_value_it", 2_500_000)),
            help=f"Currently {format_lakh(settings.get('max_value_it', 2_500_000))}",
        )
        max_value_other = value_cols[1].number_input(
            "Max other value (₹)",
            min_value=0,
            step=25_000,
            value=int(settings.get("max_value_other", 500_000)),
            help=f"Currently {format_lakh(settings.get('max_value_other', 500_000))}",
        )
        max_emd = value_cols[2].number_input(
            "Max EMD (₹)",
            min_value=0,
            step=5_000,
            value=int(settings.get("max_emd", 50_000)),
            help=f"Currently {format_lakh(settings.get('max_emd', 50_000))}",
        )
        max_pages = value_cols[3].number_input(
            "GeM pages to fetch",
            min_value=1,
            max_value=50,
            value=int(settings.get("max_pages", 5)),
            help="Each page usually contains 10 bids.",
        )

        timing_cols = st.columns(3)
        min_days = timing_cols[0].number_input(
            "Min days remaining",
            min_value=0,
            max_value=120,
            value=int(settings.get("min_days_remaining", 7)),
        )
        min_score = timing_cols[1].number_input(
            "Minimum score",
            min_value=0,
            max_value=100,
            value=int(settings.get("min_score", 25)),
        )
        st.caption(
            f"Value caps: IT {format_lakh(max_value_it)} • Other {format_lakh(max_value_other)} "
            f"• EMD {format_lakh(max_emd)}"
        )

        st.markdown("#### Categories")
        cat_cols = st.columns(2)
        categories_it = cat_cols[0].multiselect(
            "IT categories",
            IT_CATEGORIES,
            default=[c for c in settings.get("categories_it", IT_CATEGORIES) if c in IT_CATEGORIES],
        )
        categories_other = cat_cols[1].multiselect(
            "Other categories",
            OTHER_CATEGORIES,
            default=[c for c in settings.get("categories_other", OTHER_CATEGORIES) if c in OTHER_CATEGORIES],
        )

        st.markdown("#### Keywords")
        st.caption("One keyword or phrase per line. Keywords add score; they do not replace categories.")
        kw_cols = st.columns(2)
        keywords_it = kw_cols[0].text_area(
            "IT keywords",
            value="\n".join(settings.get("keywords_it", [])),
            height=220,
        )
        keywords_other = kw_cols[1].text_area(
            "Other keywords",
            value="\n".join(settings.get("keywords_other", [])),
            height=220,
        )
        exclude_keywords = st.text_area(
            "Exclude keywords",
            value="\n".join(settings.get("exclude_keywords", [])),
            height=120,
            help="Any tender whose title or category contains one of these is dropped.",
        )

        with st.expander("PDF, AI and Google Sheets"):
            advanced_cols = st.columns(3)
            enable_pdf = advanced_cols[0].toggle(
                "Read tender PDFs", value=bool(settings.get("enable_pdf", True))
            )
            enable_ai = advanced_cols[1].toggle(
                "AI summaries", value=bool(settings.get("enable_ai_summary", True))
            )
            enable_sheet = advanced_cols[2].toggle(
                "Export to Google Sheets", value=bool(settings.get("enable_google_sheets", False))
            )
            top_cols = st.columns(2)
            parse_top_n = top_cols[0].number_input(
                "PDFs to parse per run",
                min_value=0,
                max_value=100,
                value=int(settings.get("parse_pdf_top_n", 10)),
            )
            summarize_top_n = top_cols[1].number_input(
                "Tenders to summarise with AI",
                min_value=0,
                max_value=100,
                value=int(settings.get("summarize_top_n", 10)),
            )
            sheet_id = st.text_input(
                "Google Sheet ID or URL",
                value=settings.get("sheet_id", ""),
                help="Leave blank to use GOOGLE_SHEET_ID from .env",
            )
            sheet_tab = st.text_input(
                "Results tab name", value=settings.get("sheet_tab", "Tenders")
            )

        submitted = st.form_submit_button("💾 Save settings", type="primary")

    if submitted:
        payload = {
            **settings,
            "region": region,
            "preferred_states": preferred_states,
            "bid_types": bid_types,
            "max_value_it": int(max_value_it),
            "max_value_other": int(max_value_other),
            "max_emd": int(max_emd),
            "min_days_remaining": int(min_days),
            "min_score": int(min_score),
            "max_pages": int(max_pages),
            "categories_it": categories_it,
            "categories_other": categories_other,
            "keywords_it": [line.strip() for line in keywords_it.splitlines() if line.strip()],
            "keywords_other": [line.strip() for line in keywords_other.splitlines() if line.strip()],
            "exclude_keywords": [line.strip() for line in exclude_keywords.splitlines() if line.strip()],
            "enable_pdf": enable_pdf,
            "enable_ai_summary": enable_ai,
            "enable_google_sheets": enable_sheet,
            "parse_pdf_top_n": int(parse_top_n),
            "summarize_top_n": int(summarize_top_n),
            "sheet_id": sheet_id.strip(),
            "sheet_tab": sheet_tab.strip() or "Tenders",
        }
        try:
            st.session_state.settings = api.save_settings(payload)
            st.session_state.flash = "Settings saved."
            st.rerun()
        except ApiError as exc:
            st.error(str(exc))

    reset_cols = st.columns([1, 4])
    if reset_cols[0].button("Reset to defaults"):
        try:
            defaults = Settings().model_dump()
            st.session_state.settings = api.save_settings(defaults)
            st.session_state.flash = "Settings reset to defaults."
            st.rerun()
        except ApiError as exc:
            st.error(str(exc))

# ------------------------------------------------------------------------- history
with tab_history:
    st.markdown("### Saved runs")
    if not online:
        st.info("Start the backend to see run history.")
    else:
        try:
            runs = api.list_runs()
        except ApiError as exc:
            st.error(str(exc))
            runs = []
        if not runs:
            st.caption("No runs saved yet.")
        else:
            st.dataframe(
                [
                    {
                        "Run": run.get("run_id"),
                        "Started": run.get("started_at"),
                        "Status": run.get("status"),
                        "Source": run.get("source"),
                        "Fetched": run.get("total_fetched"),
                        "Matched": run.get("total_matched"),
                        "Seconds": run.get("duration_seconds"),
                    }
                    for run in runs
                ],
                hide_index=True,
                width="stretch",
            )
            run_ids = [run.get("run_id") for run in runs]
            chosen = st.selectbox("Choose a run", run_ids)
            if st.button("Load into dashboard", type="primary"):
                try:
                    st.session_state.active_run = api.get_run(chosen)
                    st.session_state.flash = f"Loaded run {chosen}."
                    st.rerun()
                except ApiError as exc:
                    st.error(str(exc))

# ---------------------------------------------------------------------------- help
with tab_help:
    st.markdown(
        """
### What happens when you press Run scan

1. **Fetch** — calls the GeM bid listing API with `requests`. If GeM blocks the request,
   the optional Playwright fallback can load the page in a headless browser.
2. **Normalize** — maps raw GeM fields to a single tender model (value, EMD, dates, buyer, state).
3. **Filter** — drops excluded keywords, tenders closing too soon, values above the IT/other
   cap, EMD above the cap, and tenders outside the selected region.
4. **Score** — adds points for category and keyword matches, preferred states, low EMD,
   and comfortable value; subtracts points for construction/civil work, high turnover,
   long experience, and OEM requirements. Results are sorted by score.
5. **Enrich** — opens the top tender PDFs with `pdfplumber`, extracts eligibility points,
   and refreshes the score with the parsed EMD/value.
6. **Summarise** — asks Groq for a 2–3 line summary when `GROQ_API_KEY` is set; otherwise
   builds a factual rule-based summary.
7. **Save & export** — stores the run in `data/runs/` and, if enabled, writes
   the Settings and results tabs to Google Sheets.

### Setup

```bash
cd C:\\projects\\gem_automation
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
python run_backend.py      # terminal 1
python run_frontend.py     # terminal 2
```

Full project documentation lives in `brain/index.html`.

### Environment variables (`.env`)

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Enables AI summaries (free Groq tier) |
| `GROQ_MODEL` | Defaults to `llama-3.3-70b-versatile` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to the service-account JSON **or** the JSON itself |
| `GOOGLE_SHEET_ID` | Default spreadsheet ID |
| `ALLOW_PLAYWRIGHT_FALLBACK` | `true` to try a headless browser when GeM blocks requests |
| `GEM_SAMPLE_FALLBACK` | `false` to fail instead of showing sample data when live fetch fails |
| `BRAIN_API_URL` | Frontend → backend URL (default `http://127.0.0.1:8000`) |

### Google Sheets setup

1. Create a Google Cloud service account and enable the Sheets + Drive APIs.
2. Download the JSON key and point `GOOGLE_SERVICE_ACCOUNT_JSON` at it.
3. Share the target spreadsheet with the service-account email as **Editor**.
4. Put the sheet ID in `GOOGLE_SHEET_ID` or in Settings → Google Sheet ID.

### Notes

- The GeM website is not an official public API; its endpoints can change or rate-limit.
  The app labels results as live/sample so demo data is never mistaken for real bids.
- Eligibility extraction is heuristic. Always verify turnover, experience, MSE/startup
  relaxation, and OEM requirements in the actual tender document before bidding.
- This tool is not affiliated with GeM.
        """
    )

st.markdown(
    "<div class='small-muted' style='margin-top:2rem'>GeM Tender Brain v1.0 • "
    "local-first • data stored in <code>data</code></div>",
    unsafe_allow_html=True,
)
