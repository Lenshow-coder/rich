"""
pipeline.py — Automated betting analysis pipeline.
Reads from a Google Sheet, analyzes performance, writes results to an output sheet.
"""

import gspread
import pandas as pd
import numpy as np
import re
import logging
import sys

# ─── Configuration ─────────────────────────────────────────────
SOURCE_SHEET_URL  = "https://docs.google.com/spreadsheets/d/YOUR_SOURCE_SHEET_ID/edit"
SOURCE_TAB_NAME   = "Bet Tracker"      # Tab within the source sheet
OUTPUT_SHEET_URL  = "https://docs.google.com/spreadsheets/d/YOUR_OUTPUT_SHEET_ID/edit"
SKIP_ROWS         = 6                  # Junk rows before the header row in the source sheet
BETTYPE_COL_INDEX = 12                 # 0-based index of the unnamed BetType column
SPORT_FILTER      = ["Basketball"]       # e.g. ["Basketball", "NFL", "NHL"]
YEAR_FILTER       = [2026]               # e.g. [2025, 2026]
BOOK_FILTER       = []                   # e.g. ["MBmb", "FDmb"] — empty list = all books

# ─── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    filename='pipeline.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler(sys.stdout))


# ─── Google Sheets I/O ─────────────────────────────────────────

def authenticate():
    """Authenticate with Google via OAuth (opens browser on first run)."""
    gc = gspread.oauth(
        credentials_filename='client_secret.json',
        authorized_user_filename='token.json',
    )
    log.info("Authenticated with Google")
    return gc


def read_source(gc):
    """Read data from the source Google Sheet and return a DataFrame."""
    sheet = gc.open_by_url(SOURCE_SHEET_URL).worksheet(SOURCE_TAB_NAME)
    raw = sheet.get_all_values()
    log.info(f"Read {len(raw)} raw rows from source sheet / '{SOURCE_TAB_NAME}'")

    # Skip junk rows; use next row as headers
    headers = [h.strip() for h in raw[SKIP_ROWS]]
    data = raw[SKIP_ROWS + 1:]

    # Name the unnamed BetType column
    if BETTYPE_COL_INDEX < len(headers) and headers[BETTYPE_COL_INDEX] == '':
        headers[BETTYPE_COL_INDEX] = 'BetType'

    # De-duplicate column names (e.g. two "Date" columns → Date, Date.1)
    seen = {}
    unique_headers = []
    for h in headers:
        if h in seen:
            unique_headers.append(f"{h}.{seen[h]}")
            seen[h] += 1
        else:
            unique_headers.append(h)
            seen[h] = 1

    df = pd.DataFrame(data, columns=unique_headers)
    df = df.replace('', np.nan).dropna(how='all').reset_index(drop=True)
    log.info(f"Parsed {len(df)} data rows with {len(unique_headers)} columns")
    return df


def write_output(gc, performance, flat_stake):
    """Write results to the output Google Sheet — one tab per summary."""
    try:
        output = gc.open_by_url(OUTPUT_SHEET_URL)
    except gspread.SpreadsheetNotFound:
        log.error(f"Output sheet not found — check OUTPUT_SHEET_URL")
        raise SystemExit(1)

    def write_tab(name, df):
        df = df.fillna('')
        # Convert numpy types to native Python for gspread
        rows = df.values.tolist()
        rows = [[x.item() if hasattr(x, 'item') else x for x in row] for row in rows]
        try:
            ws = output.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = output.add_worksheet(name, rows=len(rows) + 5, cols=len(df.columns) + 2)
        ws.clear()
        ws.update(values=[df.columns.tolist()] + rows)
        log.info(f"Wrote '{name}' tab ({len(rows)} rows)")

    write_tab("Performance Summary", performance)
    write_tab("Flat Stake Summary", flat_stake)

    # Remove default Sheet1 if it exists, is empty, and isn't the only tab
    try:
        default = output.worksheet("Sheet1")
        if len(output.worksheets()) > 1 and (default.row_count <= 1 or not any(default.row_values(1))):
            output.del_worksheet(default)
    except gspread.WorksheetNotFound:
        pass


# ─── Data loading & cleaning ──────────────────────────────────

def coerce_types(df):
    """Convert string values from Sheets to proper Python types."""

    def clean_currency(val):
        if pd.isna(val):
            return np.nan
        s = str(val).replace('$', '').replace(',', '').strip()
        if s == '' or s == '-':
            return np.nan
        try:
            return float(s)
        except ValueError:
            return np.nan

    def clean_percent(val):
        if pd.isna(val):
            return np.nan
        s = str(val).replace('%', '').strip()
        if s == '':
            return np.nan
        try:
            return float(s)
        except ValueError:
            return np.nan

    # Plain numeric columns
    for col in ['Market', 'Other', 'LineTaken', 'TrueL', 'Decim', 'Betsize']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Percentage columns (strip %)
    for col in ['Edge']:
        if col in df.columns:
            df[col] = df[col].apply(clean_percent)

    # Currency columns (strip $, commas)
    for col in ['Rich Stake', 'Other Stake', 'Total Stake', 'Net', 'ExpWinPlace']:
        if col in df.columns:
            df[col] = df[col].apply(clean_currency)

    # Date columns
    for col in ['Date', 'Date.1']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    return df


