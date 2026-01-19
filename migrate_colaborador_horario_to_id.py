import sqlite3
from pathlib import Path

DB_PATH = Path("data/ezpoint.db")

def main():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("PRAGMA foreign_keys = OFF;")

        # 1) criar tabela nova no modelo certo
        con.execute("""
            CREATE TABLE IF NOT EXISTS colaborador_horario_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              colaborador_id INTEGER NOT NULL,
              horario_id INTEGER NOT NULL,
              vigencia_inicio TEXT NOT NULL DEFAULT (date('now')),
              vigencia_fim TEXT,
              FOREIGN KEY (colaborador_id) REFERENCES colaborador(id) ON DELETE CASCADE,
              FOREIGN KEY (horario_id) REFERENCES horario(id) ON DELETE RESTRICT
            );
        """)

        # 2) descobrir se existe coluna antiga colaborador_matricula
        cols = [row[1] for row in con.execute("PRAGMA table_info(colaborador_horario);").fetchall()]

        if "colaborador_matricula" in cols:
            # 2a) copiar convertendo matricula -> colaborador.id
            con.execute("""
                INSERT INTO colaborador_horario_new (id, colaborador_id, horario_id, vigencia_inicio, vigencia_fim)
                SELECT ch.id,
                       c.id as colaborador_id,
                       ch.horario_id,
                       ch.vigencia_inicio,
                       ch.vigencia_fim
                FROM colaborador_horario ch
                JOIN colaborador c ON c.matricula = ch.colaborador_matricula;
            """)
        else:
            # 2b) se já era colaborador_id, só copia
            con.execute("""
                INSERT INTO colaborador_horario_new (id, colaborador_id, horario_id, vigencia_inicio, vigencia_fim)
                SELECT id, colaborador_id, horario_id, vigencia_inicio, vigencia_fim
                FROM colaborador_horario;
            """)

        # 3) renomear
        con.execute("ALTER TABLE colaborador_horario RENAME TO colaborador_horario_old;")
        con.execute("ALTER TABLE colaborador_horario_new RENAME TO colaborador_horario;")

        # 4) recriar índices
        con.execute("CREATE INDEX IF NOT EXISTS idx_colab_hor_colab ON colaborador_horario(colaborador_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_colab_hor_hor ON colaborador_horario(horario_id);")

        con.execute("PRAGMA foreign_keys = ON;")
        con.commit()

    print("✅ Migração concluída: colaborador_horario agora usa colaborador_id.")

if __name__ == "__main__":
    main()
