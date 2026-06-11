# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config_loader import get_config
from utils.schema import get_connection, init_db

def main():
    cfg = get_config()
    try:
        init_db(cfg.db_path)
        conn = get_connection(cfg.db_path)
        rows = conn.execute(
            "SELECT source, status, last_updated, record_count, error_message "
            "FROM source_meta ORDER BY source"
        ).fetchall()
        conn.close()

        if not rows:
            print("Database is empty. Please run update.bat first.")
        else:
            print(f"{'Source':<25} {'Status':<12} {'Last Updated':<20} {'Records':>10}")
            print("-" * 75)
            for r in rows:
                icons = {"ok": "[OK]", "error": "[ERR]", "never": "[---]", "stale": "[OLD]"}
                icon = icons.get(r[1], "?")
                last = (r[2] or "N/A")[:16]
                print(f"{r[0]:<25} {icon} {r[1]:<8} {last:<20} {r[3] or 0:>10,}")
        print()
        print(f"DB: {cfg.db_path}")
    except Exception as e:
        print(f"Error: {e}")
        print("Please run update.bat to initialize the database.")

if __name__ == "__main__":
    main()
