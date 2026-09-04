import os
import json
import streamlit as st
from dotenv import load_dotenv
from google import genai
from extractor import process_book_pdf

load_dotenv()

# Multi-environment API Key Resolution
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        api_key = None

client = genai.Client(api_key=api_key) if api_key else None

st.set_page_config(
    page_title="JEE Advanced Physics Question Engine",
    page_icon="⚛️",
    layout="wide"
)

DB_PATH = "database/questions_db.json"

def load_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_db(data):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

st.title("⚛️ JEE Advanced Physics Question Engine")

tabs = st.tabs([
    "📥 1. Ingest Physics Book",
    "📝 2. Assemble Test Paper",
    "📚 3. Question Bank Management"
])

# ==========================================
# TAB 1: INGEST PHYSICS BOOK
# ==========================================
with tabs[0]:
    st.header("Extract Problems from Textbook PDF")
    
    uploaded_pdf = st.file_uploader("Upload Physics Book (PDF)", type=["pdf"])
    col1, col2, col3 = st.columns(3)
    with col1:
        book_title = st.text_input("Book Identifier / Title", value="Irodov")
    with col2:
        start_page = st.number_input("Start Page", min_value=1, value=1, step=1)
    with col3:
        end_page = st.number_input("End Page", min_value=1, value=3, step=1)

    if st.button("Extract Problems with Gemini"):
        if not uploaded_pdf:
            st.error("Please upload a PDF file first.")
        else:
            temp_pdf_path = f"temp_{uploaded_pdf.name}"
            with open(temp_pdf_path, "wb") as f:
                f.write(uploaded_pdf.get_buffer())

            with st.spinner("Processing pages, cropping diagrams, and extracting LaTeX..."):
                count = process_book_pdf(
                    pdf_path=temp_pdf_path,
                    book_title=book_title,
                    start_page=int(start_page),
                    end_page=int(end_page),
                    db_path=DB_PATH
                )
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)

            st.success(f"Extracted and indexed {count} problem(s) successfully!")
            st.rerun()

# ==========================================
# TAB 2: ASSEMBLE TEST PAPER
# ==========================================
with tabs[1]:
    st.header("Configure & Assemble JEE Advanced Test Paper")
    questions = load_db()

    if not questions:
        st.warning("Database empty. Run Ingest in Tab 1 first.")
    else:
        all_topics = sorted(list({q.get("topic", "General") for q in questions if q.get("topic")}))

        col1, col2, col3 = st.columns(3)
        with col1:
            selected_topic = st.selectbox("Filter by Topic", ["All Topics"] + all_topics)
        with col2:
            q_types = ["All Types", "Single Correct (SCQ)", "Multiple Correct (MCQ)", "Numerical", "Match the Column", "Paragraph / Stem"]
            selected_type = st.selectbox("Question Pattern", q_types)
        with col3:
            all_books = sorted(list({q.get("source_book", "Unknown") for q in questions}))
            book_filter = st.selectbox("Filter by Source Book", ["All Books"] + all_books)

        # Filtering
        filtered_questions = questions
        if selected_topic != "All Topics":
            filtered_questions = [q for q in filtered_questions if q.get("topic") == selected_topic]
        if selected_type != "All Types":
            filtered_questions = [q for q in filtered_questions if q.get("pattern_type") == selected_type]
        if book_filter != "All Books":
            filtered_questions = [q for q in filtered_questions if q.get("source_book") == book_filter]

        st.info(f"Available Questions: **{len(filtered_questions)}**")

        if "selected_test_q_ids" not in st.session_state:
            st.session_state.selected_test_q_ids = set()

        # Paper Configuration Headers
        c1, c2, c3 = st.columns(3)
        with c1:
            paper_title = st.text_input("Test Paper Title", value="JEE Advanced Physics Test")
        with c2:
            time_limit = st.number_input("Time Allowed (Minutes)", min_value=15, value=60, step=15)
        with c3:
            total_marks = st.number_input("Total Marks", min_value=10, value=60, step=5)

        st.divider()
        st.subheader("Select Questions for Paper")

        for i, q in enumerate(filtered_questions):
            q_id = f"{q.get('source_book', 'book')}_{q.get('problem_number', i)}_{i}"
            with st.container(border=True):
                col_check, col_details = st.columns([0.08, 0.92])
                with col_check:
                    checked = st.checkbox("Pick", key=f"select_{q_id}", value=(q_id in st.session_state.selected_test_q_ids))
                    if checked:
                        st.session_state.selected_test_q_ids.add(q_id)
                    else:
                        st.session_state.selected_test_q_ids.discard(q_id)

                with col_details:
                    p_type = q.get("pattern_type", "Standard Problem")
                    st.markdown(f"**Problem {q.get('problem_number', 'N/A')}** `[{p_type}]` | **Topic:** {q.get('topic', 'N/A')} | *Source: {q.get('source_book', 'N/A')}*")
                    st.markdown(q.get("question_text", ""))

                    # Diagrams
                    if q.get("diagram_path") and os.path.exists(q["diagram_path"]):
                        st.image(q["diagram_path"], caption=f"Figure for Problem {q.get('problem_number', 'N/A')}", width=340)

                    # Options for SCQ / MCQ
                    if p_type in ["Single Correct (SCQ)", "Multiple Correct (MCQ)"] and q.get("options"):
                        opts = q.get("options", {})
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"**(A)** {opts.get('A', '')}")
                            st.write(f"**(C)** {opts.get('C', '')}")
                        with col_b:
                            st.write(f"**(B)** {opts.get('B', '')}")
                            st.write(f"**(D)** {opts.get('D', '')}")

                    # Match the Column Grid
                    elif p_type == "Match the Column":
                        mc1, mc2 = st.columns(2)
                        with mc1:
                            st.markdown("**Column I**")
                            for item in q.get("column_1", []):
                                st.write(item)
                        with mc2:
                            st.markdown("**Column II**")
                            for item in q.get("column_2", []):
                                st.write(item)

                    with st.expander("View Solution & Key"):
                        st.markdown(f"**Answer:** {q.get('correct_answer', 'N/A')}")
                        st.markdown(f"**Derivation:**\n{q.get('solution_steps', 'N/A')}")

        st.divider()
        st.write(f"Total Questions Chosen: **{len(st.session_state.selected_test_q_ids)}**")
        if st.button("Assemble and Finalize Test Paper", type="primary"):
            st.success(f"Paper '{paper_title}' finalized with {len(st.session_state.selected_test_q_ids)} questions!")

