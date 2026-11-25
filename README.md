# GeM Tender Brain

Automates the boring part of finding GeM tenders: fetch bids, drop the irrelevant ones,
score the rest against the company's limits, read the tender PDFs, and write a clean
sheet with a short summary and the eligibility points that need checking.

- **Backend** — Python + FastAPI (`backend/`)
- **Frontend** — Python + Streamlit (`frontend/`)
- **Storage** — local JSON in `data/` (no database needed)
- **Export** — Google Sheets via `gspread`, plus CSV download
- **Product docs** — the full PRD lives in [`brain/index.html`](brain/index.html)

> Not affiliated with GeM. The GeM website does not publish an official API, so live
> fetching can break or be rate-limited; results are clearly labelled as live or sample.

---

## Quick start

```powershell
cd C:\projects\gem_automation

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# Optional: add GROQ_API_KEY and Google credentials to .env

python run_backend.py      # terminal 1 → http://127.0.0.1:8000
python run_frontend.py     # terminal 2 → http://127.0.0.1:8501
```

Open <http://localhost:8501>. The **Use sample tenders** toggle is on by default, so the
first run works instantly without contacting GeM. Turn it off for a live scan.

The backend API docs are at <http://127.0.0.1:8000/docs>.

---

## What the app does

### 1. Configure parameters

Everything from the original brief is editable in the UI (and mirrored to the Google
Sheets **Settings** tab on export):

- IT / other categories and keywords
- Region and preferred states
- Maximum IT value (default ₹25 lakh), maximum other value (₹5 lakh)
- Maximum EMD (₹50,000)
- Minimum days remaining (7)
- Excluded keywords (construction, civil, furniture, vehicle hire, security guards, …)
- Bid type (product/service)
- PDF parsing and AI summary depth

### 2. Fetch

`backend/gem_client.py` calls the GeM bid listing endpoint with browser-like headers.
If GeM blocks the request, it can optionally use Playwright (headless browser). If live
fetching still fails, it falls back to a realistic offline dataset and labels the run
`sample` — never silently mixing demo data with live bids.

### 3. Filter and score

Hard filters drop excluded keywords, tenders closing too soon, values above the relevant
cap, EMD above the cap, and tenders outside the selected region.

Surviving tenders get an explainable score (shown per tender in the UI):

| Signal | Effect |
|---|---|
| Relevant category match | +10 |
| IT focus | +5 |
| Configured category hit | +22 |
| Keyword matches | up to +33 |
| Preferred state | +14 |
| Comfortable value / low or zero EMD | +1 to +8 |
| Good time to prepare | +4 |
| Construction, civil, furniture, security, housekeeping, vehicle hire | −25 to −45 |
| High turnover requirement | −7 to −25 |
| Long experience / OEM authorisation | −4 to −8 |

Tenders below the minimum score are hidden, and the rest are sorted by score.

### 4. Read the PDF

For the top N matches, `backend/pdf_parser.py` resolves the tender document, downloads
it with a size cap, extracts text using `pdfplumber`, and pulls out:

- experience requirement
- turnover requirement
- MSE / startup relaxation mentions
- OEM / authorisation requirements
- offer validity, EMD, estimated value

The score is refreshed after parsing because the PDF often contains the real EMD/value.

### 5. Summarise

If `GROQ_API_KEY` is set, `backend/summarizer.py` asks Groq for a 2–3 line factual
summary. Without a key (or if Groq fails), it builds a rule-based summary from the
tender fields. Summaries never invent eligibility claims.

### 6. Output

- Dashboard table with search, group/state filters, and a minimum-score slider
- Tender detail card with summary, eligibility checks, score breakdown, and links
- CSV download
- Optional Google Sheets export: **Settings** tab + results tab

---

## Project layout

```
gem_automation/
├── backend/
│   ├── main.py          FastAPI app and routes
│   ├── pipeline.py      Run orchestration + background RunManager
│   ├── gem_client.py    GeM fetch, Playwright fallback, normalization
│   ├── scoring.py       Classification, hard filters, explainable scoring
│   ├── pdf_parser.py    PDF download + eligibility extraction
│   ├── summarizer.py    Groq summaries with rule-based fallback
│   ├── sheets.py        Google Sheets export
│   ├── storage.py       Atomic JSON storage for settings and runs
│   ├── sample_data.py   Offline demo dataset
│   ├── models.py        Pydantic models
│   ├── constants.py     Categories, keywords, states
│   ├── utils.py         Currency/date parsing and formatting
│   └── cli.py           Command-line runner (used by GitHub Actions)
├── frontend/
│   ├── app.py           Streamlit UI
│   └── api_client.py    HTTP client for the backend
├── tests/               Unit + end-to-end sample run tests
├── deploy/              GitHub Actions workflow template
├── data/                settings.json + runs/ (created at runtime)
├── brain/               PRD and product documentation (index.html)
├── requirements.txt
├── requirements-dev.txt
├── requirements-optional.txt
├── .env.example
├── run_backend.py
├── run_frontend.py
└── run_once.py
```

