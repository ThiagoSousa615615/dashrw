"""
send_report.py — Gera o relatório HTML de apontamentos do dia e envia por e-mail.

Uso:
    python send_report.py

Agendar via Agendador de Tarefas do Windows:
    Programa: C:\\...\\venv\\Scripts\\python.exe
    Argumentos: F:\Github\dashrw\send_report.py
    Iniciar em: F:\Github\dashrw   <- OBRIGATÓRIO para resolver data/ezpoint.db
"""

import os
import sys
import html
import smtplib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, date, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
from dotenv import load_dotenv

from db import get_con
from ezpoint_web import EzPointWebClient

load_dotenv(encoding="utf-8")

DB_PATH = Path("data/ezpoint.db")

DEFAULT_TOL_MIN = int(os.getenv("TOL_MIN", "10"))
INTERVAL_TOL_MIN = int(os.getenv("INTERVAL_TOL_MIN", "10"))

# ----------------------------
# Cores (idênticas ao app.py)
# ----------------------------
COLOR_OK = "#1a7f37"
COLOR_WARN = "#b54708"
COLOR_BAD = "#b42318"
COLOR_MUTED = "#667085"

COL_ORDER = ["Matricula", "Nome", "Horario", "E1", "S1", "E2", "S2", "B1", "B2", "B3", "B4", "Status"]


