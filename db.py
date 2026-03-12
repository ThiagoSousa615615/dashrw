import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "data/ezpoint.db"))

def get_con():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    return con
