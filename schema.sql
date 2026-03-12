PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- colaborador
-- Funcionários sincronizados via EzPoint WEB (/funcionario).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS colaborador (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  matricula     TEXT    UNIQUE,
  nome_completo TEXT    NOT NULL,
  ativo         INTEGER NOT NULL DEFAULT 1,
  criado_em     TEXT    NOT NULL DEFAULT (datetime('now')),
  atualizado_em TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
-- horario
-- Template de turno com horários padrão (fallback).
-- entrada2/saida2 opcionais (turno único = apenas entrada1/saida1).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS horario (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  nome     TEXT    NOT NULL UNIQUE,
  entrada1 TEXT    NOT NULL,  -- HH:MM
  saida1   TEXT    NOT NULL,  -- HH:MM
  entrada2 TEXT,              -- HH:MM, NULL = sem segundo turno
  saida2   TEXT,              -- HH:MM, NULL = sem segundo turno
  ativo    INTEGER NOT NULL DEFAULT 1
);

-- ------------------------------------------------------------
-- horario_dia
-- Grade semanal por dia da semana para um horario.
-- Sobrescreve os campos do horario pai para o dia específico.
-- Todos os campos de hora NULL = folga explícita naquele dia.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS horario_dia (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  horario_id  INTEGER NOT NULL,
  dia_semana  INTEGER NOT NULL,  -- 0=Segunda ... 6=Domingo
  entrada1    TEXT,              -- HH:MM
  saida1      TEXT,              -- HH:MM
  entrada2    TEXT,              -- HH:MM, NULL = turno único ou folga
  saida2      TEXT,              -- HH:MM, NULL = turno único ou folga
  UNIQUE (horario_id, dia_semana),
  FOREIGN KEY (horario_id) REFERENCES horario(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_horario_dia
  ON horario_dia(horario_id, dia_semana);

-- ------------------------------------------------------------
-- colaborador_horario
-- Histórico temporal de vínculos colaborador <-> horario.
-- vigencia_fim IS NULL = vínculo vigente.
-- Ao trocar de horário: setar vigencia_fim no registro atual
-- e inserir novo registro.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS colaborador_horario (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  colaborador_id   INTEGER NOT NULL,
  horario_id       INTEGER NOT NULL,
  vigencia_inicio  TEXT    NOT NULL DEFAULT (date('now')),
  vigencia_fim     TEXT,
  FOREIGN KEY (colaborador_id) REFERENCES colaborador(id) ON DELETE CASCADE,
  FOREIGN KEY (horario_id)     REFERENCES horario(id)     ON DELETE RESTRICT
);

-- ------------------------------------------------------------
-- batida_override
-- Batidas marcadas pelo admin para serem ignoradas no dashboard.
-- acao = 'IGNORAR' (único valor usado atualmente).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS batida_override (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  matricula  TEXT    NOT NULL,
  data       TEXT    NOT NULL,  -- YYYY-MM-DD
  hora       TEXT    NOT NULL,  -- HH:MM:SS
  acao       TEXT    NOT NULL DEFAULT 'IGNORAR',
  motivo     TEXT,
  criado_em  TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (matricula, data, hora, acao)
);

CREATE INDEX IF NOT EXISTS idx_batida_override_lookup
  ON batida_override(matricula, data);

-- ------------------------------------------------------------
-- email_destinatario
-- Destinatários do relatório diário enviado por e-mail.
-- ativo = 0 pausa o envio sem excluir o cadastro.
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- usuarios
-- Usuários com acesso ao dashboard. Admin inicial criado via
-- migrate_add_usuarios.py com senha padrão Tecbio2026
-- (primeiro_acesso=1 força troca na primeira entrada).
-- ------------------------------------------------------------
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