# ==========================================
# TAB 3: QUESTION BANK MANAGEMENT
# ==========================================
with tabs[2]:
    st.header("Question Bank Management")
    
    with st.expander("➕ Design / Add Question to Bank", expanded=True):
        pattern_mode = st.selectbox(
            "Select Question Pattern",
            ["Single Correct (SCQ)", "Multiple Correct (MCQ)", "Numerical", "Match the Column", "Paragraph / Stem"]
        )

        with st.form("custom_jee_builder_form", clear_on_submit=True):
            r1, r2 = st.columns(2)
            with r1:
                f_top = st.text_input("Topic", value="Mechanics")
            with r2:
                f_label = st.text_input("Problem Label / Number", value="Q-Design-01")

            f_text = st.text_area("Question Stem (LaTeX equations enclosed in $...$)", height=120)

            c1_data, c2_data, opts_dict = [], [], {}
            if pattern_mode in ["Single Correct (SCQ)", "Multiple Correct (MCQ)"]:
                st.markdown("##### Choices")
                oc1, oc2 = st.columns(2)
                with oc1:
                    opt_a = st.text_input("Option (A)")
                    opt_c = st.text_input("Option (C)")
                with oc2:
                    opt_b = st.text_input("Option (B)")
                    opt_d = st.text_input("Option (D)")
                opts_dict = {"A": opt_a, "B": opt_b, "C": opt_c, "D": opt_d}

            elif pattern_mode == "Match the Column":
                st.markdown("##### Columns Configuration")
                mc1, mc2 = st.columns(2)
                with mc1:
                    c1_raw = st.text_area("Column I (one per line)", value="(A) Uniform Disc\n(B) Ring\n(C) Solid Sphere\n(D) Hollow Sphere")
                    c1_data = [x.strip() for x in c1_raw.split("\n") if x.strip()]
                with mc2:
                    c2_raw = st.text_area("Column II (one per line)", value="(P) $MR^2$\n(Q) $\\frac{1}{2}MR^2$\n(R) $\\frac{2}{5}MR^2$\n(S) $\\frac{2}{3}MR^2$")
                    c2_data = [x.strip() for x in c2_raw.split("\n") if x.strip()]

            r_ans, r_src = st.columns(2)
            with r_ans:
                f_ans = st.text_input("Correct Answer / Key", value="A")
            with r_src:
                f_src = st.text_input("Source Identifier", value="Custom Design")

            f_sol = st.text_area("Analytical Derivation / Solution", height=100)

            if st.form_submit_button("Save Question to Bank"):
                current_data = load_db()
                entry = {
                    "problem_number": f_label.strip(),
                    "topic": f_top.strip(),
                    "pattern_type": pattern_mode,
                    "question_text": f_text,
                    "options": opts_dict,
                    "column_1": c1_data,
                    "column_2": c2_data,
                    "correct_answer": f_ans.strip(),
                    "solution_steps": f_sol,
                    "has_diagram": False,
                    "diagram_path": None,
                    "source_book": f_src.strip()
                }
                current_data.append(entry)
                save_db(current_data)
                st.success(f"Problem '{f_label}' added successfully!")
                st.rerun()

    st.divider()
    all_data = load_db()
    st.write(f"Total Stored Questions: **{len(all_data)}**")
    if all_data:
        st.dataframe([
            {
                "Problem #": d.get("problem_number"),
                "Type": d.get("pattern_type", "Standard"),
                "Topic": d.get("topic"),
                "Source": d.get("source_book")
            }
            for d in all_data
        ])