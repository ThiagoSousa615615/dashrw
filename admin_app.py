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
tab1, tab2, tab3 = st.tabs(["Horários", "Colaboradores", "Vincular horário"])

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
