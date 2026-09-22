import streamlit as st
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd

# ============================================================
# PAINEL DE ESTUDOS V3 — ENGENHARIA ELÉTRICA
# Arquitetura enxuta:
# PAINEL -> EDITAL -> ESTUDAR -> ERROS -> CONFIGURAÇÕES
#
# Compatibilidade:
# - Mantém o mesmo arquivo estudo_concursos_data.json
# - Mantém os campos existentes, inclusive resumos/meetings
# - Não apaga dados antigos na migração
# ============================================================

st.set_page_config(
    page_title="Painel de Estudos V3 — Engenharia Elétrica",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_FILE = Path("estudo_concursos_data.json")
IMAGES_DIR = Path("imagens")
RESUMOS_DIR = Path("resumos")
IMAGES_DIR.mkdir(exist_ok=True)
RESUMOS_DIR.mkdir(exist_ok=True)

VERSION = "3.0"

PHASES = {
    1: "Teoria / Absorção",
    2: "Questões / Fixação",
    3: "Revisão Ativa / Aprofundamento",
}

ERROR_REASONS = [
    "Falta de Teoria",
    "Pegadinha",
    "Atenção",
    "Fórmula",
    "Interpretação",
    "Cálculo",
    "Conceito confundido",
    "Outro",
]

DEFAULT_SUBJECTS = [
    {"name": "Circuitos Elétricos", "type": "Específica", "order": 1, "active": True, "block_minutes": 90},
    {"name": "Língua Portuguesa", "type": "Básica", "order": 2, "active": False, "block_minutes": 60},
    {"name": "Sistemas Elétricos de Potência - SEP", "type": "Específica", "order": 3, "active": True, "block_minutes": 90},
    {"name": "Raciocínio Lógico e Matemático - RLM", "type": "Básica", "order": 4, "active": False, "block_minutes": 60},
    {"name": "Eletrônica Geral e de Potência", "type": "Específica", "order": 5, "active": True, "block_minutes": 90},
    {"name": "Eletromagnetismo e Máquinas Elétricas", "type": "Específica", "order": 6, "active": True, "block_minutes": 90},
]

DEFAULT_DATA = {
    "version": VERSION,
    "settings": {
        "weekly_target_hours": 22.0,
        "daily_hours": {
            "Monday": 2.0,
            "Tuesday": 2.0,
            "Wednesday": 2.0,
            "Thursday": 2.0,
            "Friday": 2.0,
            "Saturday": 6.0,
            "Sunday": 6.0,
        },
    },
    "subjects": DEFAULT_SUBJECTS,
    "topics": [],
    "study_sessions": [],
    "errors": [],
    "resumos": [],
    "revisoes": [],
    "meetings": [],
    "cycle_index": 0,
}


# ------------------------------------------------------------
# Dados / compatibilidade
# ------------------------------------------------------------

def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix="id"):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def default_data():
    data = json.loads(json.dumps(DEFAULT_DATA))
    # Mantém a estrutura antiga, mas não cria mais o falso
    # "Adicionar tópico do edital".
    data["topics"] = []
    return data


def normalize_data(data):
    """Migração conservadora: adiciona apenas campos ausentes."""
    if not isinstance(data, dict):
        return default_data()

    base = default_data()

    for key, value in base.items():
        if key not in data:
            data[key] = json.loads(json.dumps(value))

    settings = data.setdefault("settings", {})
    settings.setdefault("weekly_target_hours", 22.0)

    if "daily_hours" not in settings:
        wd = float(settings.get("weekday_hours", 2.0))
        we = float(settings.get("weekend_hours", 6.0))
        settings["daily_hours"] = {
            "Monday": wd,
            "Tuesday": wd,
            "Wednesday": wd,
            "Thursday": wd,
            "Friday": wd,
            "Saturday": we,
            "Sunday": we,
        }

    for i, subject in enumerate(data.get("subjects", []), start=1):
        subject.setdefault("type", "Específica")
        subject.setdefault("order", i)
        subject.setdefault("active", True)
        subject.setdefault("block_minutes", 90)

    # Remove somente o placeholder artificial antigo.
    # Nenhum dado real do usuário é removido.
    data["topics"] = [
        t for t in data.get("topics", [])
        if str(t.get("name", "")).strip() != "Adicionar tópico do edital"
    ]

    for i, topic in enumerate(data.get("topics", []), start=1):
        topic.setdefault("id", new_id("top"))
        topic.setdefault("status", "Não iniciado")
        topic.setdefault("accuracy", None)
        topic.setdefault("created_at", now_iso())
        topic.setdefault("last_studied", None)

    data.setdefault("study_sessions", [])
    data.setdefault("errors", [])
    data.setdefault("resumos", [])
    data.setdefault("revisoes", [])
    data.setdefault("meetings", [])
    data.setdefault("cycle_index", 0)

    data["version"] = VERSION
    return data


def load_data():
    if not DATA_FILE.exists():
        return default_data()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return normalize_data(json.load(f))
    except Exception:
        # Não sobrescreve arquivo possivelmente corrompido.
        return default_data()


def save_data(data):
    tmp = DATA_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def persist():
    save_data(st.session_state.data)
    st.session_state.last_saved_message = (
        f"Salvo às {datetime.now().strftime('%H:%M:%S')}"
    )


