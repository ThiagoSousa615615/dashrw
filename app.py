import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from streamlit_autorefresh import st_autorefresh
from typing import Set, Tuple


import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from ezpoint_web import EzPointWebClient

# Windows + .env com caracteres especiais:
load_dotenv(encoding="latin-1")

DB_PATH = Path("data/ezpoint.db")

# ----------------------------
# Regras (da sua doc)
# ----------------------------
DEFAULT_TOL_MIN = int(os.getenv("TOL_MIN", "10"))  # tolerância por batida (10 min)
INTERVAL_TOL_MIN = int(os.getenv("INTERVAL_TOL_MIN", "10"))  # tolerância do intervalo (ex.: 10)
AUTO_REFRESH_SEC = int(os.getenv("AUTO_REFRESH_SEC", "30"))  # tv refresh

# ----------------------------
# Modelos
# ----------------------------
@dataclass(frozen=True)
class Shift:
    start1: time
    end1: time
    start2: Optional[time]
    end2: Optional[time]

    def expected_marks(self, d: date) -> List[Tuple[str, datetime, str]]:
        events = [
            ("ENTRADA_1", datetime.combine(d, self.start1), "in"),
            ("SAIDA_1", datetime.combine(d, self.end1), "out"),
        ]
        if self.start2 and self.end2:
            events += [
                ("ENTRADA_2", datetime.combine(d, self.start2), "in"),
                ("SAIDA_2", datetime.combine(d, self.end2), "out"),
            ]
        return events

# ----------------------------
# Utilitários
# ----------------------------
def parse_hhmm(hhmm: Optional[str]) -> Optional[time]:
    if not hhmm:
        return None
    hhmm = hhmm.strip()
    h, m = hhmm.split(":")
    return time(int(h), int(m))

