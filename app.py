import os
import json
import streamlit as st
from dotenv import load_dotenv
from google import genai
from extractor import process_book_pdf

load_dotenv()

# API Key fallback
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
    "📚 3. Question Bank & Types"
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
        # Dynamic Topic & Subtopic Filters
        all_topics = sorted(list({q.get("topic", "General") for q in questions if q.get("topic")}))
        
        col_t, col_st, col_type, col_bk = st.columns(4)
        with col_t:
            selected_topic = st.selectbox("Filter Topic", ["All Topics"] + all_topics)

        # Filter Subtopic options dynamically according to chosen Topic
        if selected_topic == "All Topics":
            available_subtopics = sorted(list({q.get("subtopic", "General") for q in questions if q.get("subtopic")}))
        else:
            available_subtopics = sorted(list({
                q.get("subtopic", "General") 
                for q in questions 
                if q.get("topic") == selected_topic and q.get("subtopic")
            }))

        with col_st:
            selected_subtopic = st.selectbox("Filter Subtopic", ["All Subtopics"] + available_subtopics)

        with col_type:
            question_types = ["All Types", "Single Correct (SCQ)", "Multiple Correct (MCQ)", "Numerical", "Match the Column", "Paragraph / Stem"]
            selected_q_type = st.selectbox("Question Pattern", question_types)

        with col_bk:
            book_filter = st.selectbox("Book Source", ["All Books"] + sorted(list({q.get("source_book", "Unknown") for q in questions})))

        # Apply Filters
        filtered_questions = questions
        if selected_topic != "All Topics":
            filtered_questions = [q for q in filtered_questions if q.get("topic") == selected_topic]
        if selected_subtopic != "All Subtopics":
            filtered_questions = [q for q in filtered_questions if q.get("subtopic") == selected_subtopic]
        if selected_q_type != "All Types":
            filtered_questions = [q for q in filtered_questions if q.get("pattern_type") == selected_q_type]
        if book_filter != "All Books":
            filtered_questions = [q for q in filtered_questions if q.get("source_book") == book_filter]

        st.info(f"Available Questions: **{len(filtered_questions)}**")

        if "selected_test_q_ids" not in st.session_state:
            st.session_state.selected_test_q_ids = set()

        # Test Assembly Controls
        st.subheader("Selected Paper Configuration")
        c1, c2, c3 = st.columns(3)
        with c1:
            paper_title = st.text_input("Test Name", value="JEE Advanced Physics Full Test - 01")
        with c2:
            time_limit = st.number_input("Time Limit (Minutes)", min_value=15, value=60, step=15)
        with c3:
            total_marks = st.number_input("Total Marks", min_value=10, value=60, step=5)

        st.divider()
        st.subheader("Question Selection")
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
                    pat = q.get("pattern_type", "Standard Problem")
                    st.markdown(f"**Problem {q.get('problem_number', 'N/A')}** `[{pat}]` | **Topic:** {q.get('topic', 'N/A')} $\\rightarrow$ **Subtopic:** {q.get('subtopic', 'N/A')} | *Source: {q.get('source_book', 'N/A')}*")
                    st.markdown(q.get("question_text", ""))

                    if q.get("diagram_path") and os.path.exists(q["diagram_path"]):
                        st.image(q["diagram_path"], caption="Figure Reference", width=340)

                    # Display Specific Pattern Elements
                    if q.get("pattern_type") == "Match the Column":
                        m_col1, m_col2 = st.columns(2)
                        with m_col1:
                            st.markdown("**Column I**")
                            for item in q.get("column_1", []):
                                st.write(item)
                        with m_col2:
                            st.markdown("**Column II**")
                            for item in q.get("column_2", []):
                                st.write(item)

                    elif q.get("pattern_type") in ["Single Correct (SCQ)", "Multiple Correct (MCQ)"] and q.get("options"):
                        for opt_key, opt_val in q.get("options", {}).items():
                            st.markdown(f"**({opt_key})** {opt_val}")

                    with st.expander("Solution & Marking Scheme"):
                        st.markdown(f"**Correct Answer / Match:** {q.get('correct_answer', 'N/A')}")
                        st.markdown(f"**Step-by-Step Derivation:**\n{q.get('solution_steps', 'N/A')}")

        st.divider()
        st.write(f"Total Questions Chosen: **{len(st.session_state.selected_test_q_ids)}**")
        if st.button("Generate Final Printable / Export Paper"):
            st.success(f"Paper '{paper_title}' successfully compiled with {len(st.session_state.selected_test_q_ids)} items!")