def add_derived_columns(df):
    """Add Team, Total, and Unique Bet Rule 1 columns (mirrors notebook Cell 3)."""

    # Total: True if BetType is "total"
    df['Total'] = df['BetType'].astype(str).str.strip().str.lower() == 'total'

    # Team: extract from Bet column
    def extract_team(row):
        bet = str(row['Bet'])
        if row['Total']:
            m = re.search(r'\d', bet)
            return bet[:m.start()].strip() if m else bet.strip()
        else:
            m = re.search(r' ml| -| \+', bet)
            return bet[:m.start()].strip() if m else bet.strip()

    df['Team'] = df.apply(extract_team, axis=1)

    # Unique Bet Rule 1: counter that increments when Team, Total, or Date differ
    counter = 1
    rule1 = [counter]
    for i in range(1, len(df)):
        same = (df.iloc[i]['Team'] == df.iloc[i - 1]['Team']
                and df.iloc[i]['Total'] == df.iloc[i - 1]['Total']
                and df.iloc[i]['Date'] == df.iloc[i - 1]['Date'])
        if not same:
            counter += 1
        rule1.append(counter)
    df['Unique Bet Rule 1'] = rule1

    return df


def clean_data(df):
    """Drop unnecessary columns (mirrors notebook Cell 4)."""
    drop_cols = [c for c in ['Time', 'Ignore', 'Ignore.1'] if c in df.columns]
    df.drop(columns=drop_cols, inplace=True, errors='ignore')

    null_cols = [c for c in df.columns if df[c].isna().all()]
    if null_cols:
        log.info(f"Dropping {len(null_cols)} fully null columns")
        df.drop(columns=null_cols, inplace=True)

    if 'Grade' in df.columns:
        df['Grade'] = df['Grade'].astype('category')

    return df


# ─── Analysis ─────────────────────────────────────────────────

def build_analysis_df(df):
    """Filter to sport/year and prepare analysis columns (mirrors notebook Cell 5)."""
    mask = df['Sport'].isin(SPORT_FILTER) & df['Date'].dt.year.isin(YEAR_FILTER)
    if BOOK_FILTER:
        mask = mask & df['Book'].isin(BOOK_FILTER)
    bdf = df[mask].copy()
    log.info(f"Filtered to {SPORT_FILTER} {YEAR_FILTER} (books: {'all' if not BOOK_FILTER else BOOK_FILTER}): {len(bdf)} rows")

    if len(bdf) == 0:
        log.warning("No rows match the filter — check SPORT_FILTER / YEAR_FILTER / BOOK_FILTER")
        return bdf

    bdf = bdf[['Unique Bet Rule 1', 'Team', 'Bet', 'Date', 'Book', 'Market',
                'Other', 'LineTaken', 'Edge', 'BetType', 'Rich Stake', 'Grade']].copy()

    bdf.rename(columns={
        'Unique Bet Rule 1': 'Bet',
        'Bet': 'ExactBet',
        'Rich Stake': 'RichStake',
    }, inplace=True)

    # Edge is already a percentage from the sheet (e.g. 22.83 = 22.83%)
    bdf['Edge'] = bdf['Edge'].round(1)
    bdf['RichStake'] = bdf['RichStake'].round(2)

    bdf['ExpProfit'] = (bdf['RichStake'] * bdf['Edge'] / 100).round(0).astype(int)

    def calc_profit(row):
        if row['Grade'] == 'P':
            return 0.0
        if row['Grade'] == 'L':
            return -row['RichStake']
        odds = row['LineTaken']
        stake = row['RichStake']
        return stake * (odds / 100) if odds > 0 else stake * (100 / abs(odds))

    bdf['Profit'] = bdf.apply(calc_profit, axis=1).astype(int)
    log.info(f"{len(bdf)} bets | Total Profit: ${bdf['Profit'].sum():,}")
    return bdf


