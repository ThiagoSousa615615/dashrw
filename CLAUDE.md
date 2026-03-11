# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the main dashboard
streamlit run app.py

# Initialize the SQLite database from schema
python init_db.py
```

The `.env` file must be loaded with `encoding="utf-8"` — the file is saved in UTF-8 and credentials may contain special characters like `¨`, `#`, `%`.

## Architecture

This is a two-page Streamlit app that monitors employee time-punching against expected work schedules, integrated with the **EzPoint WEB** time-clock API.

### Pages

- **`app.py`** — Main dashboard (TV-mode). Fetches today's punches from the EzPoint API, compares them against each employee's scheduled shifts, and renders a color-coded HTML table. Auto-refreshes every `AUTO_REFRESH_SEC` seconds (default 30). The admin correction panel (inside an expander) allows punches to be flagged as ignored.
- **`pages/1_admin_app.py`** — Admin panel. Manages shifts (`horario`), per-day-of-week schedule grids (`horario_dia`), employee-shift links (`colaborador_horario`), and syncs employees from the EzPoint API.

### Key modules

- **`ezpoint_web.py`** — HTTP client for `https://api.ezpointweb.com.br/ezweb-ws`. Handles JWT auth (POST `/login`), fetches employees (GET `/funcionario`), and paginates time punches (GET `/batida`). The API has a ~30 req/min limit; the client adds a 0.25s sleep between pages. Ver documentação completa da API: [`ezpoint_api_documentacao.md`](ezpoint_api_documentacao.md).
- **`db.py`** — SQLite connection helper. DB file lives at `data/ezpoint.db`.

### Database schema (`data/ezpoint.db`)

`schema.sql` está desatualizado. A estrutura real do banco foi extraída diretamente de `data/ezpoint.db`.

> Tabelas `colaborador_old` e `colaborador_horario_old` são legado das migrations e estão vazias — não são usadas pelo app.

---

#### `colaborador` — 33 linhas

| Coluna | Tipo | Obrigatório | Default | Descrição |
|---|---|---|---|---|
| `id` | INTEGER | PK | autoincrement | Chave primária interna |
| `matricula` | TEXT | UNIQUE | — | Matrícula da API EzPoint |
| `nome_completo` | TEXT | NOT NULL | — | Nome completo |
| `ativo` | INTEGER | NOT NULL | `1` | 1 = ativo, 0 = inativo |
| `criado_em` | TEXT | NOT NULL | `datetime('now')` | ISO datetime |
| `atualizado_em` | TEXT | NOT NULL | `datetime('now')` | ISO datetime |

---

#### `horario` — 2 linhas

| Coluna | Tipo | Obrigatório | Default | Descrição |
|---|---|---|---|---|
| `id` | INTEGER | PK | autoincrement | — |
| `nome` | TEXT | NOT NULL UNIQUE | — | Ex.: `"Padrão"`, `"Comercial"` |
| `entrada1` | TEXT | NOT NULL | — | HH:MM — início do turno 1 |
| `saida1` | TEXT | NOT NULL | — | HH:MM — fim do turno 1 |
| `entrada2` | TEXT | — | NULL | HH:MM — início do turno 2 (intervalo) |
| `saida2` | TEXT | — | NULL | HH:MM — fim do turno 2 |
| `ativo` | INTEGER | NOT NULL | `1` | 1 = ativo |

Dados atuais: `(1, 'Padrão', '08:00', '12:00', '13:00', '17:00')` · `(2, 'Comercial', '07:00', '11:00', '12:00', '16:00')`

---

#### `horario_dia` — 14 linhas

Grade semanal por horário. Sobrescreve os horários padrão da tabela `horario` para um dia específico da semana. Todos os campos de hora `NULL` = folga explícita.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|---|---|---|---|---|
| `id` | INTEGER | PK | autoincrement | — |
| `horario_id` | INTEGER | NOT NULL | — | FK → `horario.id` (CASCADE DELETE) |
| `dia_semana` | INTEGER | NOT NULL | — | 0=Segunda … 6=Domingo |
| `entrada1` | TEXT | — | NULL | HH:MM |
| `saida1` | TEXT | — | NULL | HH:MM |
| `entrada2` | TEXT | — | NULL | HH:MM (opcional) |
| `saida2` | TEXT | — | NULL | HH:MM (opcional) |