# ==========================================
# TAB 3: QUESTION BANK & PATTERN BUILDER
# ==========================================
with tabs[2]:
    st.header("Question Bank & JEE Advanced Pattern Builder")
    
    with st.expander("➕ Add / Construct a JEE Advanced Problem", expanded=True):
        pattern_mode = st.selectbox(
            "Select Question Structure",
            ["Single Correct (SCQ)", "Multiple Correct (MCQ)", "Numerical", "Match the Column", "Paragraph / Stem"]
        )

        with st.form("jee_question_form", clear_on_submit=True):
            r1_c1, r1_c2, r1_c3 = st.columns(3)
            with r1_c1:
                f_topic = st.text_input("Topic", value="Mechanics")
            with r1_c2:
                f_subtopic = st.text_input("Subtopic", value="Rotational Dynamics")
            with r1_c3:
                f_label = st.text_input("Problem Identifier", value="P-2026-01")

            f_text = st.text_area("Question Stem / Statement (Supports LaTeX $...$)", height=120)

            # Match the Column specific fields
            c1_data, c2_data, opts_dict = [], [], {}
            if pattern_mode == "Match the Column":
                st.markdown("##### Column Matching Setup")
                mc1, mc2 = st.columns(2)
                with mc1:
                    c1_text = st.text_area("Column I Items (one per line)", value="(A) Uniform Disk\n(B) Hollow Cylinder\n(C) Solid Sphere\n(D) Spherical Shell")
                    c1_data = [x.strip() for x in c1_text.split("\n") if x.strip()]
                with mc2:
                    c2_text = st.text_area("Column II Items (one per line)", value="(P) $I = \\frac{1}{2}MR^2$\n(Q) $I = MR^2$\n(R) $I = \\frac{2}{5}MR^2$\n(S) $I = \\frac{2}{3}MR^2$")
                    c2_data = [x.strip() for x in c2_text.split("\n") if x.strip()]

            # Multiple Choice specific fields
            elif pattern_mode in ["Single Correct (SCQ)", "Multiple Correct (MCQ)"]:
                st.markdown("##### Answer Choices")
                oc1, oc2 = st.columns(2)
                with oc1:
                    opt_a = st.text_input("Option (A)")
                    opt_b = st.text_input("Option (B)")
                with oc2:
                    opt_c = st.text_input("Option (C)")
                    opt_d = st.text_input("Option (D)")
                opts_dict = {"A": opt_a, "B": opt_b, "C": opt_c, "D": opt_d}

            r2_c1, r2_c2 = st.columns(2)
            with r2_c1:
                f_ans = st.text_input("Correct Answer / Key", value="A->P, B->Q, C->R, D->S" if pattern_mode == "Match the Column" else "A")
            with r2_c2:
                f_source = st.text_input("Source Tag", value="Self Designed")

            f_sol = st.text_area("Analytical Solution / Derivation", height=100)

            if st.form_submit_button("Save Question to Bank"):
                current_data = load_db()
                entry = {
                    "problem_number": f_label.strip(),
                    "topic": f_topic.strip(),
                    "subtopic": f_subtopic.strip(),
                    "pattern_type": pattern_mode,
                    "question_text": f_text,
                    "options": opts_dict,
                    "column_1": c1_data,
                    "column_2": c2_data,
                    "correct_answer": f_ans.strip(),
                    "solution_steps": f_sol,
                    "has_diagram": False,
                    "diagram_path": None,
                    "source_book": f_source.strip()
                }
                current_data.append(entry)
                save_db(current_data)
                st.success(f"Problem '{f_label}' added under {f_topic} -> {f_subtopic}!")
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
                "Subtopic": d.get("subtopic"),
                "Source": d.get("source_book")
            }
            for d in all_data
        ])