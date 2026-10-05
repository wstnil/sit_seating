# 🎓 Seating Studio — Premium Examination Seating Suite

A beautiful, professional **Streamlit** application for planning exam seating,
previewing interactive **seat maps**, and exporting **official PDF report packs**.

Powered by the proven `sit3` seating engine (capacity-bounded blocks, clean
sequential block numbering, formatted session names).

---

## 🚀 Quick Start

```bash
# 1. Install dependencies (once)
pip install -r requirements.txt

# 2. Launch the studio
streamlit run app.py
```

The app opens in your browser (default: http://localhost:8501).

---

## 🧭 How to Use

1. **📂 Upload** — drop your student list CSV (same format as `sem7sl.csv`)
   in the sidebar. College name & institute code are auto-detected.
2. **🏛️ Headings** — edit the *College Heading*, *Institute Code* and
   *Exam Heading* printed on every report. Optionally upload a college logo (PNG).
3. **🪑 Seating Options**
   - *Block Capacity* slider — every block holds at most this many students (default 30).
   - *Per-block override* — e.g. `1=30, 2=45` to give specific blocks different limits.
4. **🎨 Seat Map Style** — choose a colour theme (Aurora / Sunset / Ocean / Royal Gold),
   seats per row, aisle gap frequency, and whether seats show PRN / official seat numbers.
5. **✨ Generate Seating Plan** — builds the plan instantly, then explore:
   - **📊 Overview** — KPI cards, session schedule, subject & block-utilisation charts.
   - **🪑 Seat Map** — interactive, colour-coded seats (hover for PRN/name/subject),
     blackboard & supervisor desk layout, block fill bars.
   - **📥 Reports** — one click generates the full PDF pack and a ZIP download:
     block arrangement report, seating charts, attendance sheets, junior-supervisor
     reports, answer-book collection sheets, summary of supervision, group summary
     statement and seat-number summary.
   - **🗂️ Data** — raw CSV preview with seated vs filtered row counts.

---

## 📁 Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI (Seating Studio) |
| `sit3.py` | Seating engine — plan builder + PDF generators (also runs standalone as a CLI) |
| `requirements.txt` | Python dependencies |

## 🖥️ CLI Mode (optional)

The engine still works exactly like the original script:

```bash
python sit3.py sem7sl.csv
python sit3.py sem7sl.csv --block_capacity 40
python sit3.py sem7sl.csv --block_capacity 1=30,2=45
python sit3.py sem7sl.csv --exam_heading "Your Exam Title"
```

---

## 💡 Tips

- Windows forbids `:` in folder names — session times are automatically formatted
  as `10.00 AM - 12.00 PM` for folders and PDF headings.
- Blocks are numbered cleanly (1, 2, 3 …) per exam date & session and never exceed
  the configured capacity.
- Re-generate anytime — changing capacity or headings and pressing
  **Generate Seating Plan** rebuilds everything.