def merge_bets(bdf):
    """Merge rows sharing the same Bet ID (mirrors notebook Cell 6)."""

    def american_to_decimal(odds):
        if odds > 0:
            return (odds / 100) + 1
        elif odds < 0:
            return (100 / abs(odds)) + 1
        return 2.0

    def decimal_to_american(dec):
        if dec >= 2.0:
            return round((dec - 1) * 100)
        return round(-100 / (dec - 1))

    def median_odds(series):
        return decimal_to_american(series.apply(american_to_decimal).median())

    def grade_agg(grades):
        unique = grades.unique()
        return unique[0] if len(unique) == 1 else 'mix'

    merged = bdf.groupby('Bet').agg(
        Team=('Team', 'first'),
        ExactBet=('ExactBet', 'first'),
        Date=('Date', 'first'),
        Book=('Book', lambda x: ', '.join(x.unique())),
        Market=('Market', median_odds),
        Other=('Other', median_odds),
        LineTaken=('LineTaken', median_odds),
        Edge=('Edge', 'median'),
        BetType=('BetType', 'first'),
        RichStake=('RichStake', 'sum'),
        Grade=('Grade', grade_agg),
        Profit=('Profit', 'sum'),
    ).reset_index()

    merged['Edge'] = merged['Edge'].round(1)
    merged['RichStake'] = merged['RichStake'].round(2)
    log.info(f"Merged: {len(bdf)} rows -> {len(merged)} unique bets")
    return merged


# ─── Performance summaries ─────────────────────────────────────

def _summarize_weighted(group):
    staked = group['RichStake'].sum()
    exp_profit = group['ExpProfit'].sum()
    return pd.Series({
        'Bets': int(len(group)),
        'Wins': int((group['Grade'] == 'W').sum()),
        'Win%': round((group['Grade'] == 'W').mean() * 100, 1),
        'Staked': int(staked),
        'ExpProfit': int(exp_profit),
        'Profit': int(group['Profit'].sum()),
        'ExpROI%': round(exp_profit / staked * 100, 1) if staked else 0,
        'ROI%': round(group['Profit'].sum() / staked * 100, 1) if staked else 0,
    })


def _int_cols(summary):
    for col in ['Bets', 'Wins', 'Staked', 'ExpProfit', 'Profit']:
        if col in summary.columns:
            summary[col] = summary[col].astype(int)
    return summary


def build_performance_summary(bdf, merged):
    """Build the weighted-stake performance summary table (mirrors notebook Cells 7-9)."""
    cdf = bdf[bdf['Grade'] != 'P'].copy()
    blank = pd.DataFrame([{}])

    # By Odds Band
    cdf['OddsBand'] = pd.cut(cdf['LineTaken'],
                              bins=[-999999, -150, -100, 150, 999999],
                              labels=['-150 or less', '-150 to -100', '+100 to +150', '+150 or greater'])
    odds = _int_cols(cdf.groupby('OddsBand', observed=False)
                     .apply(_summarize_weighted, include_groups=False).reset_index()
                     .rename(columns={'OddsBand': 'Bucket'}))
    odds.insert(0, 'Group', 'Odds Band')

    # By Edge Band
    cdf['EdgeBand'] = pd.cut(cdf['Edge'],
                              bins=[0, 5, 10, 15, float('inf')],
                              labels=['0-5%', '5-10%', '10-15%', '15%+'])
    edge = _int_cols(cdf.groupby('EdgeBand', observed=False)
                     .apply(_summarize_weighted, include_groups=False).reset_index()
                     .rename(columns={'EdgeBand': 'Bucket'}))
    edge.insert(0, 'Group', 'Edge Band')

    # By BetType
    core = cdf[cdf['BetType'].isin(['moneyline', 'spread', 'total'])]
    bettype = _int_cols(core.groupby('BetType')
                        .apply(_summarize_weighted, include_groups=False).reset_index()
                        .rename(columns={'BetType': 'Bucket'}))
    bettype.insert(0, 'Group', 'Bet Type')

    # Grand Totals
    totals = _int_cols(_summarize_weighted(cdf).to_frame().T.assign(Bucket='All'))
    totals.insert(0, 'Group', 'Grand Total')

    # By Stake Band (from merged data)
    mdf = merged[merged['Grade'] != 'P'].copy()
    mdf['ExpProfit'] = (mdf['RichStake'] * mdf['Edge'] / 100).round(0).astype(int)
    mdf['StakeBand'] = pd.cut(mdf['RichStake'],
                               bins=[0, 500, 1000, 2000, float('inf')],
                               labels=['0-500', '500-1000', '1000-2000', '2000+'])
    stake = _int_cols(mdf.groupby('StakeBand', observed=False)
                      .apply(_summarize_weighted, include_groups=False).reset_index()
                      .rename(columns={'StakeBand': 'Bucket'}))
    stake.insert(0, 'Group', 'Stake Band')

    combined = pd.concat([odds, blank, edge, blank, bettype, blank, totals,
                          blank, blank, stake], ignore_index=True)
    cols = ['Group', 'Bucket'] + [c for c in combined.columns if c not in ('Group', 'Bucket')]
    return combined[cols]


