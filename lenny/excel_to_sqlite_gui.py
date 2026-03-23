"""
Excel -> SQLite Converter GUI
- Lists .xlsx/.xlsm/.xls files in the SAME directory as this script (not Windows/system32)
- Lets you choose one from a dropdown
- "Convert to DB" applies the same conversion logic we used earlier:
    * Read first sheet (sheet_name=0)
    * Strip column name whitespace
    * Write full DataFrame to SQLite table 'bets' (replace)
    * Create indexes if columns exist:
        - idx_main_filters on (Book, Sport, Rich Stake) if present (composite)
        - idx_date on Date if present
- Outputs SQLite file to the same directory with a unique timestamped name

Requirements:
  pip install pandas openpyxl
"""

import os
import sys
import sqlite3
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

def script_dir() -> str:
    """Directory where the script file lives (works even when launched from elsewhere)."""
    return os.path.dirname(os.path.abspath(sys.argv[0]))

def list_excel_files(folder: str):
    exts = (".xlsx", ".xlsm", ".xls")
    files = []
    try:
        for name in os.listdir(folder):
            if name.lower().endswith(exts) and os.path.isfile(os.path.join(folder, name)):
                files.append(name)
    except Exception:
        return []
    files.sort(key=lambda s: s.lower())
    return files

def now_stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def conversion_logic(excel_path: str, out_db_path: str) -> tuple[int, int, list[str]]:
    """Applies the exact same conversion logic as earlier. Returns (rows, cols, colnames)."""
    try:
        import pandas as pd
    except Exception as e:
        raise RuntimeError(
            "Missing dependency: pandas.\n\nInstall with:\n  pip install pandas openpyxl\n\n"
            f"Details: {e}"
        )

    df = pd.read_excel(excel_path, sheet_name=0)
    df.columns = [str(c).strip() for c in df.columns]

    conn = sqlite3.connect(out_db_path)
    try:
        table_name = "bets"
        df.to_sql(table_name, conn, if_exists="replace", index=False)

        cols = set(df.columns)
        idx_sql = []
        if "Book" in cols:
            idx_sql.append('"Book"')
        if "Sport" in cols:
            idx_sql.append('"Sport"')
        if "Rich Stake" in cols:
            idx_sql.append('"Rich Stake"')
        if idx_sql:
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_main_filters ON {table_name}({",".join(idx_sql)});')
        if "Date" in cols:
            conn.execute(f'CREATE INDEX IF NOT EXISTS idx_date ON {table_name}("Date");')

        conn.commit()
    finally:
        conn.close()

    return int(df.shape[0]), int(df.shape[1]), list(df.columns)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Excel → SQLite DB Converter")
        self.geometry("700x320")
        self.resizable(False, False)

        self.folder = script_dir()

        hdr = ttk.Frame(self, padding=10)
        hdr.pack(fill="x")
        ttk.Label(hdr, text="Excel → SQLite DB Converter", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(hdr, text=f"Working folder: {self.folder}", foreground="#666666").pack(anchor="w", pady=(4,0))

        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Choose an Excel file from this folder:").grid(row=0, column=0, sticky="w")

        self.file_var = tk.StringVar()
        self.combo = ttk.Combobox(main, textvariable=self.file_var, state="readonly", width=70)
        self.combo.grid(row=1, column=0, sticky="w", pady=(6,0))

        btns = ttk.Frame(main)
        btns.grid(row=2, column=0, sticky="w", pady=(10,0))

        self.refresh_btn = ttk.Button(btns, text="Refresh list", command=self.refresh_files)
        self.refresh_btn.pack(side="left")

        self.convert_btn = ttk.Button(btns, text="Convert to DB", command=self.convert)
        self.convert_btn.pack(side="left", padx=(10,0))

        self.status = tk.Text(main, height=8, width=82, wrap="word")
        self.status.grid(row=3, column=0, sticky="w", pady=(12,0))
        self.status.configure(state="disabled")

        self.refresh_files()

    def log(self, msg: str):
        self.status.configure(state="normal")
        self.status.insert("end", msg + "\n")
        self.status.see("end")
        self.status.configure(state="disabled")

    def refresh_files(self):
        files = list_excel_files(self.folder)
        self.combo["values"] = files
        if files:
            current = self.file_var.get()
            if current in files:
                self.combo.set(current)
            else:
                self.combo.current(0)
            self.convert_btn.configure(state="normal")
            self.log(f"Found {len(files)} Excel file(s).")
        else:
            self.file_var.set("")
            self.convert_btn.configure(state="disabled")
            self.log("No Excel files found in this folder. Put .xlsx/.xlsm files next to this .py and click Refresh.")

    def convert(self):
        fname = self.file_var.get().strip()
        if not fname:
            messagebox.showwarning("No file selected", "Please select an Excel file first.")
            return

        excel_path = os.path.join(self.folder, fname)
        if not os.path.exists(excel_path):
            messagebox.showerror("File not found", f"Could not find:\n{excel_path}")
            return

        base = os.path.splitext(os.path.basename(fname))[0]
        out_name = f"{base}_full_{now_stamp()}.sqlite"
        out_path = os.path.join(self.folder, out_name)

        self.log(f"Converting: {excel_path}")
        self.log(f"Output DB: {out_path}")

        try:
            rows, cols, colnames = conversion_logic(excel_path, out_path)
        except Exception as e:
            messagebox.showerror("Conversion failed", str(e))
            self.log(f"ERROR: {e}")
            return

        self.log(f"SUCCESS: wrote table 'bets' with {rows:,} rows and {cols} columns.")
        self.log("Indexes created (if columns exist): idx_main_filters(Book,Sport,Rich Stake), idx_date(Date).")
        self.log(f"Columns: {', '.join(colnames)}")
        messagebox.showinfo("Done", f"Created:\n{out_path}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