def minutes_diff(actual: datetime, expected: datetime) -> int:
    return int((actual - expected).total_seconds() // 60)

def get_overrides_do_dia(dia_str: str) -> set[tuple[str, str]]:
    # retorna {(matricula, "HH:MM:SS"), ...}
    with get_con() as con:
        rows = con.execute(
            "SELECT matricula, hora FROM batida_override WHERE data = ? AND acao = 'IGNORAR'",
            (dia_str,)
        ).fetchall()
    return {(str(m), str(h)) for (m, h) in rows}


def within_tolerance(delta_min: int, tol_min: int) -> bool:
    # Janela = [previsto - tol, previsto + tol] :contentReference[oaicite:7]{index=7}
    return (-tol_min <= delta_min <= tol_min)

def classify(kind: str, delta_min: int, tol_min: int) -> Tuple[str, bool]:
    """
    Retorna (label, ok)
    Se ok=False => vermelho; ok=True => verde
    Regras de classificação conforme doc :contentReference[oaicite:8]{index=8}
    """
    ok = within_tolerance(delta_min, tol_min)
    if ok:
        return ("OK", True)

    if kind == "in":
        return ("Entrada Antecipada" if delta_min < 0 else "Atrasado", False)
    if kind == "out":
        return ("Saída antecipada" if delta_min < 0 else "Saída excedida", False)

    return ("Fora do horário", False)

def fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return "-"
    return dt.strftime("%H:%M")

# ----------------------------
# DB
# ----------------------------
def get_con():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON;")
    return con

def load_colabs_with_shift() -> pd.DataFrame:
    """
    Traz colaborador + horário vigente.
    """
    with get_con() as con:
        df = pd.read_sql_query(
            """
            SELECT
              c.id AS colaborador_id,
              c.matricula,
              c.nome_completo,
              c.ativo,
              h.id AS horario_id,
              h.nome AS horario_nome,
              h.entrada1, h.saida1, h.entrada2, h.saida2
            FROM colaborador c
            LEFT JOIN colaborador_horario ch
              ON ch.colaborador_id = c.id AND ch.vigencia_fim IS NULL
            LEFT JOIN horario h
              ON h.id = ch.horario_id
            WHERE c.ativo = 1
            ORDER BY c.nome_completo
            """,
            con,
        )
    return df

# ----------------------------
# API (batidas do dia)
# ----------------------------
@st.cache_data(ttl=20)  # evita estourar 30 req/min :contentReference[oaicite:9]{index=9}
def fetch_batidas_do_dia(empresa: str, usuario: str, senha: str, dia: str) -> List[dict]:
    client = EzPointWebClient(empresa=empresa, usuario=usuario, senha=senha)
    return client.listar_batidas(data_inicio=dia, data_fim=dia)  # /batida :contentReference[oaicite:10]{index=10}



def group_batidas_by_matricula(
    batidas: List[dict],
    d: date,
    overrides: Set[Tuple[str, str]],
) -> Dict[str, List[datetime]]:


    """
    Retorna dict matricula -> [datetimes ordenados],
    ignorando batidas marcadas em overrides.
    overrides = {(matricula, "HH:MM:SS"), ...}
    """
    out: Dict[str, List[datetime]] = {}

    for b in batidas:
        mat = str(b.get("matriculaFuncionario") or "").strip()
        hora = str(b.get("hora") or "").strip()  # "HH:MM:SS"
        data_str = str(b.get("data") or "").strip()


        if not mat or not hora or not data_str:
            continue


        # ignora batidas marcadas pelo admin
        if (mat, hora) in overrides:
            continue

        try:
            hh, mm, ss = hora.split(":")
            dt = datetime.combine(d, time(int(hh), int(mm), int(ss)))
        except Exception:
            continue

        out.setdefault(mat, []).append(dt)

    for mat in out:
        out[mat] = sorted(out[mat])

    return out






# ----------------------------
# Cálculo (baseado na sua doc)
# ----------------------------
def analyze_employee_day(shift: Shift, punches: List[datetime], d: date, tol_min: int, interval_tol_min: int):
    """
    Mapeamento simples por ordem (1ª batida -> ENTRADA_1 etc), como no seu exemplo :contentReference[oaicite:12]{index=12}
    Retorna:
      - marks: lista por evento esperado: {code, expected, actual, delta, label, ok}
      - interval: {label, ok, expected_min, actual_min} opcional
    """
    expected = shift.expected_marks(d)
    punches = sorted(punches)

    marks = []
    for i, (code, exp_dt, kind) in enumerate(expected):
        act_dt = punches[i] if i < len(punches) else None
        if act_dt is None:
            marks.append({
                "code": code,
                "expected": fmt_dt(exp_dt),
                "actual": "-",
                "delta": None,
                "label": "Falta de batida",
                "ok": False,
            })
            continue

        delta = minutes_diff(act_dt, exp_dt)
        label, ok = classify(kind, delta, tol_min)
        marks.append({
            "code": code,
            "expected": fmt_dt(exp_dt),
            "actual": fmt_dt(act_dt),
            "delta": delta,
            "label": label,
            "ok": ok,
        })

    # Regra do intervalo (opcional) conforme sua doc :contentReference[oaicite:13]{index=13}
    interval_info = None
    if shift.start2 and shift.end2 and len(punches) >= 3:
        saida_1 = punches[1]
        entrada_2 = punches[2]
        intervalo_real = int((entrada_2 - saida_1).total_seconds() // 60)

        intervalo_previsto = int(
            (datetime.combine(d, shift.start2) - datetime.combine(d, shift.end1)).total_seconds() // 60
        )

        # Com tolerância: < previsto - tol => intervalo reduzido; > previsto + tol => excedido :contentReference[oaicite:14]{index=14}
        if intervalo_real < intervalo_previsto - interval_tol_min:
            interval_info = {
                "label": "Intervalo reduzido",
                "ok": False,
                "expected_min": intervalo_previsto,
                "actual_min": intervalo_real,
            }
        elif intervalo_real > intervalo_previsto + interval_tol_min:
            interval_info = {
                "label": "Intervalo excedido",
                "ok": False,
                "expected_min": intervalo_previsto,
                "actual_min": intervalo_real,
            }
        else:
            interval_info = {
                "label": "Intervalo OK",
                "ok": True,
                "expected_min": intervalo_previsto,
                "actual_min": intervalo_real,
            }

    return marks, interval_info

# ----------------------------
# UI
# ----------------------------
st.set_page_config(page_title="Dashboard — Apontamentos do Dia", layout="wide")
st.title("Dashboard — Horário x Apontamentos do dia")

st_autorefresh(
    interval=AUTO_REFRESH_SEC * 1000,
    key="tv_refresh"
)

empresa = os.getenv("EZPOINT_EMPRESA", "").strip()
usuario = os.getenv("EZPOINT_USUARIO", "").strip()
senha = os.getenv("EZPOINT_SENHA", "").strip()

if not (empresa and usuario and senha):
    st.error("Configure EZPOINT_EMPRESA, EZPOINT_USUARIO e EZPOINT_SENHA no .env.")
    st.stop()

d = date.today()
dia_str = d.isoformat()

# Auto refresh (TV)
st.caption(f"Data: {dia_str} | Tolerância: {DEFAULT_TOL_MIN} min (por batida) | Refresh: {AUTO_REFRESH_SEC}s")


colabs = load_colabs_with_shift()
if colabs.empty:
    st.warning("Nenhum colaborador ativo encontrado no banco.")
    st.stop()

table_placeholder = st.empty()

batidas = fetch_batidas_do_dia(empresa, usuario, senha, dia_str)

# 🔽 NOVO: buscar overrides do dia (1x só)
overrides = get_overrides_do_dia(dia_str)

# 🔽 NOVO: agrupar batidas já ignorando as marcadas
batidas_por_matricula = group_batidas_by_matricula(
    batidas,
    d,
    overrides
)

# ===============================
# 🔧 Correção de batidas (ADMIN)
# ===============================
with st.expander("⚙️ Correção de batidas (admin)", expanded=False):

    colabs_lista = colabs[["nome_completo", "matricula"]].dropna()

    nome_sel = st.selectbox(
        "Colaborador",
        colabs_lista["nome_completo"].tolist()
    )

    matricula_sel = str(
        colabs_lista.loc[
            colabs_lista["nome_completo"] == nome_sel,
            "matricula"
        ].iloc[0]
    )

    punches = batidas_por_matricula.get(matricula_sel, [])

    if not punches:
        st.info("Sem batidas hoje para este colaborador.")
    else:
        for p in punches:
            hora_str = p.strftime("%H:%M:%S")

            c1, c2, c3 = st.columns([2, 4, 2])
            c1.write(hora_str)

            motivo = c2.text_input(
                "Motivo",
                key=f"mot_{matricula_sel}_{hora_str}"
            )

            if c3.button(
                "Ignorar",
                key=f"ign_{matricula_sel}_{hora_str}"
            ):
                with get_con() as con:
                    con.execute(
                        """
                        INSERT OR IGNORE INTO batida_override
                        (matricula, data, hora, acao, motivo)
                        VALUES (?, ?, ?, 'IGNORAR', ?)
                        """,
                        (matricula_sel, dia_str, hora_str, motivo or None)
                    )
                    con.commit()

                st.success(f"Batida {hora_str} ignorada.")
                st.rerun()


rows = []
cell_meta = {}  # para colorir células específicas

for idx, r in colabs.iterrows():
    matricula = str(r["matricula"] or "").strip()
    nome = r["nome_completo"]
    horario_nome = r["horario_nome"] if pd.notna(r["horario_nome"]) else "SEM HORÁRIO"
    e1, s1, e2, s2 = r["entrada1"], r["saida1"], r["entrada2"], r["saida2"]

    if pd.isna(e1) or pd.isna(s1):
        # Sem horário vinculado => vermelho
        row = {
            "Matricula": matricula,
            "Nome": nome,
            "Horario": horario_nome,
            "E1": "-", "S1": "-", "E2": "-", "S2": "-",
            "B1": "-", "B2": "-", "B3": "-", "B4": "-",
            "Status": "SEM HORÁRIO (cadastre no admin)",
        }
        rows.append(row)
        continue

    shift = Shift(
        start1=parse_hhmm(e1),
        end1=parse_hhmm(s1),
        start2=parse_hhmm(e2) if pd.notna(e2) else None,
        end2=parse_hhmm(s2) if pd.notna(s2) else None,
    )

    punches = batidas_por_matricula.get(matricula, [])
    marks, interval_info = analyze_employee_day(shift, punches, d, DEFAULT_TOL_MIN, INTERVAL_TOL_MIN)

    # Monta colunas “B1..B4” mostrando batida real e marcação (OK / Atrasado etc.)
    b_cols = ["B1", "B2", "B3", "B4"]
    b_vals = {}
    any_red = False

    for i, bcol in enumerate(b_cols):
        if i < len(marks):
            m = marks[i]
            # exemplo: "08:11 (Atrasado)"
            suffix = m["label"]
            b_vals[bcol] = f"{m['actual']} ({suffix})"
            if not m["ok"]:
                any_red = True
                cell_meta[(idx, bcol)] = "red"
            else:
                cell_meta[(idx, bcol)] = "green"
        else:
            b_vals[bcol] = "-"

    # Intervalo curto/excedido também deve “puxar” vermelho, conforme sua regra opcional :contentReference[oaicite:15]{index=15}
    status_parts = []
    if interval_info is not None:
        status_parts.append(f"{interval_info['label']} ({interval_info['actual_min']}min)")
        if not interval_info["ok"]:
            any_red = True

    status = " | ".join(status_parts) if status_parts else ("OK" if not any_red else "FORA DA REGRA")

    row = {
        "Matricula": matricula,
        "Nome": nome,
        "Horario": f"{horario_nome} [{e1}-{s1}" + (f" / {e2}-{s2}]" if pd.notna(e2) and pd.notna(s2) else "]"),
        "E1": e1, "S1": s1, "E2": (e2 if pd.notna(e2) else "-"), "S2": (s2 if pd.notna(s2) else "-"),
        **b_vals,
        "Status": status,
    }
    rows.append(row)

df = pd.DataFrame(rows)

def style_df(data: pd.DataFrame):
    def color_cell(val: str, row_idx: int, col_name: str):
        # default: sem cor
        color = None
        # achar índice original (como iterrows idx)
        # aqui usamos posição do dataframe
        return ""

    styled = data.style

    # Aplica cor nos B1..B4 (verde/vermelho)
    def apply_colors(row):
        styles = [""] * len(row)
        # row.name é o índice do dataframe (0..n-1), mas nosso cell_meta foi indexado pelo idx original do iterrows
        # então vamos colorir por conteúdo: se contém "(OK)" -> verde, senão se contém "(" e != "-" -> vermelho/verde já definido no texto
        for j, col in enumerate(row.index):
            if col in ("B1", "B2", "B3", "B4"):
                v = str(row[col])
                if v == "-" or v.strip() == "":
                    continue
                if "(OK)" in v or "(Intervalo OK)" in v:
                    styles[j] = "color: green; font-weight: 700;"
                else:
                    # se tem "(...)" e não é OK => vermelho
                    styles[j] = "color: red; font-weight: 700;"
        return styles

    styled = styled.apply(apply_colors, axis=1)
    return styled

with table_placeholder.container():
    st.dataframe(style_df(df), use_container_width=True, hide_index=True)


