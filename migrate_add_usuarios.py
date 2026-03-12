"""
migrate_add_usuarios.py — Cria a tabela `usuarios` e insere o admin inicial.

Uso:
    python migrate_add_usuarios.py

Requer ADMIN_EMAIL configurado no .env antes de executar.
"""

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(encoding="utf-8")

DB_PATH = Path("data/ezpoint.db")


def main() -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "").strip()
    if not admin_email:
        print("ERRO: ADMIN_EMAIL não configurado no .env. Adicione e tente novamente.")
        raise SystemExit(1)

    import bcrypt
    senha_hash = bcrypt.hashpw(b"Tecbio2026", bcrypt.gensalt()).decode("utf-8")

    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = ON;")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS usuarios (
              id               INTEGER PRIMARY KEY AUTOINCREMENT,
              username         TEXT    NOT NULL UNIQUE,
              email            TEXT    NOT NULL UNIQUE,
              senha_hash       TEXT    NOT NULL,
              primeiro_acesso  INTEGER NOT NULL DEFAULT 1,
              ativo            INTEGER NOT NULL DEFAULT 1,
              criado_em        TEXT    NOT NULL DEFAULT (datetime('now')),
              atualizado_em    TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
        con.commit()

        count = con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if count == 0:
            con.execute(
                """INSERT INTO usuarios (username, email, senha_hash, primeiro_acesso)
                   VALUES (?, ?, ?, 1)""",
                ("admin", admin_email, senha_hash),
            )
            con.commit()
            print(f"Admin criado: username=admin, email={admin_email}, senha=Tecbio2026 (troque no primeiro acesso).")
        else:
            print("Tabela usuarios já contém registros — admin não foi reinserido.")

    print("Migração concluída: tabela usuarios pronta.")


if __name__ == "__main__":
    main()
