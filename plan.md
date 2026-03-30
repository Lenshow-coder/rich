# Automated Pipeline Plan

## Goal
Replace the manual notebook workflow (CSV in → analysis → CSV out) with a one-click pipeline that reads from a live Google Sheet, cleans and analyzes the data in memory, and writes results to a separate output Google Sheet. Built for someone else to run on their own machine on-demand.

## Architecture

```
Google Sheet (source data)
        |
   Python script (pipeline.py)
   - authenticates via OAuth (user's own Google account)
   - reads the "Bet Tracker" sheet via gspread
   - coerces types (Sheets returns strings, not numbers/NaN)
   - cleans & analyzes in memory (no intermediate files)
   - writes summary to output Google Sheet (one tab per summary)
   - logs results to pipeline.log
        |
   run.bat (double-click to run)
```

## Auth approach: OAuth (user login)

Using OAuth instead of a service account because someone else is running this:
- First run opens a browser → "Sign in with Google" → done
- Token is cached locally and auto-refreshes
- No raw credential files to protect or hand off
- No need to share sheets with a service account email — the script uses their own Google permissions

Requires creating an **OAuth Client ID** (type: Desktop App) in Google Cloud Console. The resulting `client_secret.json` identifies the app, not a key — safe to hand off.

**First-run UX note:** The user will see Google's "This app isn't verified" warning screen. This is normal for personal/internal apps. They click **Advanced → Go to [app name]** to proceed. One-time thing.

## Steps

### 1. Google Cloud setup (one-time)
- Go to Google Cloud Console → create a project
- Enable the **Google Sheets API** and **Google Drive API**
- Create an **OAuth Client ID** (Application type: Desktop App)
- Download `client_secret.json` and place it in the project directory
- Add the user's Google account as a test user on the OAuth consent screen
- **Publish the app to Production:** OAuth consent screen → click "Publish App". This avoids the 7-day token expiry that "Testing" mode enforces. No Google review needed for under 100 users — takes effect immediately.

### 2. Convert notebook to script
- Extract cleaning/analysis logic from `lenny-analysis/lenny-analysis.ipynb` into `pipeline.py`
- Replace `pd.read_csv('data.csv')` with a `gspread` call to pull from the "Bet Tracker" tab of the source Sheet
- Replace `combined_flat.to_csv(...)` with a `gspread` call to write to the output Sheet
- Keep all intermediate DataFrames in memory — no temp CSV files
- **Add explicit type coercion after reading from Sheets** — `get_all_records()` returns strings and empty strings instead of NaN. Numeric columns (`LineTaken`, `Edge`, `RichStake`, `Market`, `Other`, etc.) must be converted with `pd.to_numeric(..., errors='coerce')`, and empty strings replaced with NaN, or the cleaning/analysis logic will break.

### 3. Key code pattern
```python
import gspread
import pandas as pd
import logging

logging.basicConfig(filename='pipeline.log', level=logging.INFO,
                    format='%(asctime)s %(message)s')

# Auth (opens browser on first run, then uses cached token)
gc = gspread.oauth(
    credentials_filename='client_secret.json',
    authorized_user_filename='token.json'
)

# Read
source = gc.open("Your Source Sheet").worksheet("Bet Tracker")
df = pd.DataFrame(source.get_all_records())
logging.info(f"Read {len(df)} rows from source sheet")

# Coerce types (Sheets returns everything as strings)
df = df.replace('', pd.NA)
numeric_cols = ['LineTaken', 'Edge', 'RichStake', 'Market', 'Other', ...]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# ... existing cleaning & analysis logic (all in memory) ...

# Write
output = gc.open("Your Output Sheet").sheet1
output.clear()
output.update([combined_flat.columns.tolist()] + combined_flat.values.tolist())
logging.info("Wrote results to output sheet")
```

### 4. Deliverables to hand off
- `pipeline.py` — the script
- `client_secret.json` — OAuth app identity
- `requirements.txt` — `gspread`, `pandas`, `google-auth-oauthlib`
- `run.bat` — one-click runner with Python fallback:
  ```bat
  @echo off
  python pipeline.py 2>NUL || py pipeline.py
  pause
  ```
- `.gitignore` — excludes `token.json`, `client_secret.json`, `pipeline.log`
- Brief README with: install Python (check "Add to PATH"), `pip install -r requirements.txt`, double-click `run.bat`

### 5. Output sheet decision (needs input)
The notebook produces two summary tables:
- `performance_summary.csv` — weighted stake analysis
- `flat_stake_performance.csv` — flat stake analysis

Options:
- **One tab each** in the output sheet (cleanest)
- **One stacked table** in a single tab
- Confirm with the user which summaries they want

### 6. Assumptions
- The source Google Sheet has a tab called **"Bet Tracker"** — this is the only tab the pipeline reads
- Row 1 of "Bet Tracker" contains unique column headers matching the CSV layout
- No merged cells or extra title rows in "Bet Tracker"
- The output sheet is machine-only — `clear()` + `update()` wipes all formatting and manual notes each run

## Friend's setup steps (for reference)

### One-time setup
1. **Install Python** — download from python.org, check "Add Python to PATH" during install
2. **Install dependencies** — open a terminal in the project folder, run `pip install -r requirements.txt`
3. **Place `client_secret.json`** — you give him this file (created from your Google Cloud Console), he puts it in the project folder
4. **First run — authenticate** — double-click `run.bat`, a browser opens:
   - He'll see Google's "This app isn't verified" screen
   - Click **Advanced → Go to [app name]**
   - Sign in with his Google account and grant access
   - A `token.json` is saved locally — he won't need to do this again

### Every subsequent run
- Double-click `run.bat`
- Results appear in the output Google Sheet

### What to give him
Only 4 files — zip and send. The notebook and analysis CSVs stay in your repo as reference; the cleaning/analysis logic is ported directly into `pipeline.py`.
- `pipeline.py`
- `client_secret.json`
- `requirements.txt`
- `run.bat`

### What's on your side (not his)
- Google Cloud project creation
- Enabling Sheets API and Drive API
- Creating the OAuth Client ID
- Publishing the app to Production
- Handing him the `client_secret.json` + project folder

## GUI for filter management

Add a tkinter GUI so the user can adjust filters (sport, year, book) without editing `pipeline.py`. Sheet URLs stay hardcoded in the script — not part of the GUI.

- **Preset system:** A `presets.json` file stores named filter configurations (e.g. "Basketball 2026", "All Sports 2025-2026"). The GUI has a dropdown to pick a preset, which populates the filter fields. Users can save new presets and delete existing ones from the GUI.
- **Settings persistence:** Last-used filters are saved automatically so they persist across runs.
- **Run button:** Triggers the pipeline directly from the GUI with the selected filters.

## What to avoid
- **Service accounts** — awkward to hand off credentials to another person
- **Scheduled runs (Task Scheduler)** — unnecessary; on-demand via `run.bat` is simpler and avoids wake/sleep issues
- **Raw `google-api-python-client`** — verbose; `gspread` wraps it cleanly
- **Intermediate CSV files** — keep everything in memory within the pipeline
