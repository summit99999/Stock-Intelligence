import glob
import sqlite3

for db_path in glob.glob("backend/data/*.db"):
    try:
        con = sqlite3.connect(db_path)
        cnt_ltm = con.execute("SELECT COUNT(*) FROM observed_intraday_ohlcv WHERE symbol in ('LTIM', 'LTM')").fetchone()[0]
        cnt_total = con.execute("SELECT COUNT(*) FROM observed_intraday_ohlcv").fetchone()[0]
        cnt_prov = con.execute("SELECT COUNT(*) FROM bar_provenance").fetchone()[0]
        print(f"{db_path}:\n  total observed={cnt_total}, total prov={cnt_prov}, ltm/ltim observed={cnt_ltm}")
    except Exception as e:
        print(f"{db_path}: {e}")