def build_flat_stake_summary(merged):
    """Build flat-stake performance summary (mirrors notebook Cell 10)."""
    fdf = merged[~merged['Grade'].isin(['P', 'mix'])].copy()
    fdf = fdf[(fdf['LineTaken'] > -150) & (fdf['LineTaken'] < 300)].copy()
    log.info(f"Flat stake analysis: {len(fdf)} bets after filtering")

    fdf['RichStake'] = 1
    fdf['ExpProfit'] = (fdf['Edge'] / 100).round(4)

    def calc_profit_flat(row):
        if row['Grade'] == 'L':
            return -1.0
        odds = row['LineTaken']
        return odds / 100 if odds > 0 else 100 / abs(odds)

    fdf['Profit'] = fdf.apply(calc_profit_flat, axis=1)

    def summarize_flat(group):
        staked = group['RichStake'].sum()
        exp_profit = group['ExpProfit'].sum()
        return pd.Series({
            'Bets': int(len(group)),
            'Wins': int((group['Grade'] == 'W').sum()),
            'Win%': round((group['Grade'] == 'W').mean() * 100, 1),
            'Staked': int(staked),
            'ExpProfit': round(exp_profit, 2),
            'Profit': round(group['Profit'].sum(), 2),
            'ExpROI%': round(exp_profit / staked * 100, 1) if staked else 0,
            'ROI%': round(group['Profit'].sum() / staked * 100, 1) if staked else 0,
        })

    def int_cols_flat(s):
        for col in ['Bets', 'Wins', 'Staked']:
            if col in s.columns:
                s[col] = s[col].astype(int)
        return s

    blank = pd.DataFrame([{}])

    # By Odds Band (narrower range — extremes already filtered)
    fdf['OddsBand'] = pd.cut(fdf['LineTaken'],
                              bins=[-150, -100, 150, 300],
                              labels=['-150 to -100', '+100 to +150', '+151 to +300'])
    f_odds = int_cols_flat(fdf.groupby('OddsBand', observed=False)
                           .apply(summarize_flat, include_groups=False).reset_index()
                           .rename(columns={'OddsBand': 'Bucket'}))
    f_odds.insert(0, 'Group', 'Odds Band')

    # By Edge Band
    fdf['EdgeBand'] = pd.cut(fdf['Edge'],
                              bins=[0, 5, 10, 15, float('inf')],
                              labels=['0-5%', '5-10%', '10-15%', '15%+'])
    f_edge = int_cols_flat(fdf.groupby('EdgeBand', observed=False)
                           .apply(summarize_flat, include_groups=False).reset_index()
                           .rename(columns={'EdgeBand': 'Bucket'}))
    f_edge.insert(0, 'Group', 'Edge Band')

    # By BetType
    core = fdf[fdf['BetType'].isin(['moneyline', 'spread', 'total'])]
    f_bettype = int_cols_flat(core.groupby('BetType')
                              .apply(summarize_flat, include_groups=False).reset_index()
                              .rename(columns={'BetType': 'Bucket'}))
    f_bettype.insert(0, 'Group', 'Bet Type')

    # Grand Totals
    f_totals = int_cols_flat(summarize_flat(fdf).to_frame().T.assign(Bucket='All'))
    f_totals.insert(0, 'Group', 'Grand Total')

    combined = pd.concat([f_odds, blank, f_edge, blank, f_bettype, blank, f_totals],
                         ignore_index=True)
    cols = ['Group', 'Bucket'] + [c for c in combined.columns if c not in ('Group', 'Bucket')]
    return combined[cols]


# ─── Main ──────────────────────────────────────────────────────

def _validate_config():
    """Exit early if placeholder URLs haven't been replaced."""
    for name, url in [("SOURCE_SHEET_URL", SOURCE_SHEET_URL),
                      ("OUTPUT_SHEET_URL", OUTPUT_SHEET_URL)]:
        if "YOUR_" in url:
            print(f"ERROR: {name} still contains a placeholder — paste the real Google Sheet URL.")
            raise SystemExit(1)


def main():
    _validate_config()
    log.info("=" * 50)
    log.info("Pipeline starting")

    gc = authenticate()

    # Read & clean
    df = read_source(gc)
    df = coerce_types(df)
    df = add_derived_columns(df)
    df = clean_data(df)

    # Analyze
    bdf = build_analysis_df(df)
    if len(bdf) == 0:
        log.error("No data after filtering — aborting")
        return

    merged = merge_bets(bdf)

    # Build summaries
    performance = build_performance_summary(bdf, merged)
    flat_stake = build_flat_stake_summary(merged)

    # Write to output sheet
    write_output(gc, performance, flat_stake)

    log.info("Pipeline complete")


if __name__ == '__main__':
    main()
