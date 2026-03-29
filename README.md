# Bet Analysis Pipeline

Reads betting data from a Google Sheet, runs performance analysis, and writes results to an output Google Sheet.

## Setup

1. **Install Python** from [python.org](https://www.python.org/downloads/) — check "Add Python to PATH" during install - (you've already done this)
2. **Install dependencies** — open a terminal in this folder and run:
   ```
   pip install -r requirements.txt
   ```
   (you can just open this folder in VSCode, click the Terminal tab --> New Terminal, and run it there)
3. **Edit `pipeline.py`** — paste your Google Sheet URLs into `SOURCE_SHEET_URL` and `OUTPUT_SHEET_URL` at the top of the file

## Running

Double-click **`run.bat`**.

On first run, a browser window will open asking you to sign in with Google. You'll see an "This app isn't verified" warning — click **Advanced > Go to [app name]** to proceed. This is a one-time step; a `token.json` is saved locally for future runs.

## Output

Two tabs are written to the output Google Sheet:
- **Performance Summary** — weighted stake analysis (by odds band, edge band, bet type, stake band)
- **Flat Stake Summary** — flat stake analysis with filtered odds range

Both tabs are overwritten on each run.
