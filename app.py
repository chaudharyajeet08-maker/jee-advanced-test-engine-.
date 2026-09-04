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
    "📚 3. Question Bank & Designer"
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
        st.warning("Database empty. Run Ingest in Tab 1 or Design a question in Tab 3 first.")
    else:
        # Extract unique Topics
        all_topics = sorted(list({q.get("topic", "General") for q in questions if q.get("topic")}))
        
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            selected_topic = st.selectbox("Select Topic", ["All Topics"] + all_topics)

        # Filter Subtopics dynamically based on Selected Topic
        if selected_topic == "All Topics":
            available_subtopics = sorted(list({q.get("subtopic", "General") for q in questions if q.get("subtopic")}))
        else:
            available_subtopics = sorted(list({
                q.get("subtopic", "General") 
                for q in questions 
                if q.get("topic") == selected_topic and q.get("subtopic")
            }))

        with f_col2:
            selected_subtopic = st.selectbox("Select Subtopic", ["All Subtopics"] + available_subtopics)

        with f_col3:
            book_filter = st.selectbox("Book Source", ["All Books"] + sorted(list({q.get("source_book", "Unknown") for q in questions})))

        # Apply Filters
        filtered_questions = questions
        if selected_topic != "All Topics":
            filtered_questions = [q for q in filtered_questions if q.get("topic") == selected_topic]
        if selected_subtopic != "All Subtopics":
            filtered_questions = [q for q in filtered_questions if q.get("subtopic") == selected_subtopic]
        if book_filter != "All Books":
            filtered_questions = [q for q in filtered_questions if q.get("source_book") == book_filter]

        st.write(f"**Found {len(filtered_questions)} question(s) matching current criteria.**")

        if "selected_test_q_ids" not in st.session_state:
            st.session_state.selected_test_q_ids = set()

        st.subheader("Select Questions for Test Paper")
        for i, q in enumerate(filtered_questions):
            q_id = f"{q.get('source_book', 'book')}_{q.get('problem_number', i)}_{i}"
            with st.container(border=True):
                col_check, col_details = st.columns([0.1, 0.9])
                with col_check:
                    checked = st.checkbox("Include", key=f"select_{q_id}", value=(q_id in st.session_state.selected_test_q_ids))
                    if checked:
                        st.session_state.selected_test_q_ids.add(q_id)
                    else:
                        st.session_state.selected_test_q_ids.discard(q_id)

                with col_details:
                    st.markdown(f"**Problem {q.get('problem_number', 'N/A')}** | `{q.get('topic', 'N/A')}` $\\rightarrow$ `{q.get('subtopic', 'N/A')}` | *Source: {q.get('source_book', 'N/A')}*")
                    st.markdown(q.get("question_text", ""))

                    if q.get("diagram_path") and os.path.exists(q["diagram_path"]):
                        st.image(q["diagram_path"], caption="Extracted Diagram", width=320)

                    with st.expander("Show Derivation / Answer"):
                        st.markdown(f"**Answer:** {q.get('correct_answer', 'N/A')}")
                        st.markdown(q.get("solution_steps", "N/A"))

# ==========================================
# TAB 3: QUESTION BANK & DESIGNER
# ==========================================
with tabs[2]:
    st.header("Design & Manage Physics Questions")
    
    st.subheader("Design a New Question for a Specific Topic / Subtopic")
    with st.expander("➕ Open Question Designer", expanded=True):
        with st.form("add_custom_question_form", clear_on_submit=True):
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                new_topic = st.text_input("Topic (e.g. Mechanics, Electromagnetism)", value="Mechanics")
                new_subtopic = st.text_input("Subtopic (e.g. Rotational Dynamics, Coriolis Force)", value="Rotational Dynamics")
            with d_col2:
                new_book = st.text_input("Source / Reference Tag", value="Custom Design")
                new_prob_num = st.text_input("Question / Problem Label", value="Q-Design-01")

            new_q_text = st.text_area(
                "Question Text (Use LaTeX $...$ for equations)",
                value="A uniform solid cylinder of mass $m$ and radius $R$ is placed on a rough horizontal surface...",
                height=120
            )
            new_ans = st.text_input("Correct Answer (or LaTeX expression)", value="$a = \\frac{2}{3} g \\sin\\theta$")
            new_sol = st.text_area("Step-by-step Derivation", value="Using torque equation about contact point: $\\tau = I\\alpha$...", height=100)

            submitted = st.form_submit_button("Save Question to Database")
            if submitted:
                current_data = load_db()
                new_entry = {
                    "problem_number": new_prob_num,
                    "topic": new_topic.strip(),
                    "subtopic": new_subtopic.strip(),
                    "question_text": new_q_text,
                    "correct_answer": new_ans,
                    "solution_steps": new_sol,
                    "has_diagram": False,
                    "diagram_path": None,
                    "source_book": new_book.strip()
                }
                current_data.append(new_entry)
                save_db(current_data)
                st.success(f"Custom problem '{new_prob_num}' successfully added to {new_topic} -> {new_subtopic}!")
                st.rerun()

    st.divider()
    st.subheader("Current Question Database")
    all_db_questions = load_db()
    st.write(f"Total Questions Stored: **{len(all_db_questions)}**")
    if all_db_questions:
        st.json(all_db_questions[:5])