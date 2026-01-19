import sqlite3
from pathlib import Path

DB_PATH = Path("data/ezpoint.db")

def main():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = OFF;")

        # 1) criar tabela nova com id
        con.execute("""
            CREATE TABLE IF NOT EXISTS colaborador_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              matricula TEXT UNIQUE,
              nome_completo TEXT NOT NULL,
              ativo INTEGER NOT NULL DEFAULT 1,
              criado_em TEXT NOT NULL DEFAULT (datetime('now')),
              atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)

        # 2) copiar dados do colaborador antigo (sem id) para o novo
        # Ajuste os nomes das colunas conforme seu schema atual
        con.execute("""
            INSERT INTO colaborador_new (matricula, nome_completo, ativo, criado_em, atualizado_em)
            SELECT matricula, nome_completo, ativo,
                   COALESCE(criado_em, datetime('now')),
                   COALESCE(atualizado_em, datetime('now'))
            FROM colaborador;
        """)

        # 3) renomear tabelas
        con.execute("ALTER TABLE colaborador RENAME TO colaborador_old;")
        con.execute("ALTER TABLE colaborador_new RENAME TO colaborador;")

        con.execute("PRAGMA foreign_keys = ON;")
        con.commit()

    print("✅ Migração concluída: colaborador agora tem coluna id.")

if __name__ == "__main__":
    main()
