import streamlit as st
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ============================================================
# PAINEL CENTRAL DE GESTÃO DE ESTUDOS — CONCURSOS ENGENHARIA
# ============================================================

st.set_page_config(
    page_title="Painel de Estudos — Engenharia Elétrica",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_FILE = Path("estudo_concursos_data.json")
IMAGES_DIR = Path("imagens")
IMAGES_DIR.mkdir(exist_ok=True)
RESUMOS_DIR = Path("resumos")
RESUMOS_DIR.mkdir(exist_ok=True)

BACKUP_VERSION = "2.0"

CORE_SUBJECTS = [
    {"name": "Circuitos Elétricos", "type": "Específica", "order": 1, "active": True, "block_minutes": 90},
    {"name": "Língua Portuguesa", "type": "Básica", "order": 2, "active": False, "block_minutes": 60},
    {"name": "Sistemas Elétricos de Potência - SEP", "type": "Específica", "order": 3, "active": True, "block_minutes": 90},
    {"name": "Raciocínio Lógico e Matemático - RLM", "type": "Básica", "order": 4, "active": False, "block_minutes": 60},
    {"name": "Eletrônica Geral e de Potência", "type": "Específica", "order": 5, "active": True, "block_minutes": 90},
    {"name": "Eletromagnetismo e Máquinas Elétricas", "type": "Específica", "order": 6, "active": True, "block_minutes": 90},
]

PHASES = {
    1: "Teoria/Absorção + Fixação Inicial",
    2: "Questões + Caderno de Erros",
    3: "Revisão Ativa + Velocidade/Aprofundamento",
}

ERROR_REASONS = [
    "Falta de Teoria", "Pegadinha", "Atenção", "Fórmula", 
    "Interpretação", "Cálculo", "Conceito confundido", "Outro"
]

DEFAULT_DATA = {
    "version": BACKUP_VERSION,
    "settings": {
        "weekly_target_hours": 22.0,
        "approval_year": 2030,
        "daily_hours": {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0, "Thursday": 2.0,
            "Friday": 2.0, "Saturday": 6.0, "Sunday": 6.0
        }
    },
    "subjects": CORE_SUBJECTS,
    "topics": [],
    "study_sessions": [],
    "errors": [],
    "resumos": [],
    "revisoes": [],
    "meetings": [],
    "cycle_index": 0,
}

def default_data():
    data = json.loads(json.dumps(DEFAULT_DATA))
    data["topics"] = [
        {
            "id": f"{i+1}-1",
            "subject": s["name"],
            "name": "Adicionar tópico do edital",
            "status": "Não iniciado",
            "accuracy": None,
            "created_at": now_iso(),
            "last_studied": None
        }
        for i, s in enumerate(CORE_SUBJECTS)
    ]
    return data

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def load_data():
    if not DATA_FILE.exists(): return default_data()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if "daily_hours" not in data.get("settings", {}):
            wd = data.get("settings", {}).get("weekday_hours", 2.0)
            we = data.get("settings", {}).get("weekend_hours", 6.0)
            data["settings"]["daily_hours"] = {
                "Monday": wd, "Tuesday": wd, "Wednesday": wd, "Thursday": wd,
                "Friday": wd, "Saturday": we, "Sunday": we
            }
        for s in data.get("subjects", []):
            if "active" not in s: s["active"] = True
            if "block_minutes" not in s: s["block_minutes"] = 60
            if "order" not in s: s["order"] = 99
        for t in data.get("topics", []):
            if "id" not in t: t["id"] = f"top-{now_iso()}"
            if "last_studied" not in t: t["last_studied"] = t.get("created_at")
        
        if "resumos" not in data: data["resumos"] = []
        if "revisoes" not in data: data["revisoes"] = []
            
        return data
    except Exception:
        return default_data()

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
    if df.empty: return 0, 0, 0
    df["parsed_date"] = pd.to_datetime(df["date"]).dt.date
    return (
        df[df["parsed_date"] >= week_start]["minutes"].sum() / 60,
        df[df["parsed_date"] >= month_start]["minutes"].sum() / 60,
        df["minutes"].sum() / 60
    )

def inject_css():
    st.markdown("""
        <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
        .metric-card { padding: 16px; border-radius: 14px; border: 1px solid rgba(128,128,128,.25); background: rgba(128,128,128,.06); }
        .next-card { padding: 22px; border-radius: 18px; border: 2px solid rgba(0, 160, 120, .35); background: rgba(0, 160, 120, .08); }
        .alert-card { padding: 16px; border-radius: 14px; border: 1px solid rgba(220, 60, 60, .35); background: rgba(220, 60, 60, .08); }
        .phase { font-size: 0.9rem; opacity: .8; }
        </style>
    """, unsafe_allow_html=True)

# -----------------------------
# Inicialização
# -----------------------------
ensure_session_state()
inject_css()

# -----------------------------
# Sidebar (Hierarquia Ajustada + Guia Operacional no Topo)
# -----------------------------
st.sidebar.title("⚡ Painel Central")
st.sidebar.caption("Gestão de Estudos • Engenharia Elétrica")
page = st.sidebar.radio("Navegação", [
    "🧭 Guia Operacional",
    "📚 Edital Verticalizado",
    "⚙️ Ajustar Ciclo",
    "⏱️ Executar Ciclo",
    "🔔 Notificações",
    "🔄 Revisões Espaçadas",
    "📝 Resumos",
    "❌ Caderno de Erros",
    "📋 Planilha de Controle",
    "📈 Desempenho & Prioridades",
    "🧠 Relatórios",
    "📊 Dashboard",
    "💾 Backup / Configurações",
])

st.sidebar.divider()
st.sidebar.markdown("### Meta")
st.sidebar.write("🎯 Aprovação: **2030**")
st.sidebar.write("⏱️ Meta semanal: **22 h líquidas**")
st.sidebar.write("🎓 Regra: **≥ 70% = assimilado**")
st.sidebar.caption(st.session_state.last_saved_message)


# -----------------------------
# 0. Guia Operacional
# -----------------------------
if page == "🧭 Guia Operacional":
    st.title("🧭 Guia Operacional (Método dos Mestres)")
    st.caption("O passo a passo estruturado para utilizar cada funcionalidade do painel com base no método de Alexandre Meirelles e William Douglas.")

    st.markdown("---")
    st.markdown("### 📍 Fase 1: Planejamento & Estruturação")
    st.markdown("""
    * **📚 Edital Verticalizado:**  
      Cadastre novas disciplinas e o conteúdo programático. Segundo William Douglas, o edital esmiuçado é seu mapa para guiar o estudo ativo.
    * **⚙️ Ajustar Ciclo:**  
      Organize sua ordem de matérias e horas diárias. Conforme Meirelles, planeje a semana de forma flexível e realista.
    """)

    st.markdown("---")
    st.markdown("### 📍 Fase 2: Execução Diária & Operação")
    st.markdown("""
    * **⏱️ Executar Ciclo:**  
      Ligue o cronômetro progressivo e registre o bloco. Siga a rotação contínua de Meirelles para eliminar o engessamento diário.
    * **🔔 Notificações:**  
      Confira diariamente revisões vencidas e alertas do ritmo. Douglas destaca que a consistência diária supera picos de estudo.
    """)

    st.markdown("---")
    st.markdown("### 📍 Fase 3: Fixação & Aprendizado Ativo")
    st.markdown("""
    * **🔄 Revisões Espaçadas:**  
      Execute as revisões programadas nos prazos automáticos. Meirelles reforça que revisar constantemente é mais importante que avançar matéria.
    * **📝 Resumos:**  
      Anexe fotos de esquemas visuais e fórmulas. Douglas reforça que sintetizar a matéria em material próprio acelera a revisão final.
    * **❌ Caderno de Erros:**  
      Registre cada questão errada e seu motivo. Segundo William Douglas, o aprovado é quem mais aprende corrigindo seus pontos fracos.
    """)

    st.markdown("---")
    st.markdown("### 📍 Fase 4: Auditoria, Desempenho & Ajustes")
    st.markdown("""
    * **📋 Planilha de Controle:**  
      Monitore o avanço percentual e status de cada tópico, garantindo a cobertura total do edital sem lacunas no seu radar.
    * **📈 Desempenho & Prioridades:**  
      Analise o risco preditivo de cada matéria. Use o cruzamento de erros e esquecimento para priorizar reforços onde há deficiência.
    * **🧠 Relatórios:**  
      Faça a Reunião do CEO semanal comparando planejado x realizado. Meirelles exige auditoria para ajustar metas e corrigir a rota.
    * **📊 Dashboard:**  
      Visualize gráficos consolidados de horas diárias, fases e alertas do progresso global.
    * **💾 Backup / Configurações:**  
      Exporte o backup em JSON periodicamente. Proteja seus registros e garanta a integridade do seu histórico de preparação.
    """)


# -----------------------------
# 1. Dashboard 
# -----------------------------
elif page == "📊 Dashboard":
    st.title("📊 Dashboard")
    weekly, monthly, total = kpi_periods()
    c1, c2, c3 = st.columns(3)
    c1.metric("Horas — semana", f"{weekly:.1f} h")
    c2.metric("Horas — mês", f"{monthly:.1f} h")
    c3.metric("Horas — total", f"{total:.1f} h")
    
    st.divider()
    
    st.subheader("🧠 Curva de Esquecimento (Alerta de Retenção)")
    retention_alerts = []
    
    for t in st.session_state.data.get("topics", []):
        if t.get("status") in ["Lido/Estudado", "Assimilado/Concluído", "Concluído"]:
            last_date_str = t.get("last_studied") or t.get("created_at")
            if last_date_str:
                try:
                    last_date = date.fromisoformat(last_date_str[:10]) 
                    days_passed = (date.today() - last_date).days
                    if days_passed >= 30:
                        retention_alerts.append({
                            "Disciplina": t["subject"],
                            "Tópico": t["name"],
                            "Dias sem revisão": days_passed,
                            "Último Estudo": last_date.strftime("%d/%m/%Y")
                        })
                except Exception:
                    pass

    if retention_alerts:
        st.warning("⚠️ Os tópicos abaixo foram estudados há mais de 30 dias. É recomendável incluir uma bateria de questões no fim de semana para manutenção da memória.")
        df_alerts = pd.DataFrame(retention_alerts).sort_values("Dias sem revisão", ascending=False)
        st.dataframe(df_alerts, hide_index=True, use_container_width=True)
    else:
        st.success("Tudo em dia! Nenhum tópico maduro esquecido há mais de 30 dias.")

    st.divider()

    df = session_dataframe()
    if not df.empty:
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            daily = df.groupby(pd.to_datetime(df["date"]).dt.date).agg(horas=("minutes", lambda x: x.sum()/60)).reset_index()
            daily.columns = ["date", "horas"]
            fig_line = px.line(daily, x="date", y="horas", markers=True, title="Horas líquidas por dia")
            st.plotly_chart(fig_line, use_container_width=True)
        with col_d2:
            phase_grouped = df.groupby("phase", as_index=False).agg(horas=("minutes", lambda x: x.sum()/60))
            phase_grouped["Fase Desc"] = phase_grouped["phase"].map(lambda p: f"Fase {p}")
            fig_pie = px.pie(phase_grouped, names="Fase Desc", values="horas", title="Distribuição de Horas por Fase de Estudo", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)


# -----------------------------
# 2. Executar ciclo
# -----------------------------
elif page == "⏱️ Executar Ciclo":
    st.title("⏱️ Executar Ciclo")
    st.caption("Ciclo contínuo: acompanhe o foco atual, use o cronômetro progressivo e registre o bloco.")

    curr, nxt = next_subject_info()
    if curr:
        st.markdown(
            f'<div class="next-card"><div class="phase">FLUXO DO CICLO</div>'
            f'<h3>🎯 Foco Atual (Tópico / Matéria): <span style="color:#00a078;">{curr}</span></h3>'
            f'<p style="margin-bottom:0;">Próximo da fila: <b>{nxt}</b></p></div><br>', 
            unsafe_allow_html=True
        )
        
        timer_col, form_col = st.columns([1, 1.2])
        
        with timer_col:
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

        with form_col:
            st.subheader("📝 Registrar bloco")
            
            active_names = [s["name"] for s in get_active_subjects()]
            default_idx = active_names.index(curr) if curr in active_names else 0
            
            subject_sel = st.selectbox("Matéria em estudo", active_names, index=default_idx)
            
            topics_for_subj = [t for t in st.session_state.data["topics"] if t["subject"] == subject_sel and t["name"] != "Adicionar tópico do edital"]
            topic_names = [t["name"] for t in topics_for_subj]
            
            with st.form("session_form"):
                selected_topics = st.multiselect("Tópicos abordados neste bloco (Opcional)", topic_names, placeholder="Selecione os tópicos lidos/revisados...")
                
                phase_num = st.selectbox("Fase de estudo", [1, 2, 3], format_func=lambda x: f"Fase {x} — {PHASES[x]}")
                
                default_mins = round(st.session_state.timer_seconds / 60, 1) if st.session_state.timer_seconds > 0 else 60.0
                minutes = st.number_input("Tempo decorrido (minutos)", value=float(default_mins), step=5.0)
                
                questions = st.number_input("Questões resolvidas", min_value=0, value=0)
                correct = st.number_input("Acertos", min_value=0, value=0)
                notes = st.text_area("Observações do bloco")
                
                submitted = st.form_submit_button("✅ Registrar bloco e avançar ciclo", use_container_width=True)

            if submitted:
                if correct > questions:
                    st.error("Os acertos não podem ser maiores que o número de questões.")
                else:
                    acc = (correct / questions * 100) if questions else None
                    joined_topics = ", ".join(selected_topics) if selected_topics else ""
                    current_dt = datetime.now()
                    session_date_str = current_dt.strftime("%Y-%m-%d")
                    
                    st.session_state.data["study_sessions"].append({
                        "id": current_dt.strftime("%Y%m%d%H%M%S%f"),
                        "date": session_date_str,
                        "timestamp": current_dt.strftime("%Y-%m-%d %H:%M"),
                        "subject": subject_sel,
                        "topic": joined_topics,
                        "phase": int(phase_num),
                        "minutes": float(minutes),
                        "questions": int(questions),
                        "correct": int(correct),
                        "accuracy": acc,
                        "notes": notes,
                    })
                    
                    for topic_name in selected_topics:
                        for t in st.session_state.data["topics"]:
                            if t["subject"] == subject_sel and t["name"] == topic_name:
                                t["last_studied"] = session_date_str
                                if acc is not None and acc >= 70:
                                    t["accuracy"] = acc
                                    t["status"] = "Assimilado/Concluído"
                                elif t["status"] not in ["Concluído", "Assimilado/Concluído"]:
                                    t["status"] = "Lido/Estudado"

                    if int(phase_num) == 3:
                        base_d = date.fromisoformat(session_date_str)
                        intervals = [1, 7, 30, 60, 90]
                        target_topics = selected_topics if selected_topics else [f"Geral / {subject_sel}"]
                        for topic_name in target_topics:
                            ja_possui_revisoes = any(
                                r["subject"] == subject_sel and r["topic"] == topic_name 
                                for r in st.session_state.data["revisoes"]
                            )
                            if not ja_possui_revisoes:
                                for days_offset in intervals:
                                    rev_date = base_d + timedelta(days=days_offset)
                                    st.session_state.data["revisoes"].append({
                                        "id": f"rev-{datetime.now().strftime('%Y%m%d%H%M%S%f')}-{days_offset}",
                                        "subject": subject_sel,
                                        "topic": topic_name,
                                        "interval": f"{days_offset} dia(s)",
                                        "due_date": rev_date.isoformat(),
                                        "done": False,
                                        "dismissed": False
                                    })

                    advance_cycle(subject_sel)
                    reset_timer()
                    st.success("Bloco registrado, ciclo avançado e agenda inteligente tratada!")
                    st.rerun()

    else:
        st.warning("Nenhuma disciplina ativa no ciclo. Acesse 'Ajustar Ciclo'.")


# -----------------------------
# 3. Ajustar Ciclo
# -----------------------------
elif page == "⚙️ Ajustar Ciclo":
    st.title("⚙️ Ajustar Ciclo e Planejamento Semanal")
    
    st.subheader("1. Configurar Disciplinas e Ordem")
    df_subj = pd.DataFrame(st.session_state.data["subjects"])
    if not df_subj.empty:
        edited_df = st.data_editor(
            df_subj[["active", "order", "name", "block_minutes", "type"]],
            column_config={
                "active": st.column_config.CheckboxColumn("Ativa no Ciclo?"),
                "order": st.column_config.NumberColumn("Ordem", step=1),
                "block_minutes": st.column_config.NumberColumn("Minutos/Bloco", step=5),
                "name": st.column_config.TextColumn("Disciplina", disabled=True),
                "type": st.column_config.TextColumn("Tipo", disabled=True)
            },
            hide_index=True, use_container_width=True
        )
        if st.button("💾 Salvar Ordem e Configurações"):
            for _, row in edited_df.iterrows():
                for s in st.session_state.data["subjects"]:
                    if s["name"] == row["name"]:
                        s["active"] = row["active"]
                        s["order"] = int(row["order"])
                        s["block_minutes"] = int(row["block_minutes"])
            st.session_state.data["subjects"].sort(key=lambda x: x["order"])
            persist()
            st.success("Ciclo atualizado!")
            st.rerun()

    st.subheader("2. Disponibilidade e Projeção (Próximos 7 Dias)")
    days_map = {"Monday": "Seg", "Tuesday": "Ter", "Wednesday": "Qua", "Thursday": "Qui", "Friday": "Sex", "Saturday": "Sáb", "Sunday": "Dom"}
    cols = st.columns(7)
    new_hours = {}
    for i, (day_eng, day_pt) in enumerate(days_map.items()):
        val = st.session_state.data["settings"]["daily_hours"].get(day_eng, 2.0)
        new_hours[day_eng] = cols[i].number_input(day_pt, value=float(val), step=0.5, key=f"dh_{day_eng}")
    
    if st.button("💾 Atualizar Horas Diárias"):
        st.session_state.data["settings"]["daily_hours"] = new_hours
        persist()
        st.success("Disponibilidade salva.")
        st.rerun()

    st.markdown("#### Projeção do Ciclo")
    active_subs = get_active_subjects()
    if not active_subs:
        st.info("Ative pelo menos uma disciplina acima para ver a projeção.")
    else:
        proj_date = date.today()
        current_idx = st.session_state.data.get("cycle_index", 0) % len(active_subs)
        
        proj_data = []
        for _ in range(7):
            day_name_eng = proj_date.strftime("%A")
            avail_mins = new_hours.get(day_name_eng, 0) * 60
            day_blocks = []
            
            while avail_mins > 0:
                nxt_s = active_subs[current_idx]
                if avail_mins >= nxt_s["block_minutes"] * 0.5:
                    day_blocks.append(f"{nxt_s['name']} ({nxt_s['block_minutes']}m)")
                    avail_mins -= nxt_s["block_minutes"]
                    current_idx = (current_idx + 1) % len(active_subs)
                else:
                    break
            
            proj_data.append({"Data": proj_date.strftime("%d/%m (%a)"), "Blocos Planejados": " ➔ ".join(day_blocks) if day_blocks else "Descanso/Livre"})
            proj_date += timedelta(days=1)
            
        st.table(pd.DataFrame(proj_data))


# -----------------------------
# 4. Edital Verticalizado (Com adição de nova disciplina)
# -----------------------------
elif page == "📚 Edital Verticalizado":
    st.title("📚 Edital Verticalizado")
    tab1, tab2, tab3 = st.tabs(["📋 Checklist", "➕ Adicionar Disciplina & Tópicos", "🗑️ Excluir Disciplina"])

    with tab1:
        st.caption("Marque o progresso ou exclua tópicos pontuais do edital.")
        for subject in st.session_state.data["subjects"]:
            name = subject["name"]
            topics = [t for t in st.session_state.data["topics"] if t["subject"] == name]
            with st.expander(f'{name} ({len(topics)} tópicos)', expanded=False):
                if not topics:
                    st.caption("Nenhum tópico cadastrado.")
                for topic in topics:
                    c1, c2, c3 = st.columns([0.1, 0.7, 0.2])
                    checked = topic.get("status") in ["Concluído", "Assimilado/Concluído", "Lido/Estudado"]
                    new_checked = c1.checkbox("", value=checked, key=f"t_{topic['id']}")
                    c2.write(topic["name"])
                    
                    if c3.button("🗑️ Excluir", key=f"del_top_{topic['id']}"):
                        st.session_state.data["topics"] = [t for t in st.session_state.data["topics"] if t["id"] != topic["id"]]
                        persist()
                        st.success(f"Tópico excluído!")
                        st.rerun()

                    if new_checked != checked:
                        topic["status"] = "Lido/Estudado" if new_checked else "Não iniciado"
                        if new_checked:
                            topic["last_studied"] = date.today().isoformat()
                        persist()

    with tab2:
        st.subheader("➕ Cadastrar Nova Disciplina")
        with st.form("new_subject_form"):
            new_sub_name = st.text_input("Nome da Nova Disciplina", placeholder="Ex.: Instalações Elétricas")
            new_sub_type = st.selectbox("Tipo", ["Específica", "Básica"])
            new_sub_mins = st.number_input("Minutos por bloco", min_value=30, max_value=180, value=90, step=15)
            
            submitted_new_sub = st.form_submit_button("➕ Criar Disciplina", use_container_width=True)
            
        if submitted_new_sub:
            if not new_sub_name.strip():
                st.error("Informe o nome da disciplina.")
            else:
                existing_names = [s["name"] for s in st.session_state.data["subjects"]]
                if new_sub_name.strip() in existing_names:
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
                    # Adiciona um tópico padrão inicial para a disciplina
                    st.session_state.data["topics"].append({
                        "id": f"top-{now_iso()}",
                        "subject": new_sub_name.strip(),
                        "name": "Introdução / Geral",
                        "status": "Não iniciado",
                        "accuracy": None,
                        "created_at": now_iso(),
                        "last_studied": None
                    })
                    persist()
                    st.success(f"Disciplina '{new_sub_name.strip()}' criada com sucesso!")
                    st.rerun()

        st.divider()
        st.subheader("Inclusão em Lote (Vários tópicos de uma vez)")
        with st.form("bulk_topics"):
            subject_sel = st.selectbox("Disciplina", [s["name"] for s in st.session_state.data["subjects"]])
            topics_text = st.text_area("Cole os tópicos do edital (um por linha)")
            if st.form_submit_button("➕ Adicionar Tópicos"):
                lines = [line.strip() for line in topics_text.split("\n") if line.strip()]
                for i, line in enumerate(lines):
                    st.session_state.data["topics"].append({
                        "id": f"blk-{now_iso()}-{i}",
                        "subject": subject_sel, "name": line, "status": "Não iniciado", "accuracy": None, "last_studied": None
                    })
                persist()
                st.success(f"{len(lines)} tópicos adicionados!")
                st.rerun()

    with tab3:
        st.subheader("Excluir Disciplina Inteira")
        del_subj = st.selectbox("Selecione a disciplina para remover", [s["name"] for s in st.session_state.data["subjects"]], key="del_sel")
        st.warning("⚠️ Atenção: A exclusão removerá permanentemente a disciplina e todos os seus tópicos associados.")
        if st.button("🗑️ Excluir Disciplina Definitivamente"):
            st.session_state.data["subjects"] = [s for s in st.session_state.data["subjects"] if s["name"] != del_subj]
            st.session_state.data["topics"] = [t for t in st.session_state.data["topics"] if t["subject"] != del_subj]
            persist()
            st.success(f"Disciplina {del_subj} excluída.")
            st.rerun()


# -----------------------------
# 5. Planilha de Controle
# -----------------------------
elif page == "📋 Planilha de Controle":
    st.title("📋 Planilha de Controle do Edital")
    st.caption("Visão consolidada por tópicos verticalizados com suporte à exclusão e edição direta.")

    topics_list = st.session_state.data.get("topics", [])
    if topics_list:
        ctrl_rows = []
        for t in topics_list:
            if t["name"] == "Adicionar tópico do edital": 
                continue
            ctrl_rows.append({
                "id": t["id"],
                "Disciplina": t["subject"],
                "Tópico": t["name"],
                "Status": t.get("status", "Não iniciado"),
                "Último Estudo": t.get("last_studied", "-"),
                "% Acerto": t.get("accuracy", 0.0) if t.get("accuracy") is not None else 0.0,
                "Excluir": False
            })
        
        df_ctrl = pd.DataFrame(ctrl_rows)
        if not df_ctrl.empty:
            edited_ctrl = st.data_editor(
                df_ctrl,
                column_config={
                    "id": None,
                    "Disciplina": st.column_config.TextColumn("Disciplina", disabled=True),
                    "Tópico": st.column_config.TextColumn("Tópico"),
                    "Status": st.column_config.SelectboxColumn("Status", options=["Não iniciado", "Lido/Estudado", "Assimilado/Concluído", "Concluído"]),
                    "Último Estudo": st.column_config.TextColumn("Último Estudo", disabled=True),
                    "% Acerto": st.column_config.NumberColumn("% Acerto", format="%.1f %%", disabled=True),
                    "Excluir": st.column_config.CheckboxColumn("Excluir?")
                },
                hide_index=True,
                use_container_width=True,
                key="control_sheet_editor"
            )
            
            if st.button("💾 Sincronizar e Excluir Marcados"):
                ids_to_delete = []
                for _, row in edited_ctrl.iterrows():
                    if row["Excluir"]:
                        ids_to_delete.append(row["id"])
                    else:
                        for t in st.session_state.data["topics"]:
                            if t["id"] == row["id"]:
                                t["name"] = row["Tópico"]
                                t["status"] = row["Status"]
                
                if ids_to_delete:
                    st.session_state.data["topics"] = [t for t in st.session_state.data["topics"] if t["id"] not in ids_to_delete]
                
                persist()
                st.success("Planilha sincronizada e itens removidos com sucesso!")
                st.rerun()
        else:
            st.info("Nenhum tópico cadastrado nos editais.")
    else:
        st.info("Nenhum tópico cadastrado.")


# -----------------------------
# 6. Resumos
# -----------------------------
elif page == "📝 Resumos":
    st.title("📝 Seção de Resumos Manuscritos")
    st.caption("Organize seus resumos fotografados por disciplina e tópico.")

    subject_res = st.selectbox("Disciplina", [s["name"] for s in st.session_state.data["subjects"]], key="res_subj")
    topics_for_res = [t["name"] for t in st.session_state.data["topics"] if t["subject"] == subject_res and t["name"] != "Adicionar tópico do edital"]

    with st.form("resumo_form"):
        c1, c2 = st.columns(2)
        with c1:
            topic_res = st.selectbox("Tópico (Opcional)", ["Nenhum"] + topics_for_res, key="res_top")
        with c2:
            res_title = st.text_input("Título / Descrição do Resumo", placeholder="Ex.: Fórmulas de Transformadores")
            uploaded_res_img = st.file_uploader("Carregar foto do resumo (PNG/JPG)", type=["png", "jpg", "jpeg"], key="res_file")

        save_resumo = st.form_submit_button("💾 Salvar Resumo", use_container_width=True)

    if save_resumo:
        if not res_title.strip():
            st.error("Informe um título ou descrição para o resumo.")
        elif uploaded_res_img is None:
            st.error("Por favor, envie a foto do resumo.")
        else:
            res_filename = f"resumo_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded_res_img.name}"
            res_path = RESUMOS_DIR / res_filename
            with open(res_path, "wb") as f:
                f.write(uploaded_res_img.getbuffer())

            st.session_state.data["resumos"].append({
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "date": date.today().isoformat(),
                "subject": subject_res,
                "topic": topic_res if topic_res != "Nenhum" else "",
                "title": res_title.strip(),
                "image_filename": res_filename
            })
            persist()
            st.success("Resumo cadastrado com sucesso!")
            st.rerun()

    st.divider()
    resumos_list = st.session_state.data.get("resumos", [])
    if resumos_list:
        st.subheader("📚 Resumos Cadastrados")
        res_df_data = []
        for r in resumos_list:
            img_fn = r.get("image_filename", "")
            img_link = f"resumos/{img_fn}" if img_fn else ""
            res_df_data.append({
                "Data": r["date"],
                "Disciplina": r["subject"],
                "Tópico": r.get("topic", ""),
                "Título": r["title"],
                "Imagem (Link)": img_link
            })
        
        st.dataframe(pd.DataFrame(res_df_data), use_container_width=True, hide_index=True)

        valid_res_previews = [
            r.get("image_filename") for r in resumos_list 
            if r.get("image_filename") and not pd.isna(r.get("image_filename")) and (RESUMOS_DIR / str(r.get("image_filename"))).exists()
        ]
        if valid_res_previews:
            st.markdown("#### 🖼️ Visualizador de Resumos")
            sel_res_prev = st.selectbox("Selecione um resumo para exibir a foto", valid_res_previews, key="sel_res")
            if sel_res_prev:
                p_path = RESUMOS_DIR / sel_res_prev
                if p_path.exists():
                    st.image(str(p_path), caption=sel_res_prev, use_container_width=True)
    else:
        st.info("Nenhum resumo cadastrado até o momento.")


# -----------------------------
# 7. Revisões Espaçadas
# -----------------------------
elif page == "🔄 Revisões Espaçadas":
    st.title("🔄 Controle de Revisões Espaçadas")
    st.caption("Agenda automatizada de revisões (Fase 3 gera marcos de 1, 7, 30, 60 e 90 dias apenas no primeiro ciclo do tópico).")

    with st.expander("➕ Adicionar Revisão Manual Avulsa"):
        m_sub = st.selectbox("Disciplina", [s["name"] for s in st.session_state.data["subjects"]], key="m_rev_sub")
        topics_for_rev = [t["name"] for t in st.session_state.data["topics"] if t["subject"] == m_sub and t["name"] != "Adicionar tópico do edital"]

        with st.form("manual_rev_form"):
            m_top = st.selectbox("Tópico / Assunto da Revisão", topics_for_rev if topics_for_rev else ["Nenhum tópico cadastrado"], key="m_rev_top")
            m_date = st.date_input("Data programada", date.today(), key="m_rev_date")
            m_interval = st.text_input("Intervalo (Ex: Customizado)", value="Personalizado", key="m_rev_int")
            if st.form_submit_button("Agendar Revisão"):
                if not m_top.strip() or m_top == "Nenhum tópico cadastrado":
                    st.error("Informe um tópico válido.")
                else:
                    st.session_state.data["revisoes"].append({
                        "id": f"rev-man-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                        "subject": m_sub,
                        "topic": m_top.strip(),
                        "interval": m_interval,
                        "due_date": m_date.isoformat(),
                        "done": False,
                        "dismissed": False
                    })
                    persist()
                    st.success("Revisão agendada!")
                    st.rerun()

    st.divider()
    st.subheader("📅 Agenda de Revisões (Pendentes & Vencidas)")
    
    revisoes_list = st.session_state.data.get("revisoes", [])
    pendentes = [r for r in revisoes_list if not r.get("done", False) and not r.get("dismissed", False)]
    
    if pendentes:
        pendentes_sorted = sorted(pendentes, key=lambda x: x["due_date"])
        
        rev_table_data = []
        for r in pendentes_sorted:
            rev_table_data.append({
                "id": r["id"],
                "Data Alvo": r["due_date"],
                "Disciplina": r["subject"],
                "Tópico": r["topic"],
                "Ciclo": r["interval"],
                "Feita": False,
                "Dispensar": False
            })
        
        df_rev = pd.DataFrame(rev_table_data)
        edited_rev = st.data_editor(
            df_rev,
            column_config={
                "id": None,
                "Data Alvo": st.column_config.TextColumn("Data Alvo", disabled=True),
                "Disciplina": st.column_config.TextColumn("Disciplina", disabled=True),
                "Tópico": st.column_config.TextColumn("Tópico", disabled=True),
                "Ciclo": st.column_config.TextColumn("Ciclo", disabled=True),
                "Feita": st.column_config.CheckboxColumn("Realizada? (Marcar conclui)"),
                "Dispensar": st.column_config.CheckboxColumn("Dispensar?")
            },
            hide_index=True,
            use_container_width=True,
            key="rev_editor"
        )
        
        if st.button("💾 Atualizar Status das Revisões"):
            for _, row in edited_rev.iterrows():
                r_id = row["id"]
                for r in st.session_state.data["revisoes"]:
                    if r["id"] == r_id:
                        if row["Feita"]:
                            r["done"] = True
                        if row["Dispensar"]:
                            r["dismissed"] = True
            persist()
            st.success("Status das revisões atualizado com sucesso!")
            st.rerun()
    else:
        st.success("Parabéns! Não há revisões pendentes no momento.")

    st.divider()
    with st.expander("📂 Histórico de Revisões Concluídas / Dispensadas"):
        historico = [r for r in revisoes_list if r.get("done", False) or r.get("dismissed", False)]
        if historico:
            st.dataframe(pd.DataFrame(historico)[["due_date", "subject", "topic", "interval", "done", "dismissed"]], hide_index=True, use_container_width=True)
        else:
            st.info("Nenhum histórico registrado.")


# -----------------------------
# 8. Caderno de Erros
# -----------------------------
elif page == "❌ Caderno de Erros":
    st.title("❌ Caderno de Erros")
    st.caption("Registre o motivo do erro, vincule opcionalmente a um tópico, anexe imagem e salve.")

    subject = st.selectbox("Disciplina", [s["name"] for s in st.session_state.data["subjects"]])
    topics_for_err = [t["name"] for t in st.session_state.data["topics"] if t["subject"] == subject and t["name"] != "Adicionar tópico do edital"]

    with st.form("error_form"):
        c1, c2 = st.columns(2)
        with c1:
            topic_choice = st.selectbox("Tópico (Opcional)", ["Nenhum"] + topics_for_err)
            reason = st.selectbox("Motivo do erro", ERROR_REASONS)
            priority = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"])
        with c2:
            statement = st.text_area("Resumo da questão / ponto crítico")
            solution = st.text_area("Anotação da solução / aprendizado")
            uploaded_img = st.file_uploader("Anexar imagem da questão (opcional)", type=["png", "jpg", "jpeg"])

        add_error = st.form_submit_button("❌ Registrar erro", use_container_width=True)

    if add_error:
        if not statement.strip():
            st.error("Informe pelo menos o resumo ou enunciado no ponto crítico.")
        else:
            img_filename = ""
            if uploaded_img is not None:
                img_filename = f"erro_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uploaded_img.name}"
                img_path = IMAGES_DIR / img_filename
                with open(img_path, "wb") as f:
                    f.write(uploaded_img.getbuffer())

            st.session_state.data["errors"].append({
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "date": date.today().isoformat(),
                "subject": subject,
                "topic": topic_choice if topic_choice != "Nenhum" else "",
                "reason": reason,
                "statement": statement.strip(),
                "solution": solution.strip(),
                "priority": priority,
                "image_filename": img_filename
            })
            persist()
            st.success("Erro registrado no caderno com sucesso!")
            st.rerun()

    st.divider()
    errors = st.session_state.data.get("errors", [])
    if errors:
        edf = pd.DataFrame(errors)
        st.metric("Total de erros registrados", len(edf))

        f1, f2 = st.columns(2)
        with f1:
            subject_filter = st.selectbox("Filtrar disciplina", ["Todas"] + sorted(edf["subject"].unique().tolist()))
        with f2:
            reason_filter = st.selectbox("Filtrar motivo", ["Todos"] + sorted(edf["reason"].unique().tolist()))

        view = edf.copy()
        if subject_filter != "Todas":
            view = view[view["subject"] == subject_filter]
        if reason_filter != "Todos":
            view = view[view["reason"] == reason_filter]

        display_records = []
        for _, r in view.iterrows():
            img_fn = r.get("image_filename", "")
            if not img_fn or pd.isna(img_fn) or str(img_fn).lower() == "nan":
                img_link = ""
            else:
                img_link = f"imagens/{img_fn}"
                
            display_records.append({
                "Data": r["date"],
                "Disciplina": r["subject"],
                "Tópico": r.get("topic", ""),
                "Motivo": r["reason"],
                "Prioridade": r["priority"],
                "Resumo": r["statement"],
                "Solução": r["solution"],
                "Imagem (Link)": img_link
            })

        view_df = pd.DataFrame(display_records)
        st.dataframe(view_df, use_container_width=True, hide_index=True)
        
        img_previews = [
            r.get("image_filename") for _, r in view.iterrows() 
            if r.get("image_filename") and not pd.isna(r.get("image_filename")) and str(r.get("image_filename")).lower() != "nan" and (IMAGES_DIR / str(r.get("image_filename"))).exists()
        ]
        
        if img_previews:
            st.markdown("#### 🖼️ Prévia de imagens anexadas")
            selected_preview = st.selectbox("Selecione um arquivo de imagem para visualizar", img_previews)
            if selected_preview:
                full_img_path = IMAGES_DIR / selected_preview
                if full_img_path.exists():
                    st.image(str(full_img_path), caption=selected_preview, use_container_width=True)

        if len(view):
            fig = px.bar(
                view.groupby("reason", as_index=False).size().rename(columns={"size": "Quantidade"}),
                x="reason", y="Quantidade", title="Erros por motivo"
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Seu caderno de erros está vazio.")


# -----------------------------
# 9. Desempenho & Prioridades (Análise Preditiva)
# -----------------------------
elif page == "📈 Desempenho & Prioridades":
    st.title("📈 Desempenho Geral & Análise Preditiva de Reforço")
    st.caption("Central consolidada de questões, aproveitamento por tópico, registro manual avulso e priorização inteligente baseada na curva de retenção e caderno de erros.")

    mp_sub = st.selectbox("Disciplina", [s["name"] for s in st.session_state.data["subjects"]], key="mp_sub")
    topics_for_mp = [t["name"] for t in st.session_state.data["topics"] if t["subject"] == mp_sub and t["name"] != "Adicionar tópico do edital"]

    with st.expander("➕ Inserção Manual de Desempenho por Tópico (Avulso)"):
        with st.form("manual_perf_form"):
            mp_top = st.selectbox("Tópico", topics_for_mp if topics_for_mp else ["Nenhum tópico cadastrado"], key="mp_top")
            
            c_mp1, c_mp2, c_mp3 = st.columns(3)
            mp_q = c_mp1.number_input("Questões resolvidas", min_value=1, value=10, key="mp_q")
            mp_c = c_mp2.number_input("Acertos", min_value=0, value=8, key="mp_c")
            mp_d = c_mp3.date_input("Data do registro", date.today(), key="mp_d")
            
            if st.form_submit_button("Registrar Desempenho Avulso"):
                if mp_top == "Nenhum tópico cadastrado":
                    st.error("Cadastre tópicos no edital antes de registrar.")
                elif mp_c > mp_q:
                    st.error("Os acertos não podem superar as questões.")
                else:
                    acc_val = (mp_c / mp_q) * 100
                    st.session_state.data["study_sessions"].append({
                        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                        "date": mp_d.isoformat(),
                        "timestamp": mp_d.strftime("%Y-%m-%d 12:00"),
                        "subject": mp_sub,
                        "topic": mp_top,
                        "phase": 2,
                        "minutes": 30.0,
                        "questions": int(mp_q),
                        "correct": int(mp_c),
                        "accuracy": acc_val,
                        "notes": "Registro manual avulso"
                    })
                    for t in st.session_state.data["topics"]:
                        if t["subject"] == mp_sub and t["name"] == mp_top:
                            t["last_studied"] = mp_d.isoformat()
                            if acc_val >= 70:
                                t["accuracy"] = acc_val
                                t["status"] = "Assimilado/Concluído"
                    persist()
                    st.success("Desempenho registrado com sucesso!")
                    st.rerun()

    st.divider()

    st.subheader("📋 Tabela Consolidada de Questões e Aproveitamento")
    sessions_df = session_dataframe()
    topics_list = st.session_state.data.get("topics", [])
    errors_list = st.session_state.data.get("errors", [])

    if topics_list:
        summary_rows = []
        for t in topics_list:
            if t["name"] == "Adicionar tópico do edital": 
                continue
            t_subj = t["subject"]
            t_name = t["name"]
            
            if not sessions_df.empty:
                match_sess = sessions_df[(sessions_df["subject"] == t_subj) & (sessions_df["topic"].str.contains(t_name, na=False))]
                tot_q = match_sess["questions"].sum()
                tot_c = match_sess["correct"].sum()
                avg_acc = (tot_c / tot_q * 100) if tot_q > 0 else (t.get("accuracy") or 0.0)
            else:
                tot_q = 0
                tot_c = 0
                avg_acc = t.get("accuracy") or 0.0

            err_count = sum(1 for e in errors_list if e["subject"] == t_subj and e.get("topic") == t_name)

            last_st = t.get("last_studied") or t.get("created_at")
            if last_st:
                try:
                    d_pass = (date.today() - date.fromisoformat(last_st[:10])).days
                except:
                    d_pass = 0
            else:
                d_pass = 999

            summary_rows.append({
                "Disciplina": t_subj,
                "Tópico": t_name,
                "Status": t.get("status", "Não iniciado"),
                "Questões": int(tot_q),
                "Acertos": int(tot_c),
                "% Acerto": round(avg_acc, 1),
                "Erros Registrados": err_count,
                "Dias sem Contato": d_pass if d_pass != 999 else "Nunca"
            })

        df_summary = pd.DataFrame(summary_rows)
        st.dataframe(df_summary, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum tópico cadastrado no edital.")

    st.divider()

    st.subheader("🎯 Análise Preditiva de Reforço Prioritário")
    st.caption("Cruzamento inteligente: avalia o risco de esquecimento, a taxa de erros no caderno e o desempenho em questões para definir quais disciplinas exigem atenção imediata.")

    subjects_data = st.session_state.data.get("subjects", [])
    if subjects_data and not sessions_df.empty:
        pred_rows = []
        for s in subjects_data:
            s_name = s["name"]
            s_sess = sessions_df[sessions_df["subject"] == s_name]
            s_errs = sum(1 for e in errors_list if e["subject"] == s_name)
            
            s_q = s_sess["questions"].sum() if not s_sess.empty else 0
            s_c = s_sess["correct"].sum() if not s_sess.empty else 0
            s_acc = (s_c / s_q * 100) if s_q > 0 else 50.0 
            
            topic_objs = [t for t in topics_list if t["subject"] == s_name]
            avg_days = 0
            if topic_objs:
                days_list = []
                for t in topic_objs:
                    ls = t.get("last_studied") or t.get("created_at")
                    if ls:
                        try:
                            days_list.append((date.today() - date.fromisoformat(ls[:10])).days)
                        except:
                            days_list.append(10)
                avg_days = sum(days_list) / len(days_list) if days_list else 10

            risk_score = ((100 - s_acc) * 0.4) + (min(s_errs * 10, 100) * 0.3) + (min(avg_days * 2, 100) * 0.3)
            
            pred_rows.append({
                "Disciplina": s_name,
                "Aproveitamento Médio (%)": round(s_acc, 1),
                "Erros Acumulados": s_errs,
                "Média Dias sem Contato": round(avg_days, 1),
                "Índice de Prioridade de Reforço": round(risk_score, 1)
            })

        df_pred = pd.DataFrame(pred_rows).sort_values("Índice de Prioridade de Reforço", ascending=False)
        
        fig_prio = px.bar(
            df_pred, 
            x="Índice de Prioridade de Reforço", 
            y="Disciplina", 
            orientation="h",
            title="Índice Preditivo de Necessidade de Reforço (Quanto maior, mais urgente a revisão)",
            color="Índice de Prioridade de Reforço",
            color_continuous_scale="Reds"
        )
        fig_prio.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_prio, use_container_width=True)
        
        st.dataframe(df_pred, use_container_width=True, hide_index=True)
    else:
        st.info("Registre sessões de estudo com questões para gerar a análise preditiva de desempenho.")


# -----------------------------
# 10. Relatórios
# -----------------------------
elif page == "🧠 Relatórios":
    st.title("🧠 Relatórios & Reunião do CEO")
    st.caption("Acompanhamento gerencial: Planejado × Realizado, Relatório detalhado/editável e Atas.")

    weekly, monthly, total = kpi_periods()
    target = st.session_state.data["settings"]["weekly_target_hours"]
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Planejado na semana", f"{target:.1f} h")
    c2.metric("Realizado", f"{weekly:.1f} h")
    c3.metric("Gap", f"{weekly-target:+.1f} h")

    st.divider()

    st.subheader("📊 Relatório por disciplina (Editável)")
    st.caption("Histórico detalhado por registro de sessão. Ordenado das mais recentes para as mais antigas.")
    
    sessions_raw = st.session_state.data.get("study_sessions", [])
    if sessions_raw:
        df_sess = pd.DataFrame(sessions_raw)
        if "timestamp" not in df_sess.columns: df_sess["timestamp"] = df_sess["date"]
        if "topic" not in df_sess.columns: df_sess["topic"] = ""
        
        df_sess = df_sess.sort_values(by="timestamp", ascending=False).reset_index(drop=True)
        
        editable_report = st.data_editor(
            df_sess[["id", "timestamp", "subject", "topic", "minutes", "questions", "correct", "phase"]],
            column_config={
                "id": None,
                "timestamp": st.column_config.TextColumn("Data/Hora", disabled=True),
                "subject": st.column_config.TextColumn("Disciplina", disabled=True),
                "topic": st.column_config.TextColumn("Tópico(s)"),
                "minutes": st.column_config.NumberColumn("Minutos", step=5),
                "questions": st.column_config.NumberColumn("Questões", step=1),
                "correct": st.column_config.NumberColumn("Acertos", step=1),
                "phase": st.column_config.NumberColumn("Fase", step=1, min_value=1, max_value=3)
            },
            hide_index=True,
            use_container_width=True,
            key="sessions_report_editor"
        )
        
        if st.button("💾 Sincronizar alterações do relatório"):
            for _, row in editable_report.iterrows():
                for s in st.session_state.data["study_sessions"]:
                    if s["id"] == row["id"]:
                        s["topic"] = row["topic"]
                        s["minutes"] = float(row["minutes"])
                        s["questions"] = int(row["questions"])
                        s["correct"] = int(row["correct"])
                        s["phase"] = int(row["phase"])
                        s["accuracy"] = (s["correct"] / s["questions"] * 100) if s["questions"] > 0 else None
            persist()
            st.success("Relatório sincronizado com sucesso!")
            st.rerun()
    else:
        st.info("Nenhum registro de estudo encontrado.")

    st.divider()

    with st.form("meeting_form"):
        st.subheader("💾 Nova Ata de Reunião do CEO")
        meeting_date = st.date_input("Data da reunião", date.today())
        planned = st.number_input("Horas planejadas", min_value=0.0, max_value=100.0, value=float(target), step=0.5)
        realized = st.number_input("Horas realizadas", min_value=0.0, max_value=100.0, value=float(weekly), step=0.5)
        wins = st.text_area("O que funcionou bem?")
        problems = st.text_area("Problemas / gargalos")
        corrections = st.text_area("Correções de rota para a próxima semana")
        priorities = st.text_area("Prioridades da próxima semana")
        save_meeting = st.form_submit_button("💾 Salvar ata da reunião", use_container_width=True)

    if save_meeting:
        st.session_state.data["meetings"].append({
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
            "date": meeting_date.isoformat(),
            "planned_hours": float(planned),
            "realized_hours": float(realized),
            "gap_hours": float(realized - planned),
            "wins": wins,
            "problems": problems,
            "corrections": corrections,
            "priorities": priorities,
        })
        persist()
        st.success("Ata registrada.")
        st.rerun()

    st.divider()
    st.subheader("📝 Histórico das reuniões")
    meetings = st.session_state.data.get("meetings", [])
    if meetings:
        for m in meetings[::-1]:
            with st.expander(f'Reunião de {m["date"]} • Gap {m["gap_hours"]:+.1f} h'):
                st.write("**Planejado:**", m["planned_hours"], "h")
                st.write("**Realizado:**", m["realized_hours"], "h")
                st.write("**Funcionou:**", m["wins"])
                st.write("**Problemas:**", m["problems"])
                st.write("**Correção de rota:**", m["corrections"])
                st.write("**Prioridades:**", m["priorities"])
    else:
        st.info("Nenhuma reunião registrada.")


# -----------------------------
# 11. Backup / Configurações & Limpeza
# -----------------------------
elif page == "💾 Backup / Configurações":
    st.title("💾 Backup, Configurações & Limpeza de Dados")
    st.caption("Gerencie seus backups locais, ajuste metas globais ou realize a limpeza seletiva de registros operacionais.")

    st.subheader("📤 Exportar Backup")
    backup_json = json.dumps(st.session_state.data, ensure_ascii=False, indent=2)
    st.download_button(
        "⬇️ Exportar Backup (JSON)",
        data=backup_json,
        file_name=f"backup_estudos_{date.today().isoformat()}.json",
        mime="application/json",
        use_container_width=True,
    )

    st.divider()
    st.subheader("📥 Importar Backup")
    uploaded = st.file_uploader("Selecione um backup JSON", type=["json"])
    if uploaded is not None:
        if st.button("🔄 Restaurar backup selecionado", use_container_width=True):
            try:
                imported = json.load(uploaded)
                st.session_state.data = imported
                persist()
                st.success("Backup restaurado com sucesso.")
                st.rerun()
            except Exception as e:
                st.error(f"Arquivo JSON inválido: {e}")

    st.divider()
    st.subheader("⚙️ Regras Globais")
    with st.form("settings_form"):
        weekly_target = st.number_input(
            "Meta semanal total (horas líquidas)", 
            min_value=1.0, max_value=100.0, 
            value=float(st.session_state.data["settings"]["weekly_target_hours"]), step=0.5
        )
        approval = st.number_input(
            "Ano-meta para aprovação", 
            min_value=2026, max_value=2050, 
            value=int(st.session_state.data["settings"]["approval_year"])
        )
        save_settings = st.form_submit_button("💾 Salvar configurações globais")

    if save_settings:
        st.session_state.data["settings"]["weekly_target_hours"] = float(weekly_target)
        st.session_state.data["settings"]["approval_year"] = int(approval)
        persist()
        st.success("Configurações salvas.")

    st.divider()
    st.subheader("🧹 Limpeza Seletiva de Registros (Manutenção)")
    st.caption("Utilize estas opções para zerar dados operacionais de teste sem perder as disciplinas do seu edital ou as configurações.")

    c_clean1, c_clean2 = st.columns(2)
    
    with c_clean1:
        if st.button("🗑️ Zerar Sessões de Estudo", use_container_width=True):
            st.session_state.data["study_sessions"] = []
            for t in st.session_state.data.get("topics", []):
                t["status"] = "Não iniciado"
                t["accuracy"] = None
                t["last_studied"] = None
            persist()
            st.success("Histórico de sessões de estudo limpo com sucesso!")
            st.rerun()

        if st.button("🗑️ Zerar Caderno de Erros", use_container_width=True):
            st.session_state.data["errors"] = []
            persist()
            st.success("Caderno de erros limpo com sucesso!")
            st.rerun()

        if st.button("🗑️ Zerar Resumos", use_container_width=True):
            st.session_state.data["resumos"] = []
            persist()
            st.success("Resumos limpos com sucesso!")
            st.rerun()

    with c_clean2:
        if st.button("🗑️ Zerar Revisões Espaçadas", use_container_width=True):
            st.session_state.data["revisoes"] = []
            persist()
            st.success("Agenda de revisões espaçadas limpa com sucesso!")
            st.rerun()

        if st.button("🗑️ Zerar Atas de Reunião", use_container_width=True):
            st.session_state.data["meetings"] = []
            persist()
            st.success("Histórico de reuniões limpo com sucesso!")
            st.rerun()

        if st.button("⚠️ Zerar TODOS os Registros Operacionais", use_container_width=True):
            st.session_state.data["study_sessions"] = []
            st.session_state.data["errors"] = []
            st.session_state.data["resumos"] = []
            st.session_state.data["revisoes"] = []
            st.session_state.data["meetings"] = []
            for t in st.session_state.data.get("topics", []):
                t["status"] = "Não iniciado"
                t["accuracy"] = None
                t["last_studied"] = None
            persist()
            st.success("Todos os registros operacionais foram zerados (Disciplinas e Configurações preservadas).")
            st.rerun()

    st.divider()
    st.subheader("🗂️ Arquivo de dados local")
    st.code(str(DATA_FILE.resolve()), language="text")
    st.caption("Não apague este arquivo se quiser manter o histórico.")


# -----------------------------
# 12. Notificações & Alertas
# -----------------------------
elif page == "🔔 Notificações":
    st.title("🔔 Central de Notificações & Alertas")
    st.caption("Visão centralizada de pendências, revisões para hoje, prazos vencidos e monitoramento de metas.")

    weekly, monthly, total = kpi_periods()
    target = st.session_state.data["settings"]["weekly_target_hours"]
    gap = weekly - target

    dia_semana_atual = date.today().weekday()
    dias_decorridos = dia_semana_atual + 1
    meta_proporcional = (target / 7) * dias_decorridos
    gap_proporcional = weekly - meta_proporcional

    revisoes_pendentes = [r for r in st.session_state.data.get("revisoes", []) if not r.get("done", False) and not r.get("dismissed", False)]
    hoje_str = date.today().isoformat()
    
    rev_vencidas = [r for r in revisoes_pendentes if r["due_date"] < hoje_str]
    rev_hoje = [r for r in revisoes_pendentes if r["due_date"] == hoje_str]

    col_n1, col_n2, col_n3 = st.columns(3)
    col_n1.metric("Revisões para Hoje / Vencidas", f"{len(rev_hoje)} hoje ({len(rev_vencidas)} atrasadas)", delta="Ação Necessária" if (len(rev_vencidas) + len(rev_hoje)) > 0 else "Em dia", delta_color="inverse" if len(rev_vencidas) > 0 else "normal")
    col_n2.metric("Balanço da Semana (Real x Meta)", f"{weekly:.1f}h / {target}h", delta=f"Gap total: {gap:+.1f}h", delta_color="off")
    
    retention_count = 0
    for t in st.session_state.data.get("topics", []):
        if t.get("status") in ["Lido/Estudado", "Assimilado/Concluído", "Concluído"]:
            last_date_str = t.get("last_studied") or t.get("created_at")
            if last_date_str:
                try:
                    if (date.today() - date.fromisoformat(last_date_str[:10])).days >= 30:
                        retention_count += 1
                except:
                    pass
    col_n3.metric("Tópicos há > 30d sem Contato", f"{retention_count}", delta="Curva de Esquecimento" if retention_count > 0 else "Estável", delta_color="inverse" if retention_count > 0 else "normal")

    st.divider()

    st.subheader("📅 Revisões Espaçadas (Vencidas & Agendadas para Hoje)")
    st.caption("Marque diretamente na tabela abaixo as revisões que você já realizou ou decidiu dispensar.")

    rev_urgentes = rev_vencidas + rev_hoje
    if rev_urgentes:
        table_data = []
        for r in rev_urgentes:
            status_tipo = "🔴 Vencida" if r["due_date"] < hoje_str else "🟢 Para Hoje"
            table_data.append({
                "id": r["id"],
                "Status": status_tipo,
                "Data Alvo": r["due_date"],
                "Disciplina": r["subject"],
                "Tópico": r["topic"],
                "Ciclo": r["interval"],
                "Feita": False,
                "Dispensar": False
            })
        
        df_notif_rev = pd.DataFrame(table_data)
        edited_notif_rev = st.data_editor(
            df_notif_rev,
            column_config={
                "id": None,
                "Status": st.column_config.TextColumn("Status", disabled=True),
                "Data Alvo": st.column_config.TextColumn("Data Alvo", disabled=True),
                "Disciplina": st.column_config.TextColumn("Disciplina", disabled=True),
                "Tópico": st.column_config.TextColumn("Tópico", disabled=True),
                "Ciclo": st.column_config.TextColumn("Ciclo", disabled=True),
                "Feita": st.column_config.CheckboxColumn("Realizada?"),
                "Dispensar": st.column_config.CheckboxColumn("Dispensar?")
            },
            hide_index=True,
            use_container_width=True,
            key="notif_rev_editor"
        )
        
        if st.button("💾 Atualizar Status das Revisões (Notificações)"):
            for _, row in edited_notif_rev.iterrows():
                r_id = row["id"]
                for r in st.session_state.data["revisoes"]:
                    if r["id"] == r_id:
                        if row["Feita"]:
                            r["done"] = True
                        if row["Dispensar"]:
                            r["dismissed"] = True
            persist()
            st.success("Revisões atualizadas com sucesso!")
            st.rerun()
    else:
        st.success("✨ Nenhuma revisão pendente para hoje ou atrasada. Excelente trabalho!")

    st.divider()
    st.subheader("📋 Monitoramento de Ritmo")

    if gap_proporcional < -3.0 and dia_semana_atual >= 3:
        st.markdown(f"""
        <div class="alert-card">
            <h4>⚠️ Ritmo Abaixo da Proporção Semanal</h4>
            <p>Você está acumulando um atraso considerável em relação aos dias já decorridos desta semana ({weekly:.1f}h executadas frente a uma expectativa proporcional de {meta_proporcional:.1f}h). Foco em tirar a diferença no fim de semana!</p>
        </div><br>
        """, unsafe_allow_html=True)
    elif weekly >= meta_proporcional:
        st.markdown(f"""
        <div class="next-card">
            <h4>🎯 Ritmo Equilibrado e Saudável</h4>
            <p>Excelente! Suas horas estudadas estão no ritmo ou acima da expectativa proporcional para este dia da semana.</p>
        </div><br>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="metric-card">
            <h4>🌱 Semana em Andamento</h4>
            <p>A semana está no começo ({dias_decorridos}º dia). O ritmo está adequado para construir sua consistência de forma sustentável, sem pressão excessiva.</p>
        </div><br>
        """, unsafe_allow_html=True)

    if retention_count > 0:
        st.markdown(f"""
        <div class="alert-card">
            <h4>🧠 Alerta da Curva de Esquecimento</h4>
            <p>Existem <b>{retention_count}</b> tópicos estudados que estão há mais de 30 dias sem nova interação.</p>
        </div><br>
        """, unsafe_allow_html=True)


# -----------------------------
# 13. Planilha de Controle
# -----------------------------
elif page == "📋 Planilha de Controle":
    st.title("📋 Planilha de Controle do Edital")
    st.caption("Visão consolidada por tópicos verticalizados com suporte à exclusão e edição direta.")

    topics_list = st.session_state.data.get("topics", [])
    if topics_list:
        ctrl_rows = []
        for t in topics_list:
            if t["name"] == "Adicionar tópico do edital": 
                continue
            ctrl_rows.append({
                "id": t["id"],
                "Disciplina": t["subject"],
                "Tópico": t["name"],
                "Status": t.get("status", "Não iniciado"),
                "Último Estudo": t.get("last_studied", "-"),
                "% Acerto": t.get("accuracy", 0.0) if t.get("accuracy") is not None else 0.0,
                "Excluir": False
            })
        
        df_ctrl = pd.DataFrame(ctrl_rows)
        if not df_ctrl.empty:
            edited_ctrl = st.data_editor(
                df_ctrl,
                column_config={
                    "id": None,
                    "Disciplina": st.column_config.TextColumn("Disciplina", disabled=True),
                    "Tópico": st.column_config.TextColumn("Tópico"),
                    "Status": st.column_config.SelectboxColumn("Status", options=["Não iniciado", "Lido/Estudado", "Assimilado/Concluído", "Concluído"]),
                    "Último Estudo": st.column_config.TextColumn("Último Estudo", disabled=True),
                    "% Acerto": st.column_config.NumberColumn("% Acerto", format="%.1f %%", disabled=True),
                    "Excluir": st.column_config.CheckboxColumn("Excluir?")
                },
                hide_index=True,
                use_container_width=True,
                key="control_sheet_editor"
            )
            
            if st.button("💾 Sincronizar e Excluir Marcados"):
                ids_to_delete = []
                for _, row in edited_ctrl.iterrows():
                    if row["Excluir"]:
                        ids_to_delete.append(row["id"])
                    else:
                        for t in st.session_state.data["topics"]:
                            if t["id"] == row["id"]:
                                t["name"] = row["Tópico"]
                                t["status"] = row["Status"]
                
                if ids_to_delete:
                    st.session_state.data["topics"] = [t for t in st.session_state.data["topics"] if t["id"] not in ids_to_delete]
                
                persist()
                st.success("Planilha sincronizada e itens removidos com sucesso!")
                st.rerun()
        else:
            st.info("Nenhum tópico cadastrado nos editais.")
    else:
        st.info("Nenhum tópico cadastrado.")