def ensure_session_state():
    if "data" not in st.session_state:
        st.session_state.data = load_data()

    if "timer_running" not in st.session_state:
        st.session_state.timer_running = False
    if "timer_seconds" not in st.session_state:
        st.session_state.timer_seconds = 0
    if "timer_last_tick" not in st.session_state:
        st.session_state.timer_last_tick = datetime.now()
    if "last_saved_message" not in st.session_state:
        st.session_state.last_saved_message = ""


def reset_timer():
    st.session_state.timer_running = False
    st.session_state.timer_seconds = 0
    st.session_state.timer_last_tick = datetime.now()


def format_seconds(seconds):
    seconds = max(0, int(seconds))
    return (
        f"{seconds // 3600:02d}:"
        f"{(seconds % 3600) // 60:02d}:"
        f"{seconds % 60:02d}"
    )


def active_subjects():
    subjects = [
        s for s in st.session_state.data.get("subjects", [])
        if s.get("active", True)
    ]
    return sorted(subjects, key=lambda s: s.get("order", 999))


def all_subject_names():
    return [s["name"] for s in st.session_state.data.get("subjects", [])]


def subject_obj(name):
    return next(
        (s for s in st.session_state.data.get("subjects", []) if s["name"] == name),
        None,
    )


def topics_for_subject(subject):
    return [
        t for t in st.session_state.data.get("topics", [])
        if t.get("subject") == subject
    ]


def get_topic(subject, name):
    return next(
        (
            t for t in st.session_state.data.get("topics", [])
            if t.get("subject") == subject and t.get("name") == name
        ),
        None,
    )


# ------------------------------------------------------------
# Métricas objetivas
# ------------------------------------------------------------

def session_dataframe():
    sessions = st.session_state.data.get("study_sessions", [])
    if not sessions:
        return pd.DataFrame(
            columns=[
                "id", "date", "timestamp", "subject", "topic",
                "phase", "minutes", "questions", "correct", "accuracy",
            ]
        )

    df = pd.DataFrame(sessions)

    for col in ["minutes", "questions", "correct"]:
        if col not in df:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if "topic" not in df:
        df["topic"] = ""
    if "date" not in df:
        df["date"] = date.today().isoformat()

    df["parsed_date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["accuracy_calc"] = df.apply(
        lambda r: (
            r["correct"] / r["questions"] * 100
            if r["questions"] > 0
            else None
        ),
        axis=1,
    )
    return df


def weekly_hours():
    df = session_dataframe()
    if df.empty:
        return 0.0
    monday = date.today() - timedelta(days=date.today().weekday())
    return float(
        df.loc[df["parsed_date"] >= monday, "minutes"].sum() / 60
    )


def total_hours():
    df = session_dataframe()
    if df.empty:
        return 0.0
    return float(df["minutes"].sum() / 60)


def weekly_questions():
    df = session_dataframe()
    if df.empty:
        return 0
    monday = date.today() - timedelta(days=date.today().weekday())
    return int(df.loc[df["parsed_date"] >= monday, "questions"].sum())


def weekly_accuracy():
    df = session_dataframe()
    if df.empty:
        return None
    monday = date.today() - timedelta(days=date.today().weekday())
    w = df[df["parsed_date"] >= monday]
    q = w["questions"].sum()
    c = w["correct"].sum()
    return float(c / q * 100) if q > 0 else None


def topic_last_date(topic):
    raw = topic.get("last_studied")
    if raw:
        try:
            return date.fromisoformat(str(raw)[:10])
        except Exception:
            pass

    # Compatibilidade: se o tópico antigo não tiver last_studied,
    # procura a última sessão que mencione seu nome.
    name = topic.get("name", "")
    subject = topic.get("subject", "")
    df = session_dataframe()
    if not df.empty:
        rows = df[
            (df["subject"] == subject)
            & (df["topic"].fillna("").astype(str).str.contains(name, regex=False))
        ]
        if not rows.empty:
            return rows["parsed_date"].max()

    return None


def pending_reviews():
    today = date.today().isoformat()
    return [
        r for r in st.session_state.data.get("revisoes", [])
        if not r.get("done", False)
        and not r.get("dismissed", False)
        and r.get("due_date")
    ]


def review_counts():
    pending = pending_reviews()
    today = date.today().isoformat()
    overdue = [r for r in pending if r["due_date"] < today]
    due_today = [r for r in pending if r["due_date"] == today]
    return overdue, due_today


def topics_below_70():
    result = []
    for t in st.session_state.data.get("topics", []):
        acc = t.get("accuracy")
        if acc is not None and float(acc) < 70:
            result.append(t)
    return result


def topics_without_recent_contact(days=30):
    result = []
    today = date.today()

    for t in st.session_state.data.get("topics", []):
        if t.get("status") in ["Não iniciado", None]:
            continue

        last = topic_last_date(t)
        if last is not None and (today - last).days >= days:
            result.append((t, (today - last).days))

    return sorted(result, key=lambda x: x[1], reverse=True)


def edital_progress():
    topics = st.session_state.data.get("topics", [])
    if not topics:
        return 0, 0, 0.0

    done = sum(
        1 for t in topics
        if t.get("status") in ["Assimilado/Concluído", "Concluído"]
    )
    pct = done / len(topics) * 100
    return done, len(topics), pct