# ----------------------------
# Modelos (copiados de app.py)
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
# Utilitários (copiados de app.py)
# ----------------------------
def parse_hhmm(hhmm: Optional[str]) -> Optional[time]:
    if not hhmm:
        return None
    hhmm = hhmm.strip()
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def minutes_diff(actual: datetime, expected: datetime) -> int:
    return int((actual - expected).total_seconds() // 60)


def within_tolerance(delta_min: int, tol_min: int) -> bool:
    return -tol_min <= delta_min <= tol_min


def classify(kind: str, delta_min: int, tol_min: int) -> Tuple[str, bool]:
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


def tooltip_cell(text: str, tooltip: str, color: str = "#111", bold: bool = True) -> str:
    safe_text = html.escape(text or "")
    safe_tip = html.escape(tooltip or "")
    fw = "700" if bold else "400"
    return (
        f'<span title="{safe_tip}" '
        f'style="color:{color}; font-weight:{fw}; white-space:nowrap;">'
        f"{safe_text}"
        "</span>"
    )


def render_table_html(rows: List[dict], col_order: List[str]) -> str:
    if not rows:
        return "<div>Sem dados.</div>"

    ths = "".join(
        f"<th style='text-align:left;padding:8px;border-bottom:1px solid #ddd;'>{html.escape(c)}</th>"
        for c in col_order
    )

    body = []
    for r in rows:
        tds = []
        for c in col_order:
            v = r.get(c, "")
            if isinstance(v, str) and v.strip().startswith("<span"):
                cell = v
            else:
                cell = html.escape(str(v))
            tds.append(
                "<td style='padding:8px;border-bottom:1px solid #f2f2f2;white-space:nowrap;'>"
                + cell
                + "</td>"
            )
        body.append("<tr>" + "".join(tds) + "</tr>")

    return f"""
    <div style="overflow-x:auto;">
      <table style="width:100%; border-collapse:collapse; font-size:14px;">
        <thead><tr>{ths}</tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
    </div>
    """


def analyze_employee_day(shift: Shift, punches: List[datetime], d: date, tol_min: int, interval_tol_min: int):
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

    interval_info = None
    if shift.start2 and shift.end2 and len(punches) >= 3:
        saida_1 = punches[1]
        entrada_2 = punches[2]
        intervalo_real = int((entrada_2 - saida_1).total_seconds() // 60)
        intervalo_previsto = int(
            (datetime.combine(d, shift.start2) - datetime.combine(d, shift.end1)).total_seconds() // 60
        )

        if intervalo_real < intervalo_previsto - interval_tol_min:
            interval_info = {"label": "Intervalo reduzido", "ok": False,
                             "expected_min": intervalo_previsto, "actual_min": intervalo_real}
        elif intervalo_real > intervalo_previsto + interval_tol_min:
            interval_info = {"label": "Intervalo excedido", "ok": False,
                             "expected_min": intervalo_previsto, "actual_min": intervalo_real}
        else:
            interval_info = {"label": "Intervalo OK", "ok": True,
                             "expected_min": intervalo_previsto, "actual_min": intervalo_real}

    return marks, interval_info


# ----------------------------
# DB helpers (usam db.get_con)
# ----------------------------
def get_overrides_do_dia(dia_str: str) -> Set[Tuple[str, str]]:
    with get_con() as con:
        rows = con.execute(
            "SELECT matricula, hora FROM batida_override WHERE data = ? AND acao = 'IGNORAR'",
            (dia_str,)
        ).fetchall()
    return {(str(m), str(h)) for (m, h) in rows}


def get_horario_dia(horario_id: int, dia_semana: int):
    with get_con() as con:
        return con.execute(
            "SELECT entrada1, saida1, entrada2, saida2 FROM horario_dia WHERE horario_id = ? AND dia_semana = ?",
            (horario_id, dia_semana)
        ).fetchone()


def load_colabs_with_shift() -> pd.DataFrame:
    with get_con() as con:
        return pd.read_sql_query(
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


def group_batidas_by_matricula(
    batidas: List[dict],
    d: date,
    overrides: Set[Tuple[str, str]],
) -> Dict[str, List[datetime]]:
    out: Dict[str, List[datetime]] = {}
    for b in batidas:
        mat = str(b.get("matriculaFuncionario") or "").strip()
        hora = str(b.get("hora") or "").strip()
        data_str = str(b.get("data") or "").strip()

        if not mat or not hora or not data_str:
            continue
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
# Geração do relatório
# ----------------------------
def build_rows(d: date, batidas_por_matricula: Dict[str, List[datetime]], colabs: pd.DataFrame) -> List[dict]:
    rows = []

    for _, r in colabs.iterrows():
        matricula = str(r["matricula"] or "").strip()
        nome = r["nome_completo"]
        horario_nome = r["horario_nome"] if pd.notna(r["horario_nome"]) else "SEM HORÁRIO"

        dow = d.weekday()
        e1 = r["entrada1"]
        s1 = r["saida1"]
        e2 = r["entrada2"]
        s2 = r["saida2"]

        if pd.notna(r["horario_id"]):
            wd = get_horario_dia(int(r["horario_id"]), dow)
            if wd is not None:
                if all(v is None for v in wd):
                    e1 = s1 = e2 = s2 = None
                    horario_nome = f"{horario_nome} (FOLGA)"
                else:
                    e1, s1, e2, s2 = wd

        if pd.isna(e1) or pd.isna(s1):
            row = {
                "Matricula": matricula,
                "Nome": nome,
                "Horario": horario_nome,
                "E1": "-", "S1": "-", "E2": "-", "S2": "-",
                "B1": tooltip_cell("—", "Sem horário vinculado", COLOR_MUTED, bold=False),
                "B2": tooltip_cell("—", "Sem horário vinculado", COLOR_MUTED, bold=False),
                "B3": tooltip_cell("—", "Sem horário vinculado", COLOR_MUTED, bold=False),
                "B4": tooltip_cell("—", "Sem horário vinculado", COLOR_MUTED, bold=False),
                "Status": tooltip_cell("SEM HORÁRIO", "Cadastre e vincule um horário no admin", COLOR_BAD),
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
        has_extra = len(punches) > 4

        b_cols = ["B1", "B2", "B3", "B4"]
        b_vals = {}
        any_red = False

        for i, bcol in enumerate(b_cols):
            if i < len(marks):
                m = marks[i]
                expected = m.get("expected") or "-"
                actual = m.get("actual") or "-"
                delta = m.get("delta")
                label = m.get("label") or ""

                if delta is None:
                    tip = f"{label} | Previsto: {expected}"
                else:
                    tip = f"{label} | Previsto: {expected} | Atual: {actual} | Dif: {delta:+d} min"

                if m.get("ok"):
                    b_vals[bcol] = tooltip_cell(actual, tip, COLOR_OK)
                else:
                    any_red = True
                    b_vals[bcol] = tooltip_cell(actual, tip, COLOR_BAD)
            else:
                b_vals[bcol] = tooltip_cell("—", "Sem evento", COLOR_MUTED, bold=False)

        status_parts = []
        if interval_info is not None:
            status_parts.append(f"{interval_info['label']} ({interval_info['actual_min']}min)")
            if not interval_info["ok"]:
                any_red = True

        status = " | ".join(status_parts) if status_parts else ("OK" if not any_red else "FORA DA REGRA")

        if has_extra:
            status += " ⚠️"
            any_red = True

        tip_base = (
            "Dentro da tolerância"
            if not any_red
            else "Há eventos fora da tolerância"
        )
        if has_extra:
            tip_base += " | Há mais de 4 batidas no dia."

        status_html = tooltip_cell(
            status,
            tip_base,
            COLOR_OK if not any_red else COLOR_BAD,
        )

        row = {
            "Matricula": matricula,
            "Nome": nome,
            "Horario": f"{horario_nome} [{e1}-{s1}" + (f" / {e2}-{s2}]" if pd.notna(e2) and pd.notna(s2) else "]"),
            "E1": e1, "S1": s1,
            "E2": (e2 if pd.notna(e2) else "-"),
            "S2": (s2 if pd.notna(s2) else "-"),
            **b_vals,
            "Status": status_html,
        }
        rows.append(row)

    return rows


def build_html_report(rows: List[dict], d: date) -> str:
    table_html = render_table_html(rows, COL_ORDER)
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    data_fmt = d.strftime("%d/%m/%Y")

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Dashboard - Apontamentos do Dia {data_fmt}</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 16px; }}
    h2 {{ margin: 0 0 8px 0; }}
    .meta {{ color: #555; font-size: 12px; margin-bottom: 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th {{ text-align: left; padding: 6px; border-bottom: 1px solid #ddd; }}
    td {{ padding: 6px; border-bottom: 1px solid #f0f0f0; white-space: nowrap; }}
    @page {{ size: landscape; margin: 12mm; }}
  </style>
</head>
<body>
  <h2>Dashboard — Apontamentos do Dia ({data_fmt})</h2>
  <div class="meta">Gerado em: {agora}</div>
  {table_html}
</body>
</html>
"""


# ----------------------------
# Destinatários
# ----------------------------
def get_destinatarios() -> List[dict]:
    with get_con() as con:
        rows = con.execute(
            "SELECT email, nome FROM email_destinatario WHERE ativo = 1 ORDER BY email"
        ).fetchall()
    return [{"email": r[0], "nome": r[1]} for r in rows]


# ----------------------------
# Envio de e-mail
# ----------------------------
def send_email(html_body: str, destinatarios: List[dict], assunto: str, smtp_cfg: dict) -> None:
    host = smtp_cfg["host"]
    port = int(smtp_cfg["port"])
    usuario = smtp_cfg["usuario"]
    senha = smtp_cfg["senha"]
    remetente_nome = smtp_cfg.get("remetente_nome", "Dashboard Ponto")
    remetente = f"{remetente_nome} <{usuario}>"

    plain_fallback = (
        "Este e-mail contém o relatório diário de apontamentos. "
        "Abra em um cliente de e-mail com suporte a HTML para visualizá-lo corretamente."
    )

    erros = []
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(usuario, senha)

        for dest in destinatarios:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = assunto
                msg["From"] = remetente
                msg["To"] = dest["email"]

                msg.attach(MIMEText(plain_fallback, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))

                smtp.sendmail(usuario, [dest["email"]], msg.as_string())
                print(f"  Enviado para: {dest['email']}")
            except Exception as exc:
                erros.append((dest["email"], str(exc)))
                print(f"  ERRO ao enviar para {dest['email']}: {exc}", file=sys.stderr)

    if erros:
        raise RuntimeError(f"Falha ao enviar para {len(erros)} destinatário(s): {erros}")


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    # Validar variáveis obrigatórias
    empresa = os.getenv("EZPOINT_EMPRESA", "").strip()
    usuario = os.getenv("EZPOINT_USUARIO", "").strip()
    senha = os.getenv("EZPOINT_SENHA", "").strip()

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = os.getenv("SMTP_PORT", "587").strip()
    smtp_usuario = os.getenv("SMTP_USUARIO", "").strip()
    smtp_senha = os.getenv("SMTP_SENHA", "").strip()
    remetente_nome = os.getenv("EMAIL_REMETENTE_NOME", "Dashboard Ponto").strip()
    assunto_base = os.getenv("EMAIL_ASSUNTO", "Relatório Diário de Apontamentos").strip()

    faltando = [
        nome for nome, val in [
            ("EZPOINT_EMPRESA", empresa),
            ("EZPOINT_USUARIO", usuario),
            ("EZPOINT_SENHA", senha),
            ("SMTP_HOST", smtp_host),
            ("SMTP_USUARIO", smtp_usuario),
            ("SMTP_SENHA", smtp_senha),
        ] if not val
    ]
    if faltando:
        print(f"ERRO: variáveis de ambiente não configuradas: {', '.join(faltando)}", file=sys.stderr)
        sys.exit(1)

    d = date.today()
    dia_str = d.isoformat()
    data_fmt = d.strftime("%d/%m/%Y")
    assunto = f"{assunto_base} — {data_fmt}"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando envio do relatório de {dia_str}...")

    # Buscar destinatários
    destinatarios = get_destinatarios()
    if not destinatarios:
        print("Nenhum destinatário ativo cadastrado. Abortando.")
        sys.exit(0)
    print(f"  Destinatários: {len(destinatarios)}")

    # Buscar dados
    print("  Buscando batidas da API EzPoint...")
    client = EzPointWebClient(empresa=empresa, usuario=usuario, senha=senha)
    batidas = client.listar_batidas(data_inicio=dia_str, data_fim=dia_str)
    print(f"  {len(batidas)} batidas encontradas.")

    overrides = get_overrides_do_dia(dia_str)
    batidas_por_matricula = group_batidas_by_matricula(batidas, d, overrides)

    colabs = load_colabs_with_shift()
    if colabs.empty:
        print("Nenhum colaborador ativo no banco. Abortando.")
        sys.exit(0)

    # Gerar relatório
    rows = build_rows(d, batidas_por_matricula, colabs)
    html_body = build_html_report(rows, d)

    # Enviar
    print(f"  Conectando ao SMTP {smtp_host}:{smtp_port}...")
    smtp_cfg = {
        "host": smtp_host,
        "port": smtp_port,
        "usuario": smtp_usuario,
        "senha": smtp_senha,
        "remetente_nome": remetente_nome,
    }
    send_email(html_body, destinatarios, assunto, smtp_cfg)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Relatório enviado com sucesso para {len(destinatarios)} destinatário(s).")


if __name__ == "__main__":
    main()
