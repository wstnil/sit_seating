"""
🎓 SEATING STUDIO — Premium Examination Seating & Report Suite
A beautiful Streamlit application for generating exam seating plans,
interactive seat maps and official PDF reports.

Run:  streamlit run app.py
"""

import os
import sys
import io
import re
import html
import zipfile
import tempfile
import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sit3  # seating engine (same folder)

st.set_page_config(
    page_title="Seating Studio — Premium Exam Seating Suite",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ════════════════════════════════════════════════════════════════════
#  THEMES
# ════════════════════════════════════════════════════════════════════
THEMES = {
    "Aurora": {
        "a1": "#6366F1", "a2": "#A855F7", "a3": "#22D3EE",
        "palette": ["#818CF8", "#34D399", "#F472B6", "#FBBF24", "#60A5FA",
                    "#A78BFA", "#F87171", "#2DD4BF", "#FDBA74", "#C084FC"],
    },
    "Sunset": {
        "a1": "#F97316", "a2": "#EF4444", "a3": "#FBBF24",
        "palette": ["#FB923C", "#F87171", "#FBBF24", "#F472B6", "#FDBA74",
                    "#E879F9", "#FDE047", "#FB7185", "#F59E0B", "#FCA5A5"],
    },
    "Ocean": {
        "a1": "#0EA5E9", "a2": "#6366F1", "a3": "#14B8A6",
        "palette": ["#38BDF8", "#2DD4BF", "#818CF8", "#60A5FA", "#22D3EE",
                    "#A5B4FC", "#34D399", "#93C5FD", "#5EEAD4", "#67E8F9"],
    },
    "Royal Gold": {
        "a1": "#D4AF37", "a2": "#92400E", "a3": "#F5D76E",
        "palette": ["#E5C158", "#CA8A04", "#F5D76E", "#B45309", "#EAB308",
                    "#D97706", "#FACC15", "#A16207", "#FDE68A", "#854D0E"],
    },
}

# ════════════════════════════════════════════════════════════════════
#  CSS
# ════════════════════════════════════════════════════════════════════
def build_css(t):
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Sora:wght@600;700;800&display=swap');

:root {{ --a1:{t['a1']}; --a2:{t['a2']}; --a3:{t['a3']}; }}

.stApp {{
    background:
        radial-gradient(1200px 700px at 85% -10%, {t['a1']}22, transparent 60%),
        radial-gradient(1000px 600px at -10% 110%, {t['a2']}1E, transparent 60%),
        radial-gradient(600px 400px at 50% 50%, {t['a3']}0D, transparent 70%),
        #0A0E1A;
    color: #E5E7EB;
    font-family: 'Inter', system-ui, sans-serif;
}}
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: transparent; }}

/* ---------- TYPO ---------- */
h1, h2, h3, .stTabs button span {{ font-family: 'Sora', 'Inter', sans-serif !important; }}

