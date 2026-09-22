import streamlit as st
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import plotly.express as px

# ============================================================
# PAINEL CENTRAL DE GESTÃO DE ESTUDOS V3 — CONCURSOS ENGENHARIA
# ============================================================

st.set_page_config(
    page_title="Painel de Estudos — Engenharia Elétrica",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_FILE = Path("estudo_concursos_data.json")
BACKUP_VERSION = "3.0"

CORE_SUBJECTS = [
    {"name": "Circuitos Elétricos", "type": "Específica", "order": 1, "active": True, "block_minutes": 90},
    {"name": "Língua Portuguesa", "type": "Básica", "order": 2, "active": False, "block_minutes": 60},
    {"name": "Sistemas Elétricos de Potência - SEP", "type": "Específica", "order": 3, "active": True, "block_minutes": 90},
    {"name": "Raciocínio Lógico e Matemático - RLM", "type": "Básica", "order": 4, "active": False, "block_minutes": 60},
    {"name": "Eletrônica Geral e de Potência", "type": "Específica", "order": 5, "active": True, "block_minutes": 90},
    {"name": "Eletromagnetismo e Máquinas Elétricas", "type": "Específica", "order": 6, "active": True, "block_minutes": 90},
]

PHASES = {
    1: "Teoria / Absorção",
    2: "Questões / Fixação",
    3: "Revisão Ativa / Aprofundamento",
}

ERROR_REASONS = [
    "Conceito", "Cálculo", "Interpretação", "Atenção", "Fórmula", "Pegadinha"
]

DEFAULT_DATA = {
    "version": BACKUP_VERSION,
    "settings": {
        "weekly_target_hours": 22.0,
        "daily_hours": {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0, "Thursday": 2.0,
            "Friday": 2.0, "Saturday": 6.0, "Sunday": 6.0
        }
    },
    "subjects": CORE_SUBJECTS,
    "topics": [],
    "study_sessions": [],
    "errors": [],
    "reviews": [],
    "cycle_index": 0,
}

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def load_data():
    if not DATA_FILE.exists(): return DEFAULT_DATA.copy()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Migração de chaves legadas se necessário
        if "revisoes" in data and "reviews" not in data:
            data["reviews"] = data.pop("revisoes")
        if "resumos" in data:
            data.pop("resumos", None)
        if "meetings" in data:
            data.pop("meetings", None)
            
        if "daily_hours" not in data.get("settings", {}):
            data["settings"]["daily_hours"] = DEFAULT_DATA["settings"]["daily_hours"]
            
        # Remover tópicos fantasmas antigos "Adicionar tópico do edital"
        if "topics" in data:
            data["topics"] = [t for t in data["topics"] if t.get("name") != "Adicionar tópico do edital"]
            
        return data
    except Exception:
        return DEFAULT_DATA.copy()

def save_data(data):
    tmp = DATA_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

def ensure_session_state():
    if "data" not in st.session_state: st.session_state.data = load_data()
    if "timer_running" not in st.session_state: st.session_state.timer_running = False
    if "timer_seconds" not in st.session_state: st.session_state.timer_seconds = 0
    if "timer_last_tick" not in st.session_state: st.session_state.timer_last_tick = datetime.now()
    if "last_saved_message" not in st.session_state: st.session_state.last_saved_message = ""

def persist():
    save_data(st.session_state.data)
    st.session_state.last_saved_message = f"Salvo às {datetime.now().strftime('%H:%M:%S')}"

def reset_timer():
    st.session_state.timer_running = False
    st.session_state.timer_seconds = 0
    st.session_state.timer_last_tick = datetime.now()

def format_seconds(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"

def get_active_subjects():
    subs = st.session_state.data.get("subjects", [])
    active = [s for s in subs if s.get("active", True)]
    return sorted(active, key=lambda x: x.get("order", 999))

def next_subject_info():
    active = get_active_subjects()
    if not active: return None, None
    idx = st.session_state.data.get("cycle_index", 0) % len(active)
    curr = active[idx]["name"]
    next_idx = (idx + 1) % len(active)
    nxt = active[next_idx]["name"]
    return curr, nxt

def advance_cycle(subject):
    active = get_active_subjects()
    if not active: return
    names = [s["name"] for s in active]
    if subject in names:
        idx = names.index(subject)
        st.session_state.data["cycle_index"] = (idx + 1) % len(active)
    else:
        st.session_state.data["cycle_index"] = (st.session_state.data.get("cycle_index", 0) + 1) % len(active)
    persist()

def session_dataframe():
    sessions = st.session_state.data["study_sessions"]
    if not sessions: 
        return pd.DataFrame(columns=["id", "date", "timestamp", "subject", "topic", "phase", "minutes", "questions", "correct", "accuracy"])
    df = pd.DataFrame(sessions)
    if "topic" not in df.columns: df["topic"] = ""
    if "timestamp" not in df.columns: df["timestamp"] = df["date"]
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
    df["questions"] = pd.to_numeric(df["questions"], errors="coerce").fillna(0)
    df["correct"] = pd.to_numeric(df["correct"], errors="coerce").fillna(0)
    df["accuracy"] = df.apply(lambda r: (r["correct"] / r["questions"] * 100) if r["questions"] > 0 else None, axis=1)
    return df

def kpi_periods():
    df = session_dataframe()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    if df.empty: return 0, 0, 0, 0, 0
    df["parsed_date"] = pd.to_datetime(df["date"]).dt.date
    weekly_mins = df[df["parsed_date"] >= week_start]["minutes"].sum()
    monthly_mins = df[df["parsed_date"] >= month_start]["minutes"].sum()
    total_mins = df["minutes"].sum()
    total_q = df[df["parsed_date"] >= week_start]["questions"].sum()
    total_c = df[df["parsed_date"] >= week_start]["correct"].sum()
    weekly_acc = (total_c / total_q * 100) if total_q > 0 else 0.0
    return weekly_mins / 60, monthly_mins / 60, total_mins / 60, total_q, weekly_acc

def inject_css():
    st.markdown("""
        <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
        .metric-card { padding: 16px; border-radius: 14px; border: 1px solid rgba(128,128,128,.25); background: rgba(128,128,128,.06); }
        .next-card { padding: 22px; border-radius: 18px; border: 2px solid rgba(0, 160, 120, .35); background: rgba(0, 160, 120, .08); }
        .alert-card { padding: 16px; border-radius: 14px; border: 1px solid rgba(220, 60, 60, .35); background: rgba(220, 60, 60, .08); }
        </style>
    """, unsafe_allow_html=True)

# -----------------------------
# Inicialização & Injeção
# -----------------------------
ensure_session_state()
inject_css()

# -----------------------------
# Sidebar Minimalista (5 Opções)
# -----------------------------
st.sidebar.title("⚡ Sistema Operacional")
st.sidebar.caption("Gestão de Estudos • Engenharia Elétrica")

page = st.sidebar.radio("Navegação", [
    "🏠 Painel",
    "📚 Edital",
    "▶️ Estudar",
    "❌ Erros",
    "⚙️ Configurações",
])

st.sidebar.divider()

# Resumo rápido na sidebar
weekly_sb, _, total_sb, _, weekly_acc_sb = kpi_periods()
weekly_target_sb = st.session_state.data["settings"]["weekly_target_hours"]
pct_weekly_sb = min(100, (weekly_sb / weekly_target_sb) * 100) if weekly_target_sb > 0 else 0

st.sidebar.progress(int(pct_weekly_sb), text=f"Semana: {weekly_sb:.1f}h / {weekly_target_sb}h ({pct_weekly_sb:.0f}%)")
st.sidebar.markdown(f"🏆 Total geral: **{total_sb:.1f} h**")
st.sidebar.markdown(f"🎯 Regra: **≥ 70% = assimilado**")
st.sidebar.caption(st.session_state.last_saved_message)


# ============================================================
# 1. 🏠 PAINEL
# ============================================================
if page == "🏠 Painel":
    st.title("🏠 Painel de Comando")
    st.caption("Visão objetiva do seu progresso, metas e ações pendentes.")

    weekly, monthly, total, q_week, acc_week = kpi_periods()
    target = st.session_state.data["settings"]["weekly_target_hours"]
    gap = weekly - target

    # Métricas principais
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Meta Semanal", f"{weekly:.1f} / {target} h", delta=f"{gap:+.1f} h")
    c2.metric("Questões (Semana)", int(q_week))
    c3.metric("Aproveitamento (Semana)", f"{acc_week:.1f}%")
    c4.metric("Horas Totais", f"{total:.1f} h")

    st.divider()

    # Alertas incorporados no topo
    reviews_list = st.session_state.data.get("reviews", [])
    pending_reviews = [r for r in reviews_list if not r.get("done", False) and not r.get("dismissed", False)]
    hoje_str = date.today().isoformat()
    rev_due_today = [r for r in pending_reviews if r["due_date"] <= hoje_str]

    topics_list = st.session_state.data.get("topics", [])
    topics_below_70 = sum(1 for t in topics_list if t.get("accuracy") is not None and t.get("accuracy") < 70)

    col_alt1, col_alt2 = st.columns(2)
    with col_alt1:
        if rev_due_today:
            st.markdown(f"""
            <div class="alert-card">
                <h4>🔄 Revisões Pendentes</h4>
                <p>Você tem <b>{len(rev_due_today)}</b> revisões espaçadas para realizar hoje ou em atraso.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="next-card">
                <h4>🔄 Revisões em Dia</h4>
                <p>Nenhuma revisão pendente para o momento.</p>
            </div>
            """, unsafe_allow_html=True)

    with col_alt2:
        if topics_below_70 > 0:
            st.markdown(f"""
            <div class="alert-card">
                <h4>⚠️ Tópicos Abaixo de 70%</h4>
                <p>Existem <b>{topics_below_70}</b> tópicos estudados com aproveitamento inferior a 70% que exigem reforço.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="next-card">
                <h4>🎯 Domínio Consistente</h4>
                <p>Todos os tópicos estudados possuem aproveitamento ≥ 70% ou ainda não iniciados.</p>
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Próximo bloco do ciclo e status do edital
    c_p1, c_p2 = st.columns(2)
    with c_p1:
        st.subheader("🎯 Próximo Foco no Ciclo")
        curr, nxt = next_subject_info()
        if curr:
            st.markdown(f"""
            <div class="next-card">
                <h3>Matéria Atual: <span style="color:#00a078;">{curr}</span></h3>
                <p>Próxima da fila: <b>{nxt}</b></p>
                <hr style="margin:10px 0; border-color:rgba(0,160,120,0.2);">
                <p style="margin-bottom:0;">Vá para a aba <b>▶️ Estudar</b> para iniciar o cronômetro e registrar sua sessão.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Nenhuma disciplina ativa no ciclo.")

    with c_p2:
        st.subheader("📚 Progresso do Edital")
        total_topics = len(topics_list)
        assimilated_topics = sum(1 for t in topics_list if t.get("status") in ["Assimilado/Concluído", "Concluído"] or (t.get("accuracy") is not None and t.get("accuracy") >= 70))
        pct_edital = (assimilated_topics / total_topics * 100) if total_topics > 0 else 0.0
        
        st.metric("Tópicos Assimilados (≥ 70%)", f"{assimilated_topics} / {total_topics}")
        st.progress(int(pct_edital), text=f"Progresso Geral do Edital: {pct_edital:.1f}%")

        # Sequência atual do ciclo resumida
        active_subs = get_active_subjects()
        if active_subs:
            cycle_names = " ➔ ".join([s["name"] for s in active_subs])
            st.caption(f"**Ordem do Ciclo:** {cycle_names}")


# ============================================================
# 2. 📚 EDITAL
# ============================================================
elif page == "📚 Edital":
    st.title("📚 Edital Verticalizado")
    st.caption("Gerencie disciplinas, conteúdos programáticos, status de estudo e aproveitamento por tópico.")

    tab1, tab2 = st.tabs(["📋 Edital & Tópicos", "⚙️ Gerenciar Disciplinas"])

    with tab1:
        # Inclusão em lote rápida
        with st.expander("➕ Adicionar Tópicos em Lote"):
            with st.form("bulk_topics_form"):
                subj_sel = st.selectbox("Disciplina", [s["name"] for s in st.session_state.data["subjects"]])
                topics_text = st.text_area("Cole os tópicos do edital (um por linha)")
                if st.form_submit_button("➕ Adicionar Tópicos ao Edital"):
                    lines = [line.strip() for line in topics_text.split("\n") if line.strip()]
                    for i, line in enumerate(lines):
                        st.session_state.data["topics"].append({
                            "id": f"top-{now_iso()}-{i}",
                            "subject": subj_sel,
                            "name": line,
                            "status": "Não iniciado",
                            "accuracy": None,
                            "last_studied": None
                        })
                    persist()
                    st.success(f"{len(lines)} tópicos adicionados com sucesso!")
                    st.rerun()

        st.divider()

        # Listagem por disciplina
        for subject in st.session_state.data["subjects"]:
            s_name = subject["name"]
            s_topics = [t for t in st.session_state.data["topics"] if t["subject"] == s_name]
            
            with st.expander(f"📖 {s_name} ({len(s_topics)} tópicos cadastrados)"):
                if not s_topics:
                    st.info("Nenhum tópico cadastrado nesta disciplina.")
                else:
                    for topic in s_topics:
                        col_t1, col_t2, col_t3, col_t4 = st.columns([0.1, 0.5, 0.2, 0.2])
                        
                        t_id = topic["id"]
                        t_status = topic.get("status", "Não iniciado")
                        is_assimilated = t_status in ["Assimilado/Concluído", "Concluído"] or (topic.get("accuracy") is not None and topic.get("accuracy") >= 70)
                        
                        new_checked = col_t1.checkbox("", value=is_assimilated, key=f"chk_top_{t_id}")
                        col_t2.write(topic["name"])
                        
                        acc_val = topic.get("accuracy")
                        acc_str = f"{acc_val:.1f}%" if acc_val is not None else "Sem questões"
                        col_t3.write(f"**{acc_str}**")
                        
                        if col_t4.button("🗑️ Excluir", key=f"del_t_{t_id}"):
                            st.session_state.data["topics"] = [t for t in st.session_state.data["topics"] if t["id"] != t_id]
                            persist()
                            st.success("Tópico excluído!")
                            st.rerun()

                        if new_checked != is_assimilated:
                            topic["status"] = "Assimilado/Concluído" if new_checked else "Não iniciado"
                            persist()

    with tab2:
        st.subheader("Cadastrar Nova Disciplina")
        with st.form("new_subject_form"):
            new_sub_name = st.text_input("Nome da Disciplina", placeholder="Ex.: Instalações Elétricas")
            new_sub_type = st.selectbox("Tipo", ["Específica", "Básica"])
            new_sub_mins = st.number_input("Minutos por bloco", min_value=30, max_value=180, value=90, step=15)
            
            if st.form_submit_button("➕ Criar Disciplina"):
                if not new_sub_name.strip():
                    st.error("Informe o nome da disciplina.")
                else:
                    existing = [s["name"] for s in st.session_state.data["subjects"]]
                    if new_sub_name.strip() in existing:
                        st.error("Esta disciplina já está cadastrada.")
                    else:
                        max_order = max([s.get("order", 0) for s in st.session_state.data["subjects"]], default=0)
                        st.session_state.data["subjects"].append({
                            "name": new_sub_name.strip(),
                            "type": new_sub_type,
                            "order": max_order + 1,
                            "active": True,
                            "block_minutes": int(new_sub_mins)
                        })
                        persist()
                        st.success(f"Disciplina '{new_sub_name.strip()}' criada!")
                        st.rerun()


# ============================================================
# 3. ▶️ ESTUDAR
# ============================================================
elif page == "▶️ Estudar":
    st.title("▶️ Sessão de Estudo")
    st.caption("Acompanhe o ciclo atual, utilize o cronômetro e registre seu bloco de estudo com questões e acertos.")

    curr, nxt = next_subject_info()
    if not curr:
        st.warning("Nenhuma disciplina ativa no ciclo. Ative pelo menos uma em Configurações.")
    else:
        st.markdown(f"""
        <div class="next-card">
            <h3>🎯 Foco Atual: <span style="color:#00a078;">{curr}</span></h3>
            <p style="margin-bottom:0;">Próxima matéria da fila: <b>{nxt}</b></p>
        </div><br>
        """, unsafe_allow_html=True)

        col_timer, col_reg = st.columns([1, 1.2])

        with col_timer:
            st.subheader("⏱️ Cronômetro Progressivo")

            @st.fragment(run_every="1s")
            def timer_widget():
                if st.session_state.timer_running:
                    now = datetime.now()
                    elapsed = int((now - st.session_state.timer_last_tick).total_seconds())
                    if elapsed > 0:
                        st.session_state.timer_seconds += elapsed
                        st.session_state.timer_last_tick = now

                st.markdown(
                    f"<h1 style='text-align:center;font-size:4rem'>{format_seconds(st.session_state.timer_seconds)}</h1>",
                    unsafe_allow_html=True
                )

                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.session_state.timer_running:
                        if st.button("⏸️ Pausar", use_container_width=True):
                            now = datetime.now()
                            elapsed = int((now - st.session_state.timer_last_tick).total_seconds())
                            if elapsed > 0:
                                st.session_state.timer_seconds += elapsed
                            st.session_state.timer_running = False
                            st.session_state.timer_last_tick = now
                            st.rerun(scope="fragment")
                    else:
                        if st.button("▶️ Iniciar", use_container_width=True):
                            st.session_state.timer_running = True
                            st.session_state.timer_last_tick = datetime.now()
                            st.rerun(scope="fragment")
                with b2:
                    if st.button("⏹️ Parar", use_container_width=True):
                        st.session_state.timer_running = False
                        st.rerun(scope="fragment")
                with b3:
                    if st.button("↩️ Resetar", use_container_width=True):
                        reset_timer()
                        st.rerun(scope="fragment")

            timer_widget()

        with col_reg:
            st.subheader("📝 Registrar Bloco")

            active_names = [s["name"] for s in get_active_subjects()]
            default_idx = active_names.index(curr) if curr in active_names else 0
            subject_sel = st.selectbox("Disciplina", active_names, index=default_idx)

            topics_for_subj = [t["name"] for t in st.session_state.data["topics"] if t["subject"] == subject_sel]

            with st.form("session_form"):
                topic_sel = st.selectbox("Tópico Abordado", topics_for_subj if topics_for_subj else ["Nenhum tópico cadastrado"])
                phase_num = st.selectbox("Fase", [1, 2, 3], format_func=lambda x: f"Fase {x} — {PHASES[x]}")
                
                default_mins = round(st.session_state.timer_seconds / 60, 1) if st.session_state.timer_seconds > 0 else 90.0
                minutes = st.number_input("Tempo (minutos)", value=float(default_mins), step=5.0)
                
                questions = st.number_input("Questões resolvidas", min_value=0, value=0)
                correct = st.number_input("Acertos", min_value=0, value=0)

                submitted = st.form_submit_button("✅ Concluir Bloco e Avançar Ciclo", use_container_width=True)

            if submitted:
                if correct > questions:
                    st.error("Os acertos não podem ser superiores ao número de questões.")
                elif topic_sel == "Nenhum tópico cadastrado":
                    st.error("Cadastre pelo menos um tópico para esta disciplina na aba Edital.")
                else:
                    acc = (correct / questions * 100) if questions > 0 else None
                    current_dt = datetime.now()
                    session_date_str = current_dt.strftime("%Y-%m-%d")

                    # Registrar sessão
                    st.session_state.data["study_sessions"].append({
                        "id": current_dt.strftime("%Y%m%d%H%M%S%f"),
                        "date": session_date_str,
                        "timestamp": current_dt.strftime("%Y-%m-%d %H:%M"),
                        "subject": subject_sel,
                        "topic": topic_sel,
                        "phase": int(phase_num),
                        "minutes": float(minutes),
                        "questions": int(questions),
                        "correct": int(correct),
                        "accuracy": acc,
                    })

                    # Atualizar tópico correspondente
                    for t in st.session_state.data["topics"]:
                        if t["subject"] == subject_sel and t["name"] == topic_sel:
                            t["last_studied"] = session_date_str
                            if acc is not None:
                                t["accuracy"] = acc
                                if acc >= 70:
                                    t["status"] = "Assimilado/Concluído"
                                else:
                                    t["status"] = "Lido/Estudado"

                    # Regra de revisão espaçada simplificada
                    if questions > 0 and acc is not None:
                        if acc < 70:
                            rev_days = 2
                        elif acc < 90:
                            rev_days = 7
                        else:
                            rev_days = 30

                        rev_date = date.today() + timedelta(days=rev_days)
                        st.session_state.data["reviews"].append({
                            "id": f"rev-{current_dt.strftime('%Y%m%d%H%M%S%f')}",
                            "subject": subject_sel,
                            "topic": topic_sel,
                            "due_date": rev_date.isoformat(),
                            "interval": f"{rev_days} dias ({acc:.0f}%)",
                            "done": False,
                            "dismissed": False
                        })

                    advance_cycle(subject_sel)
                    reset_timer()
                    st.success("Bloco registrado com sucesso! Ciclo avançado.")
                    st.rerun()


# ============================================================
# 4. ❌ ERROS
# ============================================================
elif page == "❌ Erros":
    st.title("❌ Caderno de Erros")
    st.caption("Consulte seus pontos críticos organizados por matéria e tópico para estudar em sequência.")

    with st.expander("➕ Adicionar Novo Erro"):
        err_subj = st.selectbox("Disciplina", [s["name"] for s in st.session_state.data["subjects"]], key="err_s_cad")
        topics_err = [t["name"] for t in st.session_state.data["topics"] if t["subject"] == err_subj]

        with st.form("error_form"):
            err_top = st.selectbox("Tópico (Opcional)", ["Nenhum"] + topics_err)
            err_reason = st.selectbox("Por que errei?", ERROR_REASONS)
            err_solution = st.text_area("O que preciso lembrar / Solução")

            if st.form_submit_button("❌ Registrar Erro", use_container_width=True):
                if not err_solution.strip():
                    st.error("Preencha a anotação do what precisa lembrar.")
                else:
                    st.session_state.data["errors"].append({
                        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                        "date": date.today().isoformat(),
                        "subject": err_subj,
                        "topic": err_top if err_top != "Nenhum" else "Geral",
                        "reason": err_reason,
                        "solution": err_solution.strip()
                    })
                    persist()
                    st.success("Erro registrado no caderno!")
                    st.rerun()

    st.divider()

    errors_list = st.session_state.data.get("errors", [])
    if not errors_list:
        st.info("Seu caderno de erros está vazio.")
    else:
        edf = pd.DataFrame(errors_list)
        st.metric("Total de erros registrados", len(edf))

        # Filtro opcional por disciplina para visualização rápida
        f_sub = st.selectbox("Filtrar por Disciplina (Opcional)", ["Todas"] + sorted(edf["subject"].unique().tolist()))
        view_err = edf if f_sub == "Todas" else edf[edf["subject"] == f_sub]

        st.divider()

        # Nível 1: Agrupamento por Matéria (Disciplina)
        materias_com_erros = sorted(view_err["subject"].unique().tolist())

        if not materias_com_erros:
            st.info("Nenhum erro encontrado para o filtro selecionado.")
        else:
            for materia in materias_com_erros:
                df_materia = view_err[view_err["subject"] == materia]
                total_erros_mat = len(df_materia)

                # Expansor Nível 1: A Matéria
                with st.expander(f"📚 {materia} ({total_erros_mat} erro{'s' if total_erros_mat > 1 else ''})", expanded=(f_sub != "Todas")):
                    
                    # Nível 2: Agrupamento por Assunto (Tópico) dentro da Matéria
                    # Normaliza tópicos vazios ou nulos para "Geral"
                    df_materia["topic"] = df_materia["topic"].apply(lambda x: x if (x and str(x).strip() and str(x) != "nan") else "Geral")
                    topicos_na_mat = sorted(df_materia["topic"].unique().tolist())

                    for topico in topicos_na_mat:
                        df_topico = df_materia[df_materia["topic"] == topico]
                        
                        st.markdown(f"#### 🔹 Tópico: **{topico}**")
                        
                        # Exibe cada erro individual daquele tópico em sequência
                        for _, r in df_topico.iterrows():
                            e_id = r["id"]
                            e_reas = r["reason"]
                            e_dt = r["date"]
                            e_sol = r["solution"]

                            col_card1, col_card2 = st.columns([5, 1])
                            with col_card1:
                                st.markdown(f"**Motivo:** `{e_reas}` *(Registrado em {e_dt})*")
                                st.info(e_sol)
                            with col_card2:
                                st.markdown("<br>", unsafe_allow_html=True)
                                if st.button("🗑️ Excluir", key=f"del_err_{e_id}"):
                                    st.session_state.data["errors"] = [e for e in st.session_state.data["errors"] if e["id"] != e_id]
                                    persist()
                                    st.success("Erro excluído!")
                                    st.rerun()
                        
                        st.markdown("---")


# ============================================================
# 5. ⚙️ CONFIGURAÇÕES
# ============================================================
elif page == "⚙️ Configurações":
    st.title("⚙️ Configurações & Backup")
    st.caption("Ajuste metas, duração de blocos, ordem das disciplinas e gerencie backups.")

    st.subheader("📤 Exportar / Restaurar Backup")
    backup_json = json.dumps(st.session_state.data, ensure_ascii=False, indent=2)
    st.download_button(
        "⬇️ Baixar Backup (JSON)",
        data=backup_json,
        file_name=f"backup_estudos_{date.today().isoformat()}.json",
        mime="application/json",
        use_container_width=True,
    )

    uploaded = st.file_uploader("Restaurar backup JSON", type=["json"])
    if uploaded is not None:
        if st.button("🔄 Restaurar backup", use_container_width=True):
            try:
                st.session_state.data = json.load(uploaded)
                persist()
                st.success("Backup restaurado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

    st.divider()

    st.subheader("⚙️ Meta Semanal Global")
    with st.form("settings_form"):
        new_target = st.number_input("Meta semanal (horas líquidas)", min_value=1.0, max_value=100.0, value=float(st.session_state.data["settings"]["weekly_target_hours"]), step=0.5)
        if st.form_submit_button("Salvar Meta"):
            st.session_state.data["settings"]["weekly_target_hours"] = float(new_target)
            persist()
            st.success("Meta atualizada!")
            st.rerun()

    st.divider()

    st.subheader("📚 Configurar Disciplinas e Ordem do Ciclo")
    df_subj = pd.DataFrame(st.session_state.data["subjects"])
    if not df_subj.empty:
        edited_subj = st.data_editor(
            df_subj[["active", "order", "name", "block_minutes", "type"]],
            column_config={
                "active": st.column_config.CheckboxColumn("Ativa?"),
                "order": st.column_config.NumberColumn("Ordem", step=1),
                "block_minutes": st.column_config.NumberColumn("Min/Bloco", step=5),
                "name": st.column_config.TextColumn("Disciplina", disabled=True),
                "type": st.column_config.TextColumn("Tipo", disabled=True)
            },
            hide_index=True, use_container_width=True
        )
        if st.button("💾 Salvar Ordem e Configurações"):
            for _, row in edited_subj.iterrows():
                for s in st.session_state.data["subjects"]:
                    if s["name"] == row["name"]:
                        s["active"] = row["active"]
                        s["order"] = int(row["order"])
                        s["block_minutes"] = int(row["block_minutes"])
            st.session_state.data["subjects"].sort(key=lambda x: x["order"])
            persist()
            st.success("Configurações salvas!")
            st.rerun()