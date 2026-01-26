import pandas as pd
import streamlit as st
from db import get_con
import os
from ezpoint_web import EzPointWebClient
from dotenv import load_dotenv
load_dotenv(encoding="latin-1")  # ou "cp1252"

st.set_page_config(page_title="Admin - Colaboradores e Horários", layout="wide")
st.title("Administração — Colaboradores e Horários")

# ----------------------
# DB queries
# ----------------------
DIAS = [
    (0, "Segunda"),
    (1, "Terça"),
    (2, "Quarta"),
    (3, "Quinta"),
    (4, "Sexta"),
    (5, "Sábado"),
    (6, "Domingo"),
]

DIA_NOME = {
    0: "Segunda",
    1: "Terça",
    2: "Quarta",
    3: "Quinta",
    4: "Sexta",
    5: "Sábado",
    6: "Domingo",
}


def carregar_grade_semanal(horario_id: int) -> pd.DataFrame:
    with get_con() as con:
        df = pd.read_sql_query("""
            SELECT dia_semana, entrada1, saida1, entrada2, saida2
            FROM horario_dia
            WHERE horario_id = ?
            ORDER BY dia_semana
        """, con, params=(horario_id,))
    return df


def listar_horarios_df():
    with get_con() as con:
        return pd.read_sql_query(
            "SELECT id, nome, entrada1, saida1, entrada2, saida2 FROM horario ORDER BY nome",
            con
        )

def get_grade_dia(horario_id: int, dia_semana: int):
    with get_con() as con:
        return con.execute("""
            SELECT entrada1, saida1, entrada2, saida2
            FROM horario_dia
            WHERE horario_id = ? AND dia_semana = ?
        """, (horario_id, dia_semana)).fetchone()

def salvar_grade_dia(horario_id: int, dia_semana: int, e1, s1, e2, s2):
    with get_con() as con:
        con.execute("""
            INSERT INTO horario_dia (horario_id, dia_semana, entrada1, saida1, entrada2, saida2)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(horario_id, dia_semana) DO UPDATE SET
                entrada1 = excluded.entrada1,
                saida1   = excluded.saida1,
                entrada2 = excluded.entrada2,
                saida2   = excluded.saida2
        """, (horario_id, dia_semana, e1, s1, e2, s2))
        con.commit()

def listar_colaboradores():
    with get_con() as con:
        return pd.read_sql_query(
            "SELECT id, matricula, nome_completo, ativo FROM colaborador ORDER BY nome_completo",
            con
        )


def sync_colaboradores_web() -> tuple[int, int]:
    """
    Sincroniza colaboradores via EzPoint WEB (/funcionario) e grava no SQLite.
    Retorna: (upsertados, total_api)
    """
    empresa = os.getenv("EZPOINT_EMPRESA", "").strip()
    usuario = os.getenv("EZPOINT_USUARIO", "").strip()
    senha = os.getenv("EZPOINT_SENHA", "").strip()

    if not (empresa and usuario and senha):
        raise RuntimeError("Configure EZPOINT_EMPRESA, EZPOINT_USUARIO e EZPOINT_SENHA no .env.")

    client = EzPointWebClient(empresa=empresa, usuario=usuario, senha=senha)
    funcs = client.listar_funcionarios(ocultar_demitidos=True)

    upsertados = 0
    with get_con() as con:
        for f in funcs:
            matricula = str(f.get("matricula") or "").strip()
            nome = str(f.get("nome") or "").strip()

            if not matricula or not nome:
                continue

            con.execute(
                """
                INSERT INTO colaborador (matricula, nome_completo, ativo, criado_em, atualizado_em)
                VALUES (?, ?, 1, datetime('now'), datetime('now'))
                ON CONFLICT(matricula) DO UPDATE SET
                  nome_completo = excluded.nome_completo,
                  atualizado_em = datetime('now')
                """,
                (matricula, nome),
            )
            upsertados += 1

        con.commit()

    return upsertados, len(funcs)


def listar_horarios():
    with get_con() as con:
        return pd.read_sql_query(
            "SELECT id, nome, entrada1, saida1, entrada2, saida2, ativo FROM horario ORDER BY nome",
            con
        )