---

## Configuration

Copy `.env.example` to `.env` in the project root and fill in what you need.

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Enables AI summaries (Groq free tier) |
| `GROQ_MODEL` | Default `llama-3.3-70b-versatile` |
| `GROQ_MAX_TOKENS` | Completion budget, default `800` (reasoning models need headroom) |
| `GROQ_REASONING_EFFORT` | `low` by default; only sent for `gpt-oss` models |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to service-account JSON **or** the JSON string |
| `GOOGLE_SHEET_ID` | Default spreadsheet ID |
| `ALLOW_PLAYWRIGHT_FALLBACK` | `true` to try a headless browser when blocked |
| `GEM_SAMPLE_FALLBACK` | `false` to fail loudly instead of showing sample data |
| `GEM_SAMPLE_MODE` | `true` to force sample mode |
| `BRAIN_API_URL` | Frontend → backend URL |
| `BRAIN_HOST` / `BRAIN_PORT` | Backend bind address |
| `GEM_DATA_DIR` | Override where settings and runs are stored |

### Google Sheets

1. Create a Google Cloud service account and enable the **Google Sheets API**
   (Drive API is only needed if scripts should create spreadsheets).
2. Download the JSON key.
3. Share the target spreadsheet with the service-account email (`client_email` in the
   key) as **Editor**. Viewer is not enough — the export clears and rewrites the tabs.
4. Set `GOOGLE_SERVICE_ACCOUNT_JSON` to the key path (or paste the JSON for CI).
5. Set `GOOGLE_SHEET_ID`, or enter the sheet ID in **Settings → Google Sheet ID**.
6. Turn on **Export to Google Sheets** in Settings.

Verify with `python -m backend.cli export`. A `403 The caller does not have permission`
means step 3 was missed (or the invite went to a human address instead of the robot one).
The full walkthrough and error table live in `brain/index.html#service-account`.

The export creates the **Settings** and **Tenders** tabs if they do not exist and
overwrites their contents on each run. The app's **Settings** tab is the source of truth;
the sheet's Settings tab is a readable mirror, so editing the sheet does not change the
filters used by the next run.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Backend status |
| GET | `/api/meta` | Categories, states, capability flags |
| GET / PUT | `/api/settings` | Read / save search settings |
| POST | `/api/run` | Start a scan (`{"settings": {...}, "use_sample": false}`) |
| GET | `/api/run/status` | Poll progress |
| GET | `/api/runs` | Recent run summaries |
| GET | `/api/runs/latest` | Latest full run |
| GET | `/api/runs/{run_id}` | One full run |
| POST | `/api/export` | Re-export a run to Google Sheets |

Scans run in a background thread, so the UI can poll progress without blocking.

---

## Command line / GitHub Actions

```powershell
cd C:\projects\gem_automation
python -m backend.cli run --sample --csv artifacts/tenders.csv
python -m backend.cli run --no-pdf --no-ai        # fastest live run
python -m backend.cli run --sheet                 # live + Google Sheets
python -m backend.cli export --run-id 20261125T101500-abc123
```

`deploy/github-actions-gem-tenders.yml` is a manual-trigger (`workflow_dispatch`)
workflow. Copy it to `.github/workflows/gem-tenders.yml` in the repository root and add
these repository secrets:

- `GROQ_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON` (the JSON itself, on one line)
- `GOOGLE_SHEET_ID`

The workflow uploads the generated CSV as an artifact.

---

## Tests

```powershell
cd C:\projects\gem_automation
pip install -r requirements-dev.txt
python -m pytest
```

The suite covers currency/date parsing, filtering, scoring, the FastAPI endpoints, and a
full sample-mode pipeline run (no network required).

---

## Optional Playwright fallback

```powershell
pip install -r requirements-optional.txt
playwright install chromium
```

Then set `ALLOW_PLAYWRIGHT_FALLBACK=true` in `.env`. The fallback opens GeM in a headless
Chromium context and calls the same listing endpoint from inside the browser session.

---

## Limitations and good practice

- GeM's private endpoints can change without notice. If live fetching stops working, use
  sample mode to keep testing the rest of the pipeline and update `gem_client.py`.
- Eligibility extraction is heuristic. Always verify turnover, experience, MSE/startup
  relaxation, and OEM requirements in the actual tender document.
- Keep request volume low (`max_pages`) and respect GeM's terms of use.
- Credentials belong in `.env` locally and in GitHub Secrets for CI — never in code.
- Results are saved locally in `data/runs/`; delete old runs whenever you like.
