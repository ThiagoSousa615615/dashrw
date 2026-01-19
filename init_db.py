import sqlite3
from pathlib import Path

DB_PATH = Path("data/ezpoint.db")
SCHEMA_PATH = Path("schema.sql")

def main():
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    print("✅ Banco criado com sucesso")

if __name__ == "__main__":
    main()