# ------------------------------------------------------------
# Ciclo
# ------------------------------------------------------------

def current_cycle_subject():
    subjects = active_subjects()
    if not subjects:
        return None

    idx = int(st.session_state.data.get("cycle_index", 0)) % len(subjects)
    return subjects[idx]


def next_cycle_subject():
    subjects = active_subjects()
    if not subjects:
        return None

    idx = int(st.session_state.data.get("cycle_index", 0)) % len(subjects)
    return subjects[(idx + 1) % len(subjects)]


def advance_cycle(subject_name):
    subjects = active_subjects()
    names = [s["name"] for s in subjects]

    if subject_name in names:
        current = names.index(subject_name)
        st.session_state.data["cycle_index"] = (current + 1) % len(names)
    elif names:
        st.session_state.data["cycle_index"] = (
            int(st.session_state.data.get("cycle_index", 0)) + 1
        ) % len(names)

    persist()


# ------------------------------------------------------------
# Revisão simples
# ------------------------------------------------------------

def schedule_next_review(subject, topic, accuracy):
    """
    Regra deliberadamente simples:
      <70%  -> 2 dias
      70-89% -> 7 dias
      >=90% -> 30 dias

    Mantém revisões antigas. Só cria uma nova revisão por registro.
    """
    if accuracy is None:
        return

    if accuracy < 70:
        days = 2
    elif accuracy < 90:
        days = 7
    else:
        days = 30

    due = date.today() + timedelta(days=days)

    # Evita duplicação exata de uma revisão pendente.
    exists = any(
        r.get("subject") == subject
        and r.get("topic") == topic
        and r.get("due_date") == due.isoformat()
        and not r.get("done", False)
        and not r.get("dismissed", False)
        for r in st.session_state.data.get("revisoes", [])
    )

    if not exists:
        st.session_state.data["revisoes"].append({
            "id": new_id("rev"),
            "subject": subject,
            "topic": topic,
            "interval": f"{days} dia(s) [{accuracy:.0f}% acerto]",
            "due_date": due.isoformat(),
            "done": False,
            "dismissed": False,
        })


# ------------------------------------------------------------
# CSS / inicialização
# ------------------------------------------------------------