/* ---------- SIDEBAR ---------- */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, rgba(17,24,39,.96), rgba(10,14,26,.96));
    border-right: 1px solid rgba(255,255,255,.07);
}}
[data-testid="stSidebar"] * {{ color: #D1D5DB; }}
[data-testid="stSidebar"] .stTextInput label, [data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stSelectbox label, [data-testid="stSidebar"] .stCheckbox label,
[data-testid="stSidebar"] .stFileUploader label, [data-testid="stSidebar"] .stTextArea label {{
    font-weight: 600 !important; color: #9CA3AF !important; font-size: .82rem;
}}

/* ---------- WIDGETS ---------- */
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stNumberInput"] input {{
    background: rgba(255,255,255,.05) !important; border: 1px solid rgba(255,255,255,.12) !important;
    border-radius: 12px !important; color: #F3F4F6 !important;
}}
[data-testid="stTextInput"] input::placeholder {{ color: #6B7280 !important; }}
[data-testid="stTextInput"] input:focus {{
    border-color: var(--a1) !important; box-shadow: 0 0 0 3px {t['a1']}33 !important;
}}
[data-testid="stFileUploaderDropzone"] {{
    background: rgba(255,255,255,.05) !important; border: 1.5px dashed rgba(255,255,255,.22) !important;
    border-radius: 14px !important;
}}
[data-testid="stFileUploaderDropzone"] * {{ color: #9CA3AF !important; }}
[data-testid="stFileUploaderDropzone"] button {{
    background: rgba(255,255,255,.08) !important; color: #E5E7EB !important;
    border: 1px solid rgba(255,255,255,.16) !important; box-shadow: none !important; border-radius: 10px !important;
}}
[data-testid="stToolbar"] {{ display: none !important; }}
.stButton>button {{
    background: linear-gradient(135deg, var(--a1), var(--a2)) !important; color: #fff !important;
    border: none !important; border-radius: 14px !important; font-weight: 800 !important;
    letter-spacing: .3px; padding: .55rem 1rem !important;
    box-shadow: 0 10px 28px {t['a1']}55 !important; transition: all .18s ease;
}}
.stButton>button:hover {{ transform: translateY(-2px); filter: brightness(1.1); }}
.stButton>button[kind="secondary"] {{
    background: rgba(255,255,255,.06) !important; border: 1px solid rgba(255,255,255,.16) !important;
    box-shadow: none !important; color: #E5E7EB !important;
}}
.stDownloadButton>button {{
    background: linear-gradient(135deg, #10B981, #059669) !important; color: #fff !important;
    border: none !important; border-radius: 14px !important; font-weight: 800 !important;
    box-shadow: 0 10px 28px rgba(16,185,129,.4) !important;
}}
.stFileUploader>div {{
    background: rgba(255,255,255,.04); border: 1.5px dashed rgba(255,255,255,.2);
    border-radius: 16px; padding: 8px;
}}
.stSlider>div>div>div {{ background: linear-gradient(90deg, var(--a1), var(--a2)) !important; }}

/* ---------- TABS ---------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; background: rgba(255,255,255,.03);
    padding: 6px; border-radius: 16px; border: 1px solid rgba(255,255,255,.06); }}
.stTabs [data-baseweb="tab"] {{ border-radius: 12px; padding: 6px 18px; }}
.stTabs [aria-selected="true"] {{ background: linear-gradient(135deg, {t['a1']}33, {t['a2']}33) !important; }}
.stTabs [aria-selected="true"] span {{ color: #fff !important; font-weight: 700; }}

/* ---------- DATAFRAME ---------- */
[data-testid="stDataFrame"] {{ border: 1px solid rgba(255,255,255,.08); border-radius: 16px; overflow: hidden; }}

/* ---------- EXPANDER / ALERTS ---------- */
[data-testid="stExpander"] {{
    background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.08);
    border-radius: 16px;
}}
div[data-testid="stAlert"] {{ border-radius: 14px; }}

/* ---------- CUSTOM CARDS ---------- */
.hero {{
    background: linear-gradient(135deg, {t['a1']}26, {t['a2']}1A 55%, {t['a3']}14);
    border: 1px solid rgba(255,255,255,.1); border-radius: 24px; padding: 34px 38px;
    position: relative; overflow: hidden;
}}
.hero::before {{
    content: ''; position: absolute; top: -70px; right: -70px; width: 260px; height: 260px;
    background: radial-gradient(circle, {t['a1']}44, transparent 70%); border-radius: 50%;
}}
.hero h1 {{
    font-size: 2.6rem; margin: 0 0 6px; font-weight: 800;
    background: linear-gradient(90deg, #fff, {t['a3']});
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
.hero p {{ margin: 0; color: #9CA3AF; font-size: 1.02rem; }}

.metric {{
    background: linear-gradient(160deg, rgba(255,255,255,.06), rgba(255,255,255,.02));
    border: 1px solid rgba(255,255,255,.09); border-radius: 18px; padding: 18px 20px;
    height: 100%; transition: all .2s ease; position: relative; overflow: hidden;
}}
.metric:hover {{ transform: translateY(-3px); border-color: {t['a1']}66; box-shadow: 0 14px 34px {t['a1']}2E; }}
.metric .ic {{ font-size: 1.5rem; }}
.metric .v {{ font-family: 'Sora', sans-serif; font-size: 1.9rem; font-weight: 800; color: #fff; line-height: 1.15; }}
.metric .l {{ font-size: .8rem; color: #9CA3AF; font-weight: 600; letter-spacing: .4px; text-transform: uppercase; }}

.feature {{
    background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.08);
    border-radius: 18px; padding: 20px; height: 100%;
}}
.feature .fi {{ font-size: 1.6rem; margin-bottom: 8px; }}
.feature b {{ color: #F9FAFB; }}
.feature p {{ color: #9CA3AF; font-size: .88rem; margin: 4px 0 0; }}

/* ---------- SEATMAP ---------- */
.studio-card {{
    background: linear-gradient(165deg, rgba(255,255,255,.055), rgba(255,255,255,.02));
    border: 1px solid rgba(255,255,255,.09); border-radius: 22px; padding: 20px 22px;
    height: 100%;
}}
.block-head {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 4px; }}
.bno {{
    background: linear-gradient(135deg, var(--a1), var(--a2)); color: #fff; font-weight: 800;
    font-family: 'Sora', sans-serif; padding: 5px 14px; border-radius: 12px; font-size: .95rem;
    box-shadow: 0 6px 18px {t['a1']}44;
}}
.bsubj {{ font-weight: 700; color: #F9FAFB; font-size: .92rem; }}
.bpill {{
    margin-left: auto; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.12);
    padding: 4px 12px; border-radius: 999px; color: #D1D5DB; font-size: .75rem; font-weight: 600;
}}
.fillbar {{ height: 6px; background: rgba(255,255,255,.07); border-radius: 99px; overflow: hidden; margin: 10px 0 14px; }}
.fillbar>span {{ display: block; height: 100%; border-radius: 99px;
    background: linear-gradient(90deg, var(--a1), var(--a3)); }}
.board {{
    text-align: center; letter-spacing: 7px; font-weight: 800; font-size: .8rem;
    color: #93C5FD; background: linear-gradient(90deg, #111827, #1F2937, #111827);
    border: 1px solid rgba(255,255,255,.1); border-radius: 10px; padding: 9px 4px;
}}
.desk {{
    background: rgba(255,255,255,.045); border: 1px dashed rgba(255,255,255,.22);
    border-radius: 9px; padding: 5px; text-align: center; color: #CBD5E1;
    font-size: .74rem; font-weight: 600; margin: 8px 0 14px; letter-spacing: 1px;
}}
.seatgrid {{ display: grid; grid-template-columns: repeat(var(--cols), 1fr); gap: 8px; }}
.seat {{
    background: color-mix(in srgb, var(--c) 10%, rgba(255,255,255,.02));
    border: 1px solid color-mix(in srgb, var(--c) 30%, transparent);
    border-top: 3px solid var(--c); border-radius: 12px; padding: 7px 8px 6px;
    min-height: 58px; transition: transform .15s ease, box-shadow .15s ease; overflow: hidden;
}}
.seat:hover {{ transform: translateY(-2px) scale(1.02); box-shadow: 0 10px 22px {t['a1']}33; }}
.seat .sn {{ font-weight: 800; color: var(--c); font-size: .62rem; letter-spacing: .6px; text-transform: uppercase; }}
.seat .nm {{ font-size: .74rem; font-weight: 600; color: #F3F4F6; line-height: 1.25;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
.seat .pr {{ font-size: .64rem; color: #9CA3AF; font-family: ui-monospace, monospace; margin-top: 2px; }}
.seat .st {{ font-size: .62rem; color: #6B7280; }}
.aisle {{ height: 10px; grid-column: 1 / -1; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
.lchip {{
    display: inline-flex; align-items: center; gap: 7px; background: rgba(255,255,255,.04);
    border: 1px solid rgba(255,255,255,.09); padding: 5px 12px; border-radius: 999px;
    font-size: .74rem; color: #D1D5DB; font-weight: 600;
}}
.ldot {{ width: 10px; height: 10px; border-radius: 50%; }}

.sect-title {{ font-family: 'Sora', sans-serif; font-weight: 800; font-size: 1.15rem; color: #F9FAFB; margin: 0 0 2px; }}
.sect-sub {{ color: #9CA3AF; font-size: .85rem; margin: 0 0 14px; }}
.mini-note {{ color: #6B7280; font-size: .74rem; }}
::-webkit-scrollbar {{ width: 9px; height: 9px; }}
::-webkit-scrollbar-thumb {{ background: {t['a1']}55; border-radius: 99px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
</style>
"""

# ════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════
def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d.columns = d.columns.str.strip().str.replace(r"\.", "", regex=True).str.replace(" ", "_")
    return d


@st.cache_data(show_spinner=False)
def read_csv_cached(raw_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(raw_bytes), dtype=str)


def detect_institute(df: pd.DataFrame) -> dict:
    d = normalize_cols(df)
    name = code = ""
    if "Exam_Center_Name" in d.columns:
        s = d["Exam_Center_Name"].dropna()
        if len(s):
            name = str(s.iloc[0]).strip()
    if "Exam_Center_Code" in d.columns:
        s = d["Exam_Center_Code"].dropna()
        if len(s):
            code = str(s.iloc[0]).strip()
    return {"name": name, "code": code}


def parse_capacity_override(txt: str):
    txt = (txt or "").strip()
    if not txt:
        return None
    if "=" in txt:
        out = {}
        for pair in txt.split(","):
            pair = pair.strip()
            if not pair:
                continue
            b, c = pair.split("=", 1)
            out[b.strip()] = int(c.strip())
        return out
    return int(txt)


def subject_code_of(subj_disp: str) -> str:
    s = str(subj_disp or "")
    return s.split(" - ")[0].strip() if " - " in s else s.strip()


def date_sort_key(d: str):
    for fmt in ("%d-%m-%Y", "%d-%m-%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(str(d).split(" ")[0], fmt)
        except Exception:
            continue
    return dt.datetime.max


def block_num_key(b):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", str(b))]


def build_block_list(plan_result: dict) -> list:
    seats = plan_result["plan"]["seating_arrangement_dict"]
    blocks = []
    for (d, s, inst, bno), rows in seats.items():
        subj = rows[0][2] if rows else ""
        prog = rows[0][1] if rows else ""
        subject_counts = {}
        for row in rows:
            code = subject_code_of(row[2]) if len(row) > 2 else ""
            if code:
                subject_counts[code] = subject_counts.get(code, 0) + 1
        blocks.append({
            "date": str(d), "session": str(s), "inst": str(inst), "block": str(bno),
            "rows": rows, "subject": subj, "subjects": list(subject_counts),
            "subject_counts": subject_counts, "program": prog, "count": len(rows),
        })
    blocks.sort(key=lambda b: (date_sort_key(b["date"]), b["session"], block_num_key(b["block"])))
    return blocks


def assign_subject_colors(blocks: list, palette: list) -> dict:
    mapping, i = {}, 0
    for b in blocks:
        for code in b["subjects"]:
            if code not in mapping:
                mapping[code] = palette[i % len(palette)]
                i += 1
    return mapping


def make_zip_bytes(root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(Path(root).rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(root))
    return buf.getvalue()


def metric_card(icon: str, value, label: str) -> str:
    return f"""<div class="metric"><div class="ic">{icon}</div>
    <div class="v">{value}</div><div class="l">{html.escape(str(label))}</div></div>"""


# ════════════════════════════════════════════════════════════════════
#  SESSION STATE DEFAULTS
# ════════════════════════════════════════════════════════════════════
st.session_state.setdefault("exam_heading", sit3.DEFAULT_EXAM_HEADING)
st.session_state.setdefault("college_name", "")
st.session_state.setdefault("institute_code", "")
st.session_state.setdefault("file_key", "")
st.session_state.setdefault("plan", None)
st.session_state.setdefault("plan_config", None)

theme_name = st.session_state.get("theme_sel", "Aurora")
theme = THEMES.get(theme_name, THEMES["Aurora"])

st.markdown(build_css(theme), unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:12px;margin:6px 0 2px;">
        <div style="width:44px;height:44px;border-radius:14px;display:flex;align-items:center;justify-content:center;
        font-size:1.4rem;background:linear-gradient(135deg,{theme['a1']},{theme['a2']});box-shadow:0 8px 22px {theme['a1']}66;">🎓</div>
        <div><div style="font-family:'Sora';font-weight:800;font-size:1.12rem;color:#fff;">Seating Studio</div>
        <div style="font-size:.72rem;color:#9CA3AF;">Premium Exam Seating Suite</div></div></div>""",
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown("**📂 1 · Student Data**")
    uploaded = st.file_uploader("Upload Student List (CSV)", type=["csv"], label_visibility="collapsed")

    df_raw = None
    if uploaded is not None:
        try:
            df_raw = read_csv_cached(uploaded.getvalue())
        except Exception as e:
            st.error(f"Could not read CSV: {e}")

        new_key = f"{uploaded.name}|{uploaded.size}|{len(df_raw)}"
        if st.session_state["file_key"] != new_key:
            st.session_state["file_key"] = new_key
            auto = detect_institute(df_raw)
            st.session_state["college_name"] = auto["name"]
            st.session_state["institute_code"] = auto["code"]
            st.session_state["plan"] = None
        st.caption(f"✅ **{uploaded.name}** — {len(df_raw):,} rows loaded")

    logo_file = st.file_uploader("🏫 College Logo (optional PNG)", type=["png", "jpg", "jpeg"], label_visibility="visible")
    logo_path = None
    if logo_file is not None:
        logo_path = os.path.join(tempfile.gettempdir(), f"studio_logo_{logo_file.name}")
        with open(logo_path, "wb") as f:
            f.write(logo_file.getvalue())

    st.divider()
    st.markdown("**🏛️ 2 · Headings**")
    college = st.text_input("College Heading", key="college_name", placeholder="e.g. Sharad Institute of Technology")
    inst_code = st.text_input("Institute Code", key="institute_code", placeholder="e.g. EN6317")
    exam_heading = st.text_input("Exam Heading (subtitle on reports)", key="exam_heading")

    st.divider()
    st.markdown("**🪑 3 · Seating Options**")
    capacity = st.slider("Block Capacity (students per block)", 5, 150, 30, help="Every generated block holds at most this many students")
    per_block = st.text_input("Per-block override (optional)", placeholder="e.g. 1=30, 2=45")

    st.divider()
    st.markdown("**🎨 4 · Seat Map Style**")
    theme_name = st.selectbox("Colour Theme", list(THEMES.keys()), key="theme_sel")
    seats_per_row = st.slider("Seats per row", 2, 10, 6)
    aisle_every = st.slider("Rows before aisle gap", 1, 5, 2)
    show_prn = st.checkbox("Show PRN on seats", value=True, key="show_prn")
    show_seatno = st.checkbox("Show official Seat No. on seats", value=False, key="show_seatno")

    st.divider()
    generate_btn = st.button("✨  Generate Seating Plan", type="primary", width="stretch")
    st.caption("v1.0 · powered by the sit3 seating engine")

# ════════════════════════════════════════════════════════════════════
#  PLAN GENERATION
# ════════════════════════════════════════════════════════════════════
if generate_btn:
    if uploaded is None or df_raw is None:
        st.sidebar.error("⚠️ Please upload a student list CSV first.")
    else:
        try:
            with st.spinner("🏗️ Architecting your seating plan…"):
                block_nums = []
                if "Block_Number" in normalize_cols(df_raw).columns:
                    block_nums = [str(b).strip().split(".")[0] for b in normalize_cols(df_raw)["Block_Number"].dropna().unique()]
                override = parse_capacity_override(per_block)
                if isinstance(override, dict):
                    merged = {b: capacity for b in block_nums if b}
                    merged.update(override)
                    override = merged
                elif override is None and capacity != 30:
                    override = capacity
                result = sit3.create_directories_and_pdfs(
                    df_raw.copy(),
                    parent_dir=tempfile.gettempdir(),
                    custom_institute_name=college,
                    block_capacity_override=override,
                    exam_heading=exam_heading,
                    institute_code_override=inst_code,
                    logo_path=logo_path,
                    generate_pdfs=False,
                )
            st.session_state["plan"] = result
            st.session_state["plan_config"] = {
                "capacity": capacity,
                "seats_per_row": seats_per_row,
                "aisle_every": aisle_every,
                "show_prn": show_prn,
                "show_seatno": show_seatno,
                "override": override,
            }
            st.sidebar.success(f"✅ Plan ready — {result['total_blocks']} blocks · {result['total_students']:,} students")
        except Exception as e:
            st.sidebar.error(f"❌ {e}")

# ════════════════════════════════════════════════════════════════════
#  MAIN AREA
# ════════════════════════════════════════════════════════════════════
if st.session_state.get("plan") is None:
    st.markdown(
        f"""<div class="hero"><h1>🎓 Seating Studio</h1>
        <p>Premium examination seating — design block plans, preview interactive seat maps
        and export official PDF reports in minutes.</p></div>""",
        unsafe_allow_html=True,
    )
    st.write("")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown('<div class="feature"><div class="fi">🪑</div><b>Smart Blocks</b><p>Auto-split students into capacity-bounded blocks with clean sequential numbering.</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="feature"><div class="fi">🗺️</div><b>Live Seat Map</b><p>Colour-coded interactive seat map per block — hover any seat for details.</p></div>', unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="feature"><div class="fi">🎨</div><b>Full Customization</b><p>College heading, exam heading, logo, themes, seats-per-row, aisles — your call.</p></div>', unsafe_allow_html=True)
    with c4:
        st.markdown('<div class="feature"><div class="fi">📥</div><b>One-Click PDFs</b><p>Seating charts, attendance sheets, supervisor & answer-book reports as a ZIP.</p></div>', unsafe_allow_html=True)
    st.info("👈 **Start here:** upload your student list CSV in the sidebar, set your headings & capacity, then hit **Generate Seating Plan**.")
    st.stop()

# ---- plan loaded ----
if df_raw is None:
    st.warning("⚠️ Student CSV removed — please re-upload the file in the sidebar.")
    st.stop()

plan = st.session_state["plan"]
cfg = st.session_state["plan_config"]
blocks = build_block_list(plan)
cmap = assign_subject_colors(blocks, theme["palette"])

st.markdown(
    f"""<div class="hero" style="padding:22px 30px;"><h1 style="font-size:1.7rem;">🏛️ {html.escape(plan['institute_name'])}</h1>
    <p>{html.escape(plan['exam_heading'])} · Code {html.escape(plan.get('institute_code') or '—')}</p></div>""",
    unsafe_allow_html=True,
)
st.write("")

tab_over, tab_map, tab_rep, tab_data = st.tabs(["📊 Overview", "🪑 Seat Map", "📥 Reports", "🗂️ Data"])

# ════════════════════════════════════════════════════════════════════
#  TAB 1 — OVERVIEW
# ════════════════════════════════════════════════════════════════════
with tab_over:
    total_students = plan["total_students"]
    n_blocks = len(blocks)
    subjects = sorted({code for b in blocks for code in b["subjects"]})
    days = sorted({b["date"] for b in blocks}, key=date_sort_key)
    avg_fill = (sum(b["count"] for b in blocks) / max(1, sum(cfg["capacity"] for _ in blocks))) * 100

    m = st.columns(6)
    for col, (ic, v, l) in zip(
        m,
        [("👥", f"{total_students:,}", "Students"), ("🧱", n_blocks, "Blocks"),
         ("📚", len(subjects), "Subjects"), ("📅", len(days), "Exam Days"),
         ("🪑", cfg["capacity"], "Capacity / Block"), ("📈", f"{avg_fill:.0f}%", "Avg Fill")],
    ):
        col.markdown(metric_card(ic, v, l), unsafe_allow_html=True)

    st.write("")
    left, right = st.columns([3, 2])

    with left:
        st.markdown('<p class="sect-title">🗓️ Session-wise Schedule</p><p class="sect-sub">Students aggregated per exam date & session</p>', unsafe_allow_html=True)
        sched = {}
        for b in blocks:
            sched.setdefault((b["date"], b["session"]), {"subj": set(), "students": 0, "blocks": 0})
            sched[(b["date"], b["session"])]["subj"].update(b["subjects"])
            sched[(b["date"], b["session"])]["students"] += b["count"]
            sched[(b["date"], b["session"])]["blocks"] += 1
        sched_df = pd.DataFrame([
            {"Exam Date": d, "Session": sit3.format_session_label(s),
             "Subjects": len(v["subj"]), "Students": v["students"], "Blocks": v["blocks"]}
            for (d, s), v in sorted(sched.items(), key=lambda kv: (date_sort_key(kv[0][0]), kv[0][1]))
        ])
        st.dataframe(sched_df, width="stretch", hide_index=True, height=260)

    with right:
        st.markdown('<p class="sect-title">📚 Students per Subject</p><p class="sect-sub">Distribution across course codes</p>', unsafe_allow_html=True)
        subj_counts = pd.Series({c: sum(b["subject_counts"].get(c, 0) for b in blocks) for c in subjects}).sort_values(ascending=False)
        st.bar_chart(subj_counts, height=300, color=theme["a1"])

    st.markdown('<p class="sect-title">🧱 Block Utilisation</p><p class="sect-sub">Fill level of every generated block</p>', unsafe_allow_html=True)
    util = pd.Series({f"B{b['block']} ({b['date']})": b["count"] for b in blocks})
    st.bar_chart(util, height=280, color=theme["a3"])

# ════════════════════════════════════════════════════════════════════
#  TAB 2 — SEAT MAP
# ════════════════════════════════════════════════════════════════════
with tab_map:
    st.markdown('<p class="sect-title">🗺️ Interactive Seat Map</p><p class="sect-sub">Pick a date & session, choose blocks — hover any seat for student details</p>', unsafe_allow_html=True)

    all_dates = sorted({b["date"] for b in blocks}, key=date_sort_key)
    f1, f2, f3 = st.columns([1.2, 1.6, 2.2])
    date_sel = f1.selectbox("📅 Exam Date", all_dates, key="map_date")
    sess_list = sorted({b["session"] for b in blocks if b["date"] == date_sel})
    sess_sel = f2.selectbox("⏰ Session", sess_list, key="map_session",
                            format_func=lambda s: sit3.format_session_label(s))
    blocks_for_sel = [b for b in blocks if b["date"] == date_sel and b["session"] == sess_sel]
    block_labels = [f"Block {b['block']} · {', '.join(b['subjects'])} ({b['count']})" for b in blocks_for_sel]
    default_sel = block_labels[:6] if len(block_labels) > 6 else block_labels
    chosen = f3.multiselect("🧱 Blocks to display", block_labels, default=default_sel, key="map_blocks")

    chosen_blocks = [b for b, lbl in zip(blocks_for_sel, block_labels) if lbl in chosen]

    if chosen_blocks:
        legend_codes = []
        for b in chosen_blocks:
            for c in b["subjects"]:
                if c not in legend_codes:
                    legend_codes.append(c)
        legend_items = "".join(
            f'<span class="lchip"><span class="ldot" style="background:{cmap.get(c, "#94A3B8")}"></span>'
            f'{html.escape(c)}</span>'
            for c in legend_codes
        )
        st.markdown(f'<div class="legend">{legend_items}</div>', unsafe_allow_html=True)
        st.write("")

        for i in range(0, len(chosen_blocks), 2):
            pair = chosen_blocks[i:i + 2]
            cols = st.columns(2)
            for col, b in zip(cols, pair):
                with col:
                    rows = b["rows"]
                    n = len(rows)
                    cap = cfg["capacity"]
                    fill = min(100, int(n / max(1, cap) * 100))
                    parts = []
                    for idx, row in enumerate(rows):
                        if idx and idx % cfg["seats_per_row"] == 0 and (idx // cfg["seats_per_row"]) % cfg["aisle_every"] == 0:
                            parts.append('<div class="aisle"></div>')
                        _, prog, subj, seat_no, prn, name = (list(row) + [""] * 6)[:6]
                        color = cmap.get(subject_code_of(subj), "#94A3B8")
                        tooltip = html.escape(f"Seat {idx+1} · {prn} · {name} · {subj}")
                        nm = html.escape(str(name or "—"))
                        prn_line = f'<div class="pr">{html.escape(str(prn or ""))}</div>' if cfg["show_prn"] else ""
                        seat_line = f'<div class="st">🎟️ {html.escape(str(seat_no or ""))}</div>' if cfg["show_seatno"] and str(seat_no or "").strip() else ""
                        parts.append(
                            f'<div class="seat" style="--c:{color}" title="{tooltip}">'
                            f'<div class="sn">Seat {idx+1:02d}</div><div class="nm">{nm}</div>{prn_line}{seat_line}</div>'
                        )
                    card = f"""<div class="studio-card">
                        <div class="block-head"><span class="bno">🪑 Block {html.escape(b['block'])}</span>
                        <span class="bsubj">{html.escape(', '.join(b['subjects']))}</span>
                        <span class="bpill">👥 {n} / {cap} seats · {fill}%</span></div>
                        <div class="fillbar"><span style="width:{fill}%"></span></div>
                        <div class="board">✦ &nbsp;B L A C K B O A R D&nbsp; ✦</div>
                        <div class="desk">🧑‍💼 BLOCK SUPERVISOR DESK</div>
                        <div class="seatgrid" style="--cols:{cfg['seats_per_row']};">{''.join(parts)}</div>
                    </div>"""
                    st.markdown(card, unsafe_allow_html=True)
    else:
        st.warning("Select at least one block to view its seat map.")

# ════════════════════════════════════════════════════════════════════
#  TAB 3 — REPORTS
# ════════════════════════════════════════════════════════════════════
with tab_rep:
    st.markdown('<p class="sect-title">📥 Official PDF Report Suite</p><p class="sect-sub">Generate the complete deliverable pack — seating charts, attendance, supervision & answer-book reports</p>', unsafe_allow_html=True)

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(
            """<div class="feature"><b>What's inside the ZIP?</b>
            <p>• College Block Arrangement Report (per day)<br/>
            • Block Seating Arrangement charts (per block)<br/>
            • Attendance Sheets (per block)<br/>
            • Junior Supervisor Reports & Answer-Book Collection sheets<br/>
            • Summary of Supervision + Group Summary Statement + Seat Number Summary</p></div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""<div class="metric"><div class="ic">🏷️</div><div class="l">Heading on all reports</div>
            <div class="v" style="font-size:1rem;line-height:1.4;">{html.escape(plan['exam_heading'])}</div>
            <div class="l" style="margin-top:8px;">🏛️ {html.escape(plan['institute_name'])}</div></div>""",
            unsafe_allow_html=True,
        )

    st.write("")
    export_btn = st.button("🎬 Generate All PDF Reports", type="primary", use_container_width=False)

    if export_btn:
        out_dir = tempfile.mkdtemp(prefix="seating_reports_")
        prog = st.progress(0.0, text="⚙️ Preparing seating engine…")
        last_stage = {"v": 0.0}

        def cb(i, n, msg):
            frac = min(0.95, (i / max(1, n)) * 0.95)
            if frac > last_stage["v"]:
                last_stage["v"] = frac
                prog.progress(frac, text=msg)

        try:
            with st.spinner("🖨️ Printing official reports…"):
                sit3.create_directories_and_pdfs(
                    df_raw.copy(),
                    parent_dir=out_dir,
                    progress_callback=cb,
                    custom_institute_name=st.session_state.get("college_name", ""),
                    block_capacity_override=cfg.get("override"),
                    exam_heading=plan["exam_heading"],
                    institute_code_override=st.session_state.get("institute_code", ""),
                    logo_path=logo_path,
                    generate_pdfs=True,
                )
            prog.progress(1.0, text="✅ All reports generated!")

            files = sorted(Path(out_dir).rglob("*.pdf"))
            total_kb = sum(f.stat().st_size for f in files) / 1024
            zip_bytes = make_zip_bytes(Path(out_dir))
            st.success(f"🎉 **{len(files)} PDF reports** generated ({total_kb:,.0f} KB) — ready to download!")

            st.download_button(
                "⬇️  Download All Reports (ZIP)",
                data=zip_bytes,
                file_name="seating_reports.zip",
                mime="application/zip",
                width="stretch",
            )

            with st.expander(f"📄 View generated files ({len(files)})"):
                for f in files:
                    rel = f.relative_to(out_dir)
                    st.markdown(f"`{rel}` &nbsp; <span class='mini-note'>({f.stat().st_size/1024:.0f} KB)</span>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"❌ Report generation failed: {e}")

# ════════════════════════════════════════════════════════════════════
#  TAB 4 — DATA
# ════════════════════════════════════════════════════════════════════
with tab_data:
    st.markdown('<p class="sect-title">🗂️ Uploaded Student Data</p><p class="sect-sub">Raw CSV preview — the engine automatically filters invalid form statuses and empty keys</p>', unsafe_allow_html=True)
    d1, d2, d3 = st.columns(3)
    d1.markdown(metric_card("📋", f"{len(df_raw):,}", "Rows in CSV"), unsafe_allow_html=True)
    d2.markdown(metric_card("✅", f"{plan['total_students']:,}", "Students seated"), unsafe_allow_html=True)
    d3.markdown(metric_card("🧹", f"{len(df_raw) - plan['total_students']:,}", "Rows filtered out"), unsafe_allow_html=True)
    st.write("")
    st.dataframe(df_raw, width="stretch", height=420)
