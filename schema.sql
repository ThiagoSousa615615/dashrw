PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS colaborador (
  matricula TEXT PRIMARY KEY,
  nome_completo TEXT NOT NULL,
  ativo INTEGER NOT NULL DEFAULT 1,
  criado_em TEXT NOT NULL DEFAULT (datetime('now')),
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS horario (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE,
  entrada1 TEXT NOT NULL,  -- HH:MM
  saida1   TEXT NOT NULL,
  entrada2 TEXT,           -- pode ser NULL
  saida2   TEXT
);

CREATE TABLE IF NOT EXISTS colaborador_horario (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  colaborador_matricula TEXT NOT NULL,
  horario_id INTEGER NOT NULL,
  vigencia_inicio TEXT NOT NULL DEFAULT (date('now')),
  vigencia_fim TEXT,
  FOREIGN KEY (colaborador_matricula) REFERENCES colaborador(matricula),
  FOREIGN KEY (horario_id) REFERENCES horario(id)
);

CREATE INDEX IF NOT EXISTS idx_colab_hor_colab
  ON colaborador_horario(colaborador_matricula);

CREATE INDEX IF NOT EXISTS idx_colab_hor_hor
  ON colaborador_horario(horario_id);