def inject_css():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.25rem;
            padding-bottom: 2rem;
        }
        .focus-card {
            padding: 20px;
            border-radius: 16px;
            border: 1px solid rgba(0, 160, 120, .35);
            background: rgba(0, 160, 120, .08);
        }
        .alert-card {
            padding: 14px;
            border-radius: 12px;
            border: 1px solid rgba(220, 60, 60, .30);
            background: rgba(220, 60, 60, .07);
        }
        .small-muted {
            opacity: .75;
            font-size: .9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


ensure_session_state()
inject_css()


# ------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------

st.sidebar.title("⚡ Painel de Estudos")
st.sidebar.caption("Engenharia Elétrica • V3 enxuta")

page = st.sidebar.radio(
    "Navegação",
    [
        "🏠 Painel",
        "📚 Edital",
        "▶️ Estudar",
        "❌ Erros",
        "⚙️ Configurações",
    ],
)

st.sidebar.divider()

target = float(
    st.session_state.data.get("settings", {}).get("weekly_target_hours", 22.0)
)
week = weekly_hours()
pct = min(100, week / target * 100) if target > 0 else 0

st.sidebar.progress(
    int(pct),
    text=f"Semana: {week:.1f} h / {target:.1f} h",
)
st.sidebar.caption(f"Acumulado: {total_hours():.1f} h")
st.sidebar.caption("Regra: ≥70% = assimilado")
if st.session_state.last_saved_message:
    st.sidebar.caption(st.session_state.last_saved_message)


# ============================================================
# 1. PAINEL
# ============================================================

if page == "🏠 Painel":
    st.title("🏠 Painel")
    st.caption("A pergunta desta tela é simples: **o que precisa da sua atenção agora?**")

    done, total_topics, progress = edital_progress()
    overdue, due_today = review_counts()
    weak = topics_below_70()
    old_topics = topics_without_recent_contact(30)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Horas esta semana", f"{week:.1f} h", f"meta {target:.1f} h")
    c2.metric("Questões na semana", weekly_questions())
    c3.metric(
        "Acerto na semana",
        f"{weekly_accuracy():.1f}%" if weekly_accuracy() is not None else "—",
    )
    c4.metric("Edital assimilado", f"{progress:.0f}%", f"{done}/{total_topics}")

    st.divider()

    # Foco atual
    current = current_cycle_subject()
    nxt = next_cycle_subject()

    if current:
        st.markdown(
            f"""
            <div class="focus-card">
                <div class="small-muted">PRÓXIMO BLOCO DO CICLO</div>
                <h2 style="margin-bottom:4px;">🎯 {current['name']}</h2>
                <div>Bloco configurado: <b>{int(current.get('block_minutes', 90))} min</b></div>
                <div>Depois: <b>{nxt['name'] if nxt else '—'}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning("Nenhuma disciplina ativa. Ative pelo menos uma em Edital.")

    st.divider()

    # Alertas: somente os que exigem ação.
    st.subheader("⚠️ Ações pendentes")

    actions = []

    if overdue:
        actions.append(
            f"🔴 **{len(overdue)} revisão(ões) atrasada(s)**."
        )
    if due_today:
        actions.append(
            f"🟡 **{len(due_today)} revisão(ões) para hoje**."
        )
    if weak:
        actions.append(
            f"📉 **{len(weak)} tópico(s) abaixo de 70%**."
        )
    if old_topics:
        actions.append(
            f"🧠 **{len(old_topics)} tópico(s) há 30+ dias sem contato**."
        )

    if actions:
        for a in actions:
            st.markdown(a)
    else:
        st.success("Nenhuma pendência crítica. Siga o ciclo.")

    # Revisões urgentes
    urgent = sorted(
        overdue + due_today,
        key=lambda r: r.get("due_date", ""),
    )

    if urgent:
        st.markdown("#### Revisões que exigem ação")
        rows = []
        for r in urgent:
            rows.append({
                "id": r.get("id"),
                "Status": "🔴 Atrasada" if r["due_date"] < date.today().isoformat() else "🟡 Hoje",
                "Data": r.get("due_date"),
                "Disciplina": r.get("subject"),
                "Tópico": r.get("topic"),
                "Intervalo": r.get("interval", ""),
                "Concluída": False,
                "Dispensar": False,
            })

        df_rev = pd.DataFrame(rows)
        edited = st.data_editor(
            df_rev,
            hide_index=True,
            use_container_width=True,
            column_config={
                "id": None,
                "Status": st.column_config.TextColumn(disabled=True),
                "Data": st.column_config.TextColumn(disabled=True),
                "Disciplina": st.column_config.TextColumn(disabled=True),
                "Tópico": st.column_config.TextColumn(disabled=True),
                "Intervalo": st.column_config.TextColumn(disabled=True),
                "Concluída": st.column_config.CheckboxColumn("Concluída?"),
                "Dispensar": st.column_config.CheckboxColumn("Dispensar?"),
            },
            key="dashboard_reviews",
        )

        if st.button("💾 Atualizar revisões", use_container_width=False):
            for _, row in edited.iterrows():
                rid = row["id"]
                for r in st.session_state.data.get("revisoes", []):
                    if r.get("id") == rid:
                        if bool(row["Concluída"]):
                            r["done"] = True
                        if bool(row["Dispensar"]):
                            r["dismissed"] = True
            persist()
            st.rerun()

    st.divider()

    # Visão objetiva do ciclo
    st.subheader("🔄 Ciclo ativo")
    active = active_subjects()

    if active:
        cycle_rows = []
        for s in active:
            cycle_rows.append({
                "Ordem": s.get("order", ""),
                "Disciplina": s["name"],
                "Bloco (min)": s.get("block_minutes", 90),
                "Atual": "🎯" if current and s["name"] == current["name"] else "",
            })
        st.dataframe(
            pd.DataFrame(cycle_rows),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Nenhuma disciplina ativa.")

    st.caption(
        "A tela não tenta prever seu desempenho. Ela apenas mostra dados que geram uma ação concreta."
    )


# ============================================================
# 2. EDITAL
# ============================================================

elif page == "📚 Edital":
    st.title("📚 Edital")
    st.caption(
        "Cadastre as disciplinas e cole os tópicos do edital. "
        "Cada linha vira um tópico."
    )

    tab_edit, tab_add = st.tabs(["📋 Editar", "➕ Adicionar"])

    with tab_edit:
        subjects = sorted(
            st.session_state.data.get("subjects", []),
            key=lambda s: s.get("order", 999),
        )

        if not subjects:
            st.info("Nenhuma disciplina cadastrada.")
        else:
            # Configuração mínima do ciclo fica aqui para evitar outra tela.
            st.subheader("Disciplinas e ciclo")

            subject_rows = []
            for s in subjects:
                subject_rows.append({
                    "Ordem": int(s.get("order", 999)),
                    "Ativa": bool(s.get("active", True)),
                    "Disciplina": s["name"],
                    "Tipo": s.get("type", "Específica"),
                    "Bloco (min)": int(s.get("block_minutes", 90)),
                    "Excluir": False,
                })

            edited_subjects = st.data_editor(
                pd.DataFrame(subject_rows),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Ordem": st.column_config.NumberColumn(min_value=1, step=1),
                    "Ativa": st.column_config.CheckboxColumn(),
                    "Disciplina": st.column_config.TextColumn(disabled=True),
                    "Tipo": st.column_config.TextColumn(disabled=True),
                    "Bloco (min)": st.column_config.NumberColumn(
                        min_value=15, max_value=240, step=5
                    ),
                    "Excluir": st.column_config.CheckboxColumn("Excluir?"),
                },
                key="subjects_editor",
            )

            if st.button("💾 Salvar ciclo / excluir marcadas"):
                delete_names = set()

                for _, row in edited_subjects.iterrows():
                    if bool(row["Excluir"]):
                        delete_names.add(row["Disciplina"])
                        continue

                    s = subject_obj(row["Disciplina"])
                    if s:
                        s["order"] = int(row["Ordem"])
                        s["active"] = bool(row["Ativa"])
                        s["block_minutes"] = int(row["Bloco (min)"])

                if delete_names:
                    st.session_state.data["subjects"] = [
                        s for s in st.session_state.data["subjects"]
                        if s["name"] not in delete_names
                    ]
                    st.session_state.data["topics"] = [
                        t for t in st.session_state.data["topics"]
                        if t.get("subject") not in delete_names
                    ]

                st.session_state.data["subjects"].sort(
                    key=lambda s: s.get("order", 999)
                )
                persist()
                st.success("Ciclo atualizado.")
                st.rerun()

            st.divider()

            st.subheader("Tópicos do edital")

            for s in sorted(
                st.session_state.data.get("subjects", []),
                key=lambda x: x.get("order", 999),
            ):
                topics = topics_for_subject(s["name"])

                with st.expander(
                    f"{s['name']} — {len(topics)} tópico(s)",
                    expanded=False,
                ):
                    if not topics:
                        st.caption("Nenhum tópico cadastrado.")
                        continue

                    rows = []
                    for t in topics:
                        acc = t.get("accuracy")
                        rows.append({
                            "id": t["id"],
                            "Tópico": t.get("name", ""),
                            "Status": t.get("status", "Não iniciado"),
                            "% Acerto": acc if acc is not None else None,
                            "Último estudo": (
                                str(t.get("last_studied", ""))[:10]
                                if t.get("last_studied")
                                else "—"
                            ),
                            "Excluir": False,
                        })

                    edited_topics = st.data_editor(
                        pd.DataFrame(rows),
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "id": None,
                            "Tópico": st.column_config.TextColumn(),
                            "Status": st.column_config.SelectboxColumn(
                                options=[
                                    "Não iniciado",
                                    "Lido/Estudado",
                                    "Assimilado/Concluído",
                                    "Concluído",
                                ]
                            ),
                            "% Acerto": st.column_config.NumberColumn(
                                format="%.1f%%", disabled=True
                            ),
                            "Último estudo": st.column_config.TextColumn(
                                disabled=True
                            ),
                            "Excluir": st.column_config.CheckboxColumn("Excluir?"),
                        },
                        key=f"topic_editor_{s['name']}",
                    )

                    if st.button(
                        f"💾 Salvar {s['name']}",
                        key=f"save_topics_{s['name']}",
                    ):
                        delete_ids = set()

                        for _, row in edited_topics.iterrows():
                            if bool(row["Excluir"]):
                                delete_ids.add(row["id"])
                                continue

                            for t in st.session_state.data["topics"]:
                                if t["id"] == row["id"]:
                                    t["name"] = str(row["Tópico"]).strip()
                                    t["status"] = row["Status"]

                        if delete_ids:
                            st.session_state.data["topics"] = [
                                t for t in st.session_state.data["topics"]
                                if t["id"] not in delete_ids
                            ]

                        persist()
                        st.success("Tópicos atualizados.")
                        st.rerun()

    with tab_add:
        st.subheader("➕ Nova disciplina")

        with st.form("new_subject_v3"):
            name = st.text_input(
                "Nome da disciplina",
                placeholder="Ex.: Instalações Elétricas",
            )
            typ = st.selectbox("Tipo", ["Específica", "Básica"])
            block = st.number_input(
                "Duração padrão do bloco (min)",
                min_value=15,
                max_value=240,
                value=90,
                step=15,
            )
            create = st.form_submit_button(
                "Criar disciplina",
                use_container_width=True,
            )

        if create:
            clean = name.strip()
            if not clean:
                st.error("Informe o nome.")
            elif clean in all_subject_names():
                st.error("Essa disciplina já existe.")
            else:
                max_order = max(
                    [s.get("order", 0) for s in st.session_state.data["subjects"]],
                    default=0,
                )
                st.session_state.data["subjects"].append({
                    "name": clean,
                    "type": typ,
                    "order": max_order + 1,
                    "active": True,
                    "block_minutes": int(block),
                })
                persist()
                st.success("Disciplina criada.")
                st.rerun()

        st.divider()
        st.subheader("➕ Adicionar tópicos em lote")

        names = all_subject_names()
        if names:
            with st.form("bulk_topics_v3"):
                selected_subject = st.selectbox("Disciplina", names)
                pasted = st.text_area(
                    "Cole o conteúdo do edital — um tópico por linha",
                    height=220,
                    placeholder="1. Transformadores\n2. Máquinas de indução\n3. Curto-circuito...",
                )
                add_bulk = st.form_submit_button(
                    "Adicionar tópicos",
                    use_container_width=True,
                )

            if add_bulk:
                lines = [
                    line.strip()
                    for line in pasted.splitlines()
                    if line.strip()
                ]

                existing = {
                    t.get("name", "").strip().lower()
                    for t in topics_for_subject(selected_subject)
                }

                added = 0
                for line in lines:
                    if line.lower() in existing:
                        continue

                    st.session_state.data["topics"].append({
                        "id": new_id("top"),
                        "subject": selected_subject,
                        "name": line,
                        "status": "Não iniciado",
                        "accuracy": None,
                        "created_at": now_iso(),
                        "last_studied": None,
                    })
                    existing.add(line.lower())
                    added += 1

                persist()
                st.success(f"{added} tópico(s) adicionado(s).")
                st.rerun()
        else:
            st.info("Crie uma disciplina primeiro.")


# ============================================================
# 3. ESTUDAR
# ============================================================

elif page == "▶️ Estudar":
    st.title("▶️ Estudar")
    st.caption(
        "Execute o ciclo, estude e registre somente o que importa: tempo, questões e acertos."
    )

    current = current_cycle_subject()

    if not current:
        st.warning("Nenhuma disciplina ativa. Ative uma disciplina em Edital.")
    else:
        nxt = next_cycle_subject()

        st.markdown(
            f"""
            <div class="focus-card">
                <div class="small-muted">FOCO ATUAL</div>
                <h2 style="margin-bottom:4px;">🎯 {current['name']}</h2>
                <div>Bloco padrão: <b>{int(current.get('block_minutes', 90))} min</b></div>
                <div>Próximo: <b>{nxt['name'] if nxt else '—'}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        timer_col, record_col = st.columns([0.9, 1.4])

        with timer_col:
            st.subheader("⏱️ Cronômetro")

            @st.fragment(run_every="1s")
            def timer_widget():
                if st.session_state.timer_running:
                    now = datetime.now()
                    elapsed = int(
                        (now - st.session_state.timer_last_tick).total_seconds()
                    )
                    if elapsed > 0:
                        st.session_state.timer_seconds += elapsed
                        st.session_state.timer_last_tick = now

                st.markdown(
                    f"<h1 style='text-align:center;font-size:3.8rem'>"
                    f"{format_seconds(st.session_state.timer_seconds)}</h1>",
                    unsafe_allow_html=True,
                )

                b1, b2, b3 = st.columns(3)

                with b1:
                    if st.session_state.timer_running:
                        if st.button("⏸️ Pausar", use_container_width=True):
                            now = datetime.now()
                            elapsed = int(
                                (now - st.session_state.timer_last_tick).total_seconds()
                            )
                            st.session_state.timer_seconds += max(0, elapsed)
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
                        if st.session_state.timer_running:
                            now = datetime.now()
                            elapsed = int(
                                (now - st.session_state.timer_last_tick).total_seconds()
                            )
                            st.session_state.timer_seconds += max(0, elapsed)
                        st.session_state.timer_running = False
                        st.session_state.timer_last_tick = datetime.now()
                        st.rerun(scope="fragment")

                with b3:
                    if st.button("↩️ Resetar", use_container_width=True):
                        reset_timer()
                        st.rerun(scope="fragment")

            timer_widget()

            st.caption(
                "O cronômetro é progressivo. O tempo também pode ser corrigido manualmente no registro."
            )

        with record_col:
            st.subheader("📝 Registrar bloco")

            active_names = [s["name"] for s in active_subjects()]
            default_index = (
                active_names.index(current["name"])
                if current["name"] in active_names
                else 0
            )

            subject = st.selectbox(
                "Disciplina",
                active_names,
                index=default_index,
                key="study_subject",
            )

            topic_names = [t["name"] for t in topics_for_subject(subject)]

            with st.form("study_form_v3"):
                selected_topics = st.multiselect(
                    "Tópicos trabalhados",
                    topic_names,
                    placeholder="Opcional — selecione se quiser vincular o desempenho ao edital.",
                )

                phase = st.selectbox(
                    "Fase",
                    [1, 2, 3],
                    format_func=lambda x: f"Fase {x} — {PHASES[x]}",
                )

                default_minutes = (
                    round(st.session_state.timer_seconds / 60, 1)
                    if st.session_state.timer_seconds > 0
                    else float(current.get("block_minutes", 90))
                )

                minutes = st.number_input(
                    "Minutos líquidos",
                    min_value=0.0,
                    max_value=1440.0,
                    value=float(default_minutes),
                    step=5.0,
                )

                questions = st.number_input(
                    "Questões resolvidas",
                    min_value=0,
                    value=0,
                    step=1,
                )

                correct = st.number_input(
                    "Acertos",
                    min_value=0,
                    value=0,
                    step=1,
                )

                notes = st.text_area(
                    "Observação curta (opcional)",
                    height=80,
                )

                save = st.form_submit_button(
                    "✅ Registrar e avançar ciclo",
                    use_container_width=True,
                )

            if save:
                if correct > questions:
                    st.error("Acertos não podem ser maiores que questões.")
                elif minutes <= 0:
                    st.error("Informe um tempo líquido maior que zero.")
                else:
                    current_dt = datetime.now()
                    session_date = current_dt.date().isoformat()
                    accuracy = (
                        float(correct / questions * 100)
                        if questions > 0
                        else None
                    )

                    st.session_state.data["study_sessions"].append({
                        "id": new_id("session"),
                        "date": session_date,
                        "timestamp": current_dt.strftime("%Y-%m-%d %H:%M"),
                        "subject": subject,
                        "topic": ", ".join(selected_topics),
                        "phase": int(phase),
                        "minutes": float(minutes),
                        "questions": int(questions),
                        "correct": int(correct),
                        "accuracy": accuracy,
                        "notes": notes,
                    })

                    # Atualiza os tópicos somente quando selecionados.
                    for topic_name in selected_topics:
                        t = get_topic(subject, topic_name)
                        if not t:
                            continue

                        t["last_studied"] = session_date

                        if accuracy is not None:
                            t["accuracy"] = accuracy

                            if accuracy >= 70:
                                t["status"] = "Assimilado/Concluído"
                            elif t.get("status") not in [
                                "Concluído",
                                "Assimilado/Concluído",
                            ]:
                                t["status"] = "Lido/Estudado"
                        elif t.get("status") == "Não iniciado":
                            t["status"] = "Lido/Estudado"

                        # Revisão automática somente quando houve questões.
                        if int(phase) in [2, 3] and accuracy is not None:
                            schedule_next_review(
                                subject,
                                topic_name,
                                accuracy,
                            )

                    advance_cycle(subject)
                    reset_timer()
                    st.success(
                        "Bloco registrado. Próxima disciplina do ciclo definida."
                    )
                    st.rerun()

    st.divider()

    # Histórico recente — sem virar um "relatório".
    st.subheader("Últimos blocos")
    df = session_dataframe()

    if df.empty:
        st.info("Ainda não há sessões registradas.")
    else:
        recent = df.sort_values(
            ["parsed_date", "timestamp"],
            ascending=False,
        ).head(10)

        display = recent[
            ["date", "subject", "topic", "phase", "minutes", "questions", "correct"]
        ].copy()

        display.columns = [
            "Data",
            "Disciplina",
            "Tópico",
            "Fase",
            "Minutos",
            "Questões",
            "Acertos",
        ]

        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
        )


# ============================================================
# 4. CADERNO DE ERROS
# ============================================================

elif page == "❌ Erros":
    st.title("❌ Caderno de Erros")
    st.caption(
        "Registre o que você errou e, principalmente, qual foi o aprendizado."
    )

    subjects = all_subject_names()

    if subjects:
        with st.form("error_form_v3"):
            c1, c2 = st.columns(2)

            with c1:
                subject = st.selectbox("Disciplina", subjects)

            with c2:
                topic_names = [t["name"] for t in topics_for_subject(subject)]
                topic_options = ["Geral"] + topic_names
                topic = st.selectbox("Tópico", topic_options)

            reason = st.selectbox("Motivo do erro", ERROR_REASONS)

            statement = st.text_area(
                "Ponto crítico / enunciado resumido",
                height=110,
            )

            solution = st.text_area(
                "Aprendizado / solução",
                height=110,
            )

            priority = st.selectbox(
                "Prioridade",
                ["Alta", "Média", "Baixa"],
                index=1,
            )

            add_error = st.form_submit_button(
                "➕ Registrar erro",
                use_container_width=True,
            )

        if add_error:
            if not statement.strip() and not solution.strip():
                st.error("Registre pelo menos o ponto crítico ou o aprendizado.")
            else:
                st.session_state.data["errors"].append({
                    "id": new_id("err"),
                    "date": date.today().isoformat(),
                    "subject": subject,
                    "topic": topic,
                    "reason": reason,
                    "priority": priority,
                    "statement": statement.strip(),
                    "solution": solution.strip(),
                    # Compatibilidade com registros antigos:
                    "image_filename": "",
                })
                persist()
                st.success("Erro registrado.")
                st.rerun()

    st.divider()

    errors = st.session_state.data.get("errors", [])

    if not errors:
        st.info("Caderno de erros vazio.")
    else:
        st.metric("Erros registrados", len(errors))

        f1, f2, f3 = st.columns(3)

        with f1:
            subject_filter = st.selectbox(
                "Disciplina",
                ["Todas"] + sorted({e.get("subject", "") for e in errors}),
            )

        filtered = errors
        if subject_filter != "Todas":
            filtered = [
                e for e in filtered if e.get("subject") == subject_filter
            ]

        topics_filter = sorted(
            {
                e.get("topic", "")
                for e in filtered
                if e.get("topic")
            }
        )

        with f2:
            topic_filter = st.selectbox(
                "Tópico",
                ["Todos"] + topics_filter,
            )

        with f3:
            priority_filter = st.selectbox(
                "Prioridade",
                ["Todas", "Alta", "Média", "Baixa"],
            )

        if topic_filter != "Todos":
            filtered = [
                e for e in filtered if e.get("topic") == topic_filter
            ]

        if priority_filter != "Todas":
            filtered = [
                e for e in filtered if e.get("priority") == priority_filter
            ]

        st.markdown(f"**{len(filtered)} registro(s)**")

        for e in sorted(
            filtered,
            key=lambda x: x.get("date", ""),
            reverse=True,
        ):
            icon = {
                "Alta": "🔴",
                "Média": "🟡",
                "Baixa": "🟢",
            }.get(e.get("priority"), "⚪")

            title = (
                f"{icon} {e.get('subject', '')} • "
                f"{e.get('topic', 'Geral')} • "
                f"{e.get('reason', 'Outro')} • "
                f"{e.get('date', '')}"
            )

            with st.expander(title):
                st.markdown("**Ponto crítico**")
                st.info(e.get("statement") or "—")

                st.markdown("**Aprendizado / solução**")
                st.success(e.get("solution") or "—")

                img = e.get("image_filename")
                if img:
                    path = IMAGES_DIR / img
                    alt_path = RESUMOS_DIR / img

                    if path.exists():
                        st.image(str(path), caption=img)
                    elif alt_path.exists():
                        st.image(str(alt_path), caption=img)

                if st.button(
                    "🗑️ Excluir este erro",
                    key=f"delete_error_{e.get('id')}",
                ):
                    st.session_state.data["errors"] = [
                        x for x in st.session_state.data["errors"]
                        if x.get("id") != e.get("id")
                    ]
                    persist()
                    st.rerun()


# ============================================================
# 5. CONFIGURAÇÕES
# ============================================================

elif page == "⚙️ Configurações":
    st.title("⚙️ Configurações")
    st.caption(
        "Somente o que altera o funcionamento do painel. "
        "Backup e manutenção ficam aqui."
    )

    settings = st.session_state.data.setdefault("settings", {})
    daily = settings.setdefault(
        "daily_hours",
        {
            "Monday": 2.0,
            "Tuesday": 2.0,
            "Wednesday": 2.0,
            "Thursday": 2.0,
            "Friday": 2.0,
            "Saturday": 6.0,
            "Sunday": 6.0,
        },
    )

    st.subheader("🎯 Meta semanal")

    with st.form("settings_v3"):
        weekly_target = st.number_input(
            "Meta semanal de estudo líquido (h)",
            min_value=1.0,
            max_value=100.0,
            value=float(settings.get("weekly_target_hours", 22.0)),
            step=0.5,
        )

        st.markdown("**Horas disponíveis por dia**")

        day_labels = {
            "Monday": "Segunda",
            "Tuesday": "Terça",
            "Wednesday": "Quarta",
            "Thursday": "Quinta",
            "Friday": "Sexta",
            "Saturday": "Sábado",
            "Sunday": "Domingo",
        }

        day_cols = st.columns(7)
        new_daily = {}

        for col, (key, label) in zip(day_cols, day_labels.items()):
            with col:
                new_daily[key] = st.number_input(
                    label,
                    min_value=0.0,
                    max_value=24.0,
                    value=float(daily.get(key, 0.0)),
                    step=0.5,
                    key=f"day_{key}",
                )

        save_settings = st.form_submit_button(
            "💾 Salvar configurações",
            use_container_width=True,
        )

    if save_settings:
        settings["weekly_target_hours"] = float(weekly_target)
        settings["daily_hours"] = new_daily
        persist()
        st.success("Configurações salvas.")
        st.rerun()

    st.divider()

    # Backup
    st.subheader("💾 Backup do JSON")

    backup_payload = json.dumps(
        st.session_state.data,
        ensure_ascii=False,
        indent=2,
    )

    st.download_button(
        "⬇️ Baixar backup completo",
        data=backup_payload,
        file_name=f"backup_estudos_{date.today().isoformat()}.json",
        mime="application/json",
        use_container_width=True,
    )

    uploaded = st.file_uploader(
        "Restaurar backup JSON",
        type=["json"],
    )

    if uploaded is not None:
        if st.button("🔄 Restaurar backup", use_container_width=True):
            try:
                imported = json.load(uploaded)
                st.session_state.data = normalize_data(imported)
                persist()
                reset_timer()
                st.success("Backup restaurado.")
                st.rerun()
            except Exception as exc:
                st.error(f"JSON inválido: {exc}")

    st.divider()

    st.subheader("🧹 Limpeza de dados")

    st.caption(
        "Use somente para apagar registros de teste. "
        "O edital/disciplinas não são removidos."
    )

    c1, c2 = st.columns(2)

    with c1:
        if st.button("🗑️ Zerar sessões de estudo", use_container_width=True):
            st.session_state.data["study_sessions"] = []

            for t in st.session_state.data.get("topics", []):
                t["status"] = "Não iniciado"
                t["accuracy"] = None
                t["last_studied"] = None

            persist()
            st.success("Sessões zeradas.")
            st.rerun()

        if st.button("🗑️ Zerar caderno de erros", use_container_width=True):
            st.session_state.data["errors"] = []
            persist()
            st.success("Caderno de erros zerado.")
            st.rerun()

    with c2:
        if st.button("🗑️ Zerar revisões", use_container_width=True):
            st.session_state.data["revisoes"] = []
            persist()
            st.success("Revisões zeradas.")
            st.rerun()

        if st.button("⚠️ Zerar registros operacionais", use_container_width=True):
            st.session_state.data["study_sessions"] = []
            st.session_state.data["errors"] = []
            st.session_state.data["revisoes"] = []
            st.session_state.data["meetings"] = []

            for t in st.session_state.data.get("topics", []):
                t["status"] = "Não iniciado"
                t["accuracy"] = None
                t["last_studied"] = None

            persist()
            st.success("Registros operacionais zerados.")
            st.rerun()

    st.divider()

    st.subheader("ℹ️ Compatibilidade dos dados")
    st.write(
        "A V3 continua usando o arquivo `estudo_concursos_data.json`. "
        "Campos antigos como `resumos` e `meetings` são preservados no JSON, "
        "mesmo que não tenham mais uma tela própria."
    )
    st.code(str(DATA_FILE.resolve()), language="text")
    st.caption(f"Versão atual do painel: {VERSION}")
