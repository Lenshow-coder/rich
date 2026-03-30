# Bet Analysis Pipeline

Reads betting data from a Google Sheet, runs performance analysis, and writes results to an output Google Sheet.

## Setup

1. **Install Python** — Mac comes with Python 3 pre-installed. To check, open Terminal and run `python3 --version`. If it's not installed, download from [python.org](https://www.python.org/downloads/)
2. **Install dependencies** — open Terminal, `cd` into this folder, and run:
   ```
   pip3 install -r requirements.txt
   ```
3. **Edit `pipeline.py`** — paste your Google Sheet URLs into `SOURCE_SHEET_URL` and `OUTPUT_SHEET_URL` at the top of the file

## Running

Open Terminal, `cd` into this folder, and run:
```
./run.sh
```
If you get a "permission denied" error on the first try, run `chmod +x run.sh` first, then `./run.sh` again.

On first run, a browser window will open asking you to sign in with Google. You'll see an "This app isn't verified" warning — click **Advanced > Go to [app name]** to proceed. This is a one-time step; a `token.json` is saved locally for future runs.

## Output

Two tabs are written to the output Google Sheet:
- **Performance Summary** — weighted stake analysis (by odds band, edge band, bet type, stake band)
- **Flat Stake Summary** — flat stake analysis with filtered odds range

Both tabs are overwritten on each run.