**UNIQUE** em `(horario_id, dia_semana)`. Índice: `idx_horario_dia(horario_id, dia_semana)`.

Exemplo de dados (horario_id=2 "Comercial"):

| dia_semana | entrada1 | saida1 | entrada2 | saida2 |
|---|---|---|---|---|
| 0–1 (Seg-Ter) | 08:00 | 11:00 | 12:00 | 17:00 |
| 2–4 (Qua-Sex) | 07:00 | 11:00 | 12:00 | 18:00 |
| 5 (Sáb) | 07:00 | 12:00 | NULL | NULL |
| 6 (Dom) | NULL | NULL | NULL | NULL (folga) |

---

#### `colaborador_horario` — 5 linhas

Histórico temporal de vínculos colaborador ↔ horário. Registro com `vigencia_fim IS NULL` = vínculo atual.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|---|---|---|---|---|
| `id` | INTEGER | PK | autoincrement | — |
| `colaborador_id` | INTEGER | NOT NULL | — | FK → `colaborador.id` (CASCADE DELETE) |
| `horario_id` | INTEGER | NOT NULL | — | FK → `horario.id` (RESTRICT DELETE) |
| `vigencia_inicio` | TEXT | NOT NULL | `date('now')` | ISO date de início |
| `vigencia_fim` | TEXT | — | NULL | ISO date de encerramento; NULL = vigente |

Ao vincular um novo horário, o registro anterior recebe `vigencia_fim = date('now')` e um novo é inserido.

---

#### `batida_override` — 3 linhas

Batidas marcadas pelo admin para serem ignoradas no cálculo do dashboard.

| Coluna | Tipo | Obrigatório | Default | Descrição |
|---|---|---|---|---|
| `id` | INTEGER | PK | autoincrement | — |
| `matricula` | TEXT | NOT NULL | — | Matrícula do colaborador (texto, igual à API) |
| `data` | TEXT | NOT NULL | — | ISO date `YYYY-MM-DD` |
| `hora` | TEXT | NOT NULL | — | `HH:MM:SS` |
| `acao` | TEXT | NOT NULL | `'IGNORAR'` | Sempre `'IGNORAR'` atualmente |
| `motivo` | TEXT | — | NULL | Justificativa informada pelo admin |
| `criado_em` | TEXT | NOT NULL | `datetime('now')` | ISO datetime |

**UNIQUE** em `(matricula, data, hora, acao)`. Índice: `idx_batida_override_lookup(matricula, data)`.

---

#### Relacionamentos

```
horario (id) ←──── horario_dia (horario_id)      [CASCADE DELETE]
horario (id) ←──── colaborador_horario (horario_id) [RESTRICT DELETE]
colaborador (id) ←─ colaborador_horario (colaborador_id) [CASCADE DELETE]
```

### Punch analysis logic (`app.py`)

1. Loads employees + current shift from DB (`load_colabs_with_shift`)
2. Fetches today's punches from API (`fetch_batidas_do_dia`, cached 20s via `@st.cache_data`)
3. Loads admin overrides and filters them out (`get_overrides_do_dia`, `group_batidas_by_matricula`)
4. For each employee, resolves the active shift for today's weekday: first checks `horario_dia` for a per-day entry, falls back to the shift's default times
5. Matches punches positionally (1st punch → ENTRADA_1, 2nd → SAIDA_1, etc.) via `analyze_employee_day`
6. Applies `DEFAULT_TOL_MIN` tolerance per punch and `INTERVAL_TOL_MIN` for the break interval
7. Renders HTML table with `tooltip_cell` (hover reveals details) using `st.markdown(..., unsafe_allow_html=True)`

### Environment variables (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `EZPOINT_EMPRESA` | — | API company identifier |
| `EZPOINT_USUARIO` | — | API username |
| `EZPOINT_SENHA` | — | API password |
| `TOL_MIN` | `10` | Tolerance in minutes per punch |
| `INTERVAL_TOL_MIN` | `10` | Tolerance for break interval |
| `AUTO_REFRESH_SEC` | `30` | Dashboard auto-refresh interval |
