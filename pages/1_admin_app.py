import pandas as pd
import streamlit as st
from db import get_con
import os
import sys
from pathlib import Path
from ezpoint_web import EzPointWebClient
from dotenv import load_dotenv
load_dotenv(encoding="utf-8")

st.set_page_config(page_title="Admin - Colaboradores e Horários", layout="wide")
from auth import require_auth
require_auth()
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


def deletar_colaboradores(ids: list[int]) -> int:
    """Deleta colaboradores por id. CASCADE DELETE remove colaborador_horario automaticamente."""
    if not ids:
        return 0
    placeholders = ",".join("?" * len(ids))
    with get_con() as con:
        cur = con.execute(
            f"DELETE FROM colaborador WHERE id IN ({placeholders})",
            ids,
        )
        con.commit()
        return cur.rowcount


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


def listar_destinatarios():
    with get_con() as con:
        return pd.read_sql_query(
            "SELECT id, nome, email, ativo FROM email_destinatario ORDER BY email",
            con
        )


def adicionar_destinatario(email: str, nome: str) -> None:
    with get_con() as con:
        con.execute(
            "INSERT INTO email_destinatario (email, nome) VALUES (?, ?)",
            (email.strip().lower(), nome.strip() or None)
        )
        con.commit()


def toggle_destinatario(dest_id: int, ativo: int) -> None:
    with get_con() as con:
        con.execute(
            "UPDATE email_destinatario SET ativo = ?, atualizado_em = datetime('now') WHERE id = ?",
            (ativo, dest_id)
        )
        con.commit()


def remover_destinatario(dest_id: int) -> None:
    with get_con() as con:
        con.execute("DELETE FROM email_destinatario WHERE id = ?", (dest_id,))
        con.commit()


# ----------------------
# UI
# ----------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Horários", "Colaboradores", "Vincular horário", "📅 Grade Semanal", "📧 Email"])

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
            st.session_state.pop("colab_confirm_delete", None)
            st.session_state.pop("colab_ids_to_delete", None)
            with st.spinner("Sincronizando..."):
                try:
                    upsertados, total_api = sync_colaboradores_web()
                    st.success(f"✅ Sync concluído: {upsertados} upserts (API retornou {total_api}).")
                except Exception as ex:
                    st.error(f"❌ Falha no sync: {ex}")

    with colB:
        st.caption("Clique para puxar/atualizar colaboradores via EzPoint WEB e gravar no banco.")

    st.divider()

    df_colabs = listar_colaboradores()
    df_editor = df_colabs.copy()
    df_editor.insert(0, "Selecionar", False)

    edited = st.data_editor(
        df_editor,
        use_container_width=True,
        hide_index=True,
        key="colab_editor",
        column_config={
            "Selecionar": st.column_config.CheckboxColumn("Selecionar", default=False),
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "matricula": st.column_config.TextColumn("Matrícula", disabled=True),
            "nome_completo": st.column_config.TextColumn("Nome", disabled=True),
            "ativo": st.column_config.NumberColumn("Ativo", disabled=True),
        },
    )

    selected_mask = edited["Selecionar"] == True
    selected_ids = [int(i) for i in df_colabs.loc[selected_mask.values, "id"].tolist()]

    if selected_ids:
        st.caption(f"{len(selected_ids)} colaborador(es) selecionado(s).")

        if not st.session_state.get("colab_confirm_delete", False):
            if st.button(f"Excluir {len(selected_ids)} colaborador(es) selecionado(s)", type="primary", key="btn_delete_colabs"):
                st.session_state["colab_confirm_delete"] = True
                st.session_state["colab_ids_to_delete"] = selected_ids
                st.rerun()
        else:
            ids_to_delete = st.session_state.get("colab_ids_to_delete", [])
            nomes = df_colabs.loc[df_colabs["id"].isin(ids_to_delete), "nome_completo"].tolist()
            st.warning(f"Tem certeza que deseja excluir permanentemente: **{', '.join(nomes)}**? Esta ação não pode ser desfeita.")
            col_yes, col_no = st.columns([1, 5])
            with col_yes:
                if st.button("Confirmar exclusão", type="primary", key="btn_confirm_yes"):
                    try:
                        n = deletar_colaboradores(ids_to_delete)
                        st.session_state.pop("colab_confirm_delete", None)
                        st.session_state.pop("colab_ids_to_delete", None)
                        st.success(f"{n} colaborador(es) excluído(s) com sucesso.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Erro ao excluir: {ex}")
            with col_no:
                if st.button("Cancelar", key="btn_confirm_no"):
                    st.session_state.pop("colab_confirm_delete", None)
                    st.session_state.pop("colab_ids_to_delete", None)
                    st.rerun()
    else:
        st.session_state.pop("colab_confirm_delete", None)
        st.session_state.pop("colab_ids_to_delete", None)


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

with tab5:
    st.subheader("Destinatários do Relatório por E-mail")
    hora_envio = os.getenv("EMAIL_HORA_ENVIO", "17:30")
    smtp_host = os.getenv("SMTP_HOST", "não configurado")
    smtp_usuario = os.getenv("SMTP_USUARIO", "não configurado")
    st.info(
        f"Envio automático diário às **{hora_envio}** via `{smtp_host}` ({smtp_usuario}). "
        f"Para alterar o horário, edite `EMAIL_HORA_ENVIO` no `.env` e reinicie o app."
    )

    with st.form("form_add_email"):
        col1, col2 = st.columns([2, 3])
        with col1:
            novo_email = st.text_input("E-mail", placeholder="gestor@empresa.com")
        with col2:
            novo_nome = st.text_input("Nome (opcional)", placeholder="Fulano de Tal")
        submitted = st.form_submit_button("Adicionar destinatário", type="primary")
        if submitted:
            if not novo_email.strip():
                st.error("Informe o e-mail.")
            else:
                try:
                    adicionar_destinatario(novo_email, novo_nome)
                    st.success(f"Destinatário {novo_email} adicionado.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Erro: {ex}")

    st.divider()
    st.subheader("Lista de destinatários")
    dests = listar_destinatarios()
    if dests.empty:
        st.info("Nenhum destinatário cadastrado.")
    else:
        for _, row in dests.iterrows():
            c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
            c1.write(row["email"])
            c2.write(row["nome"] if row["nome"] else "—")
            label_toggle = "Pausar" if row["ativo"] else "Ativar"
            if c3.button(label_toggle, key=f"toggle_{row['id']}"):
                toggle_destinatario(int(row["id"]), 0 if row["ativo"] else 1)
                st.rerun()
            if c4.button("Remover", key=f"del_{row['id']}"):
                remover_destinatario(int(row["id"]))
                st.rerun()

    st.divider()
    st.subheader("Enviar relatório agora (teste)")
    st.caption("Envia o relatório do dia atual para todos os destinatários ativos.")
    if st.button("Enviar agora", type="primary"):
        import subprocess
        script = Path(__file__).parent.parent / "send_report.py"
        with st.spinner("Enviando..."):
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True, timeout=120,
                cwd=str(Path(__file__).parent.parent)
            )
        if result.returncode == 0:
            st.success("Relatório enviado com sucesso.")
            if result.stdout:
                st.code(result.stdout)
        else:
            st.error("Falha ao enviar o relatório.")
            st.code(result.stderr or result.stdout)
