import sqlite3
from pathlib import Path

DB_PATH = Path("data/ezpoint.db")

def main():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = ON;")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS email_destinatario (
              id            INTEGER PRIMARY KEY AUTOINCREMENT,
              email         TEXT    NOT NULL UNIQUE,
              nome          TEXT,
              ativo         INTEGER NOT NULL DEFAULT 1,
              criado_em     TEXT    NOT NULL DEFAULT (datetime('now')),
              atualizado_em TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_email_destinatario_ativo
              ON email_destinatario(ativo);
        """)
        con.commit()
    print("Migracao concluida: tabela email_destinatario criada.")

if __name__ == "__main__":
    main()
