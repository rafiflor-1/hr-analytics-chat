"""Convert the HR Excel workbook into one Parquet file per table.

Usage:  python build_data.py path/to/HR_Demo_Model.xlsx

The app reads the Parquet files in ./data, so this only needs to be re-run
when the source workbook changes.
"""
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"


def main(xlsx_path: str) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    sheets = pd.read_excel(xlsx_path, sheet_name=None)
    for name, df in sheets.items():
        df.columns = [str(c).strip().lower() for c in df.columns]
        out = DATA_DIR / f"{name.upper()}.parquet"
        df.to_parquet(out, index=False)
        print(f"{name:<34} {len(df):>8,} rows -> {out.name}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