def criar_horario(nome, e1, s1, e2, s2, ativo=True):
    with get_con() as con:
        con.execute(
            """
            INSERT INTO horario (nome, entrada1, saida1, entrada2, saida2, ativo)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (nome.strip(), e1.strip(), s1.strip(), (e2 or None), (s2 or None), 1 if ativo else 0),
        )
        con.commit()

def vincular_horario(colaborador_id: int, horario_id: int):
    # encerra vínculo vigente e cria um novo
    with get_con() as con:
        con.execute(
            """
            UPDATE colaborador_horario
            SET vigencia_fim = date('now')
            WHERE colaborador_id = ? AND vigencia_fim IS NULL
            """,
            (colaborador_id,),
        )
        con.execute(
            """
            INSERT INTO colaborador_horario (colaborador_id, horario_id, vigencia_inicio)
            VALUES (?, ?, date('now'))
            """,
            (colaborador_id, horario_id),
        )
        con.commit()

def vinculo_atual():
    with get_con() as con:
        return pd.read_sql_query(
            """
            SELECT c.id AS colaborador_id,
                   c.matricula,
                   c.nome_completo,
                   c.ativo AS colaborador_ativo,
                   h.nome AS horario,
                   h.entrada1, h.saida1, h.entrada2, h.saida2
            FROM colaborador c
            LEFT JOIN colaborador_horario ch
              ON ch.colaborador_id = c.id AND ch.vigencia_fim IS NULL
            LEFT JOIN horario h
              ON h.id = ch.horario_id
            ORDER BY c.nome_completo
            """,
            con,
        )

# ----------------------
# UI
# ----------------------
tab1, tab2, tab3, tab4 = st.tabs(["Horários", "Colaboradores", "Vincular horário", "📅 Grade Semanal"])

with tab1:
    st.subheader("Cadastrar horários")
    colA, colB = st.columns(2)

    with colA:
        nome = st.text_input("Nome do horário", placeholder="Ex.: ADM 08-12 / 13-17")
        e1 = st.text_input("Entrada 1 (HH:MM)", value="08:00")
        s1 = st.text_input("Saída 1 (HH:MM)", value="12:00")

    with colB:
        e2 = st.text_input("Entrada 2 (HH:MM) (opcional)", value="13:00")
        s2 = st.text_input("Saída 2 (HH:MM) (opcional)", value="17:00")
        ativo_h = st.checkbox("Ativo", value=True)

    if st.button("Criar horário", type="primary"):
        if not nome.strip():
            st.error("Informe um nome para o horário.")
        else:
            try:
                criar_horario(nome, e1, s1, e2, s2, ativo=ativo_h)
                st.success("Horário criado.")
            except Exception as ex:
                st.error(f"Erro ao criar horário: {ex}")

    st.divider()
    st.subheader("Horários cadastrados")
    st.dataframe(listar_horarios(), use_container_width=True, hide_index=True)
    st.divider()
    st.subheader("Grade semanal do horário (por dia da semana)")

    hors = listar_horarios_df()
    if hors.empty:
        st.info("Cadastre um horário primeiro.")
    else:
        opcoes = hors["nome"].tolist()
        nome_sel = st.selectbox("Selecione um horário", opcoes, key="gs_horario_nome")
        horario_id = int(hors.loc[hors["nome"] == nome_sel, "id"].iloc[0])

        dia_label = st.selectbox("Dia da semana", [d[1] for d in DIAS], key="gs_dia")
        dia_semana = [d[0] for d in DIAS if d[1] == dia_label][0]

        cur = get_grade_dia(horario_id, dia_semana)
        cur_e1, cur_s1, cur_e2, cur_s2 = cur if cur else ("", "", "", "")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            e1 = st.text_input("Entrada 1 (HH:MM)", value=cur_e1 or "", key="gs_e1")
        with c2:
            s1 = st.text_input("Saída 1 (HH:MM)", value=cur_s1 or "", key="gs_s1")
        with c3:
            e2 = st.text_input("Entrada 2 (HH:MM) (opcional)", value=cur_e2 or "", key="gs_e2")
        with c4:
            s2 = st.text_input("Saída 2 (HH:MM) (opcional)", value=cur_s2 or "", key="gs_s2")

        colA, colB = st.columns([1, 1])
        with colA:
            if st.button("Salvar dia", key="gs_save"):
                # permite folga: tudo vazio => grava NULL
                e1v = e1.strip() or None
                s1v = s1.strip() or None
                e2v = e2.strip() or None
                s2v = s2.strip() or None

                salvar_grade_dia(horario_id, dia_semana, e1v, s1v, e2v, s2v)
                st.success("Grade do dia salva.")
        with colB:
            st.caption("Dica: Sábado pode ser só Entrada1/Saída1. Domingo pode ficar tudo vazio (folga).")

with tab2:
    st.subheader("Colaboradores (banco)")

    colA, colB = st.columns([1, 3])
    with colA:
        if st.button("Sincronizar da API (WEB) /funcionario", type="primary", use_container_width=True):
            with st.spinner("Sincronizando..."):
                try:
                    upsertados, total_api = sync_colaboradores_web()
                    st.success(f"✅ Sync concluído: {upsertados} upserts (API retornou {total_api}).")
                except Exception as ex:
                    st.error(f"❌ Falha no sync: {ex}")

    with colB:
        st.caption("Clique para puxar/atualizar colaboradores via EzPoint WEB e gravar no banco.")

    st.divider()
    st.dataframe(listar_colaboradores(), use_container_width=True, hide_index=True)


with tab3:
    st.subheader("Vincular um horário ao colaborador")
    colabs = listar_colaboradores()
    hors = listar_horarios()

    if colabs.empty:
        st.warning("Nenhum colaborador no banco ainda. Quando você sincronizar da API, eles aparecerão aqui.")
    if hors.empty:
        st.warning("Nenhum horário cadastrado. Cadastre um horário primeiro (aba Horários).")

    if (not colabs.empty) and (not hors.empty):
        col1, col2 = st.columns(2)

        with col1:
            colaborador_escolhido = st.selectbox(
                "Colaborador",
                colabs["nome_completo"].tolist(),
            )

        with col2:
            horario_escolhido = st.selectbox(
                "Horário",
                hors["nome"].tolist(),
            )

        colaborador_id = int(colabs.loc[colabs["nome_completo"] == colaborador_escolhido, "id"].iloc[0])
        horario_id = int(hors.loc[hors["nome"] == horario_escolhido, "id"].iloc[0])

        if st.button("Vincular agora", type="primary"):
            try:
                vincular_horario(colaborador_id, horario_id)
                st.success("Vínculo atualizado (vigência a partir de hoje).")
            except Exception as ex:
                st.error(f"Erro ao vincular: {ex}")

    st.divider()
    st.subheader("Visão atual (quem está em qual horário)")
    st.dataframe(vinculo_atual(), use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Visualizar grade semanal por horário")

    hors = listar_horarios_df()  # precisa ter colunas: id, nome
    if hors.empty:
        st.info("Cadastre um horário primeiro.")
    else:
        nome_sel = st.selectbox("Selecione um horário", hors["nome"].tolist(), key="view_grade_horario")
        horario_id = int(hors.loc[hors["nome"] == nome_sel, "id"].iloc[0])

        df = carregar_grade_semanal(horario_id)

        if df.empty:
            st.warning("Este horário ainda não tem grade semanal cadastrada (horario_dia).")
        else:
            df["Dia"] = df["dia_semana"].map(DIA_NOME)
            df = df[["Dia", "entrada1", "saida1", "entrada2", "saida2"]]
            df = df.rename(columns={
                "entrada1": "E1",
                "saida1": "S1",
                "entrada2": "E2",
                "saida2": "S2",
            })

            # opcional: marcar folga
            def folga(row):
                return "FOLGA" if not row["E1"] and not row["S1"] and not row["E2"] and not row["S2"] else ""
            df["Observação"] = df.apply(folga, axis=1)

            st.dataframe(df, use_container_width=True, hide_index=True)

        st.caption("Dica: se você editar a grade na aba Horários (seção Grade semanal), ela aparece atualizada aqui.")

