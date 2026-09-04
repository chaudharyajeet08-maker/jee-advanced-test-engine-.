import os
import json
import random
import re
import tempfile
import base64
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from dotenv import load_dotenv
from extractor import process_book_pdf

load_dotenv()

# Multi-environment API Key Resolution (Local .env vs Streamlit Cloud Secrets)
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        api_key = None

client = genai.Client(api_key=api_key) if api_key else None

st.set_page_config(page_title="JEE Advanced Test Engine", layout="wide", page_icon="⚛️")

DB_PATH = "database/questions_db.json"
PRIMARY_MODEL = "gemini-3.5-flash-lite"

os.makedirs("database", exist_ok=True)
os.makedirs("books", exist_ok=True)
os.makedirs("static/diagrams", exist_ok=True)

class FramedQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question_text: str
    options: Optional[List[str]] = Field(default_factory=list, description="4 options for MCQs or 4 combination strings for Matrix Match.")
    column_1_items: Optional[List[str]] = Field(default=None, description="Exactly 4 entries for Column I (A, B, C, D).")
    column_2_items: Optional[List[str]] = Field(default=None, description="Exactly 4 entries for Column II (P, Q, R, S).")
    correct_answer: str = "N/A"
    solution_steps: str = "Comprehensive step-by-step derivation."

@st.cache_data(ttl=5)
def load_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def ensure_math_delimiters(text: str) -> str:
    """Ensures answers and isolated formulas have proper $...$ delimiters for MathJax."""
    if not text:
        return ""
    trimmed = text.strip()
    # Strip accidental prefixes
    trimmed = re.sub(r"^(Option\s*)?(\([A-Da-d0-9]\)|[A-Da-d0-9][\.\:\-])\s*", "", trimmed)
    # If it contains LaTeX backslashes or sub/superscripts without $, wrap in $...$
    if ("\\" in trimmed or "_" in trimmed or "^" in trimmed or "=" in trimmed) and "$" not in trimmed:
        return f"${trimmed}$"
    return trimmed

def clean_question_body(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"Constraints?:.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Wait, prompt says.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Remove standard markdown.*", "", text, flags=re.IGNORECASE)
    
    stripped = text.strip()
    if stripped.startswith("$") and stripped.endswith("$") and stripped.count("$") == 2:
        inner = stripped[1:-1].strip()
        if len(inner.split()) > 4:
            text = inner
    return text.strip()

def clean_option_item(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"^(Option\s*)?(\([A-Da-d0-9]\)|[A-Da-d0-9][\.\:\-])\s*", "", text.strip())
    text = text.replace("$$", "$").strip()

    replacements = {
        r"towardsEast": " towards East",
        r"towardsWest": " towards West",
        r"towardsNorth": " towards North",
        r"towardsSouth": " towards South",
        r"clockwise": " clockwise",
        r"anticlockwise": " anticlockwise"
    }
    for pat, repl in replacements.items():
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)

    match = re.match(r"^\$([^$]+?)\s+(towards\s+[A-Za-z]+|clockwise|anticlockwise|upwards|downwards)\$$", text, re.I)
    if match:
        math_part = match.group(1).strip()
        eng_part = match.group(2).strip()
        text = f"${math_part}$, {eng_part}"

    trimmed = text.strip()
    if ("\\" in trimmed or "=" in trimmed or "^" in trimmed or "_" in trimmed) and "$" not in trimmed:
        if len(trimmed.split()) <= 4:
            text = f"${trimmed}$"

    return text.strip()

def format_solution_to_html(raw_sol: str) -> str:
    if not raw_sol:
        return "<p>Solution not available.</p>"
    
    # Standardize headers even if model outputs continuous text
    text = raw_sol
    keywords = [
        "Key Physical Concepts", "Key Concepts", "Physical Concepts",
        "Coordinate System & Setup", "Physical Setup", "Setup",
        "Rigorous Derivation", "Step-by-Step Derivation", "Step-by-Step Solution", "Derivation",
        "Option Verification", "Analysis of Statements", "Conclusion & Verification", "Conclusion"
    ]
    for kw in keywords:
        pattern = re.compile(rf"(\b{kw}:|\b\*\*{kw}\*\*|\b###\s*{kw})", re.IGNORECASE)
        text = pattern.sub(f"\n\n### {kw}\n", text)

    blocks = text.split("\n")
    html_out = []
    
    for b in blocks:
        item = b.strip()
        if not item:
            continue
        if item.startswith("###"):
            heading = item.lstrip("#").strip()
            html_out.append(f'<div class="sol-section-heading">{heading}</div>')
        elif item.startswith("$$") and item.endswith("$$"):
            html_out.append(f'<div class="sol-display-math">{item}</div>')
        elif item.startswith("* ") or item.startswith("- "):
            html_out.append(f'<div class="sol-bullet">• {item[2:]}</div>')
        else:
            html_out.append(f'<p class="sol-paragraph">{item}</p>')

    return "".join(html_out)

def frame_question_dynamically(raw_q: dict, target_type: str) -> dict:
    if not client:
        fallback = raw_q.copy()
        fallback["question_type"] = target_type
        return fallback

    if target_type == "numerical":
        base_prompt = f"""
        You are an expert JEE Advanced Physics professor.
        Provide a textbook-grade, rigorous, and beautifully formatted solution for this numerical problem.

        PROBLEM:
        {raw_q.get('question_text')}
        ANSWER:
        {raw_q.get('correct_answer')}
        DERIVATION:
        {raw_q.get('solution_steps')}

        STRICT STYLING AND PEDAGOGY RULES:
        1. Write in natural sentence case (NEVER WRITE IN ALL CAPS).
        2. In 'correct_answer': Enclose all formulas and numbers with units in standard LaTeX math delimiters (e.g. "$p_0 V_0 \\left[ \\eta \\ln \\eta - (1+\\eta)\\ln \\left(\\frac{{1+\\eta}}{{2}}\\right) \\right]$").
        3. In 'solution_steps': Structure with clear Markdown headers:
           ### Key Concepts
           Explain the underlying physics laws (isothermal expansion, first law of thermodynamics, etc.).
           ### Physical Setup
           State the coordinates, parameters, and thermodynamic variables.
           ### Step-by-Step Derivation
           Derive the result step-by-step. Put key integration and work equations on their own lines using display math ($$...$$).
           ### Final Evaluation
           State the calculated numerical/algebraic result clearly with proper SI units.
        """
        try:
            response = client.models.generate_content(
                model=PRIMARY_MODEL,
                contents=[base_prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FramedQuestion
                ),
            )
            data = json.loads(response.text)
            framed = raw_q.copy()
            framed["question_type"] = "numerical"
            framed["solution_steps"] = data.get("solution_steps", raw_q.get("solution_steps"))
            framed["correct_answer"] = data.get("correct_answer", raw_q.get("correct_answer"))
            return framed
        except Exception:
            res = raw_q.copy()
            res["question_type"] = "numerical"
            return res

    if target_type == "matrix_match":
        prompt = f"""
        You are an expert JEE Advanced Physics professor.
        Convert this physics problem into a rigorous JEE Advanced MATCH THE COLUMN (Matrix Match) question.

        PROBLEM:
        {raw_q.get('question_text')}
        SOLUTION & ANSWER:
        {raw_q.get('correct_answer')} | {raw_q.get('solution_steps')}

        INSTRUCTIONS:
        1. Natural sentence case (NEVER USE ALL CAPS).
        2. Set column_1_items as 4 physical parameters/scenarios (A, B, C, D).
        3. Set column_2_items as 4 values/expressions (P, Q, R, S) in LaTeX $...$.
        4. options: 4 combinations (e.g. ["A->P, R; B->Q; C->S; D->P", ...]).
        5. In correct_answer: Write the single correct option letter ("A", "B", "C", or "D").
        6. In solution_steps: Structure into:
           ### Key Concepts
           ### Step-by-Step Derivation
           Provide clear individual derivations proving each match (A), (B), (C), and (D).
           ### Conclusion
        """
    else:
        prompt = f"""
        You are an expert JEE Advanced Physics professor.
        Convert this numerical problem into a standard JEE Advanced {target_type.replace('_', ' ').title()} question.

        PROBLEM:
        {raw_q.get('question_text')}
        SOLUTION & ANSWER:
        {raw_q.get('correct_answer')} | {raw_q.get('solution_steps')}

        INSTRUCTIONS:
        1. Natural sentence case (NEVER USE ALL CAPS).
        2. In 'options': Provide 4 distinct options. Keep text outside math and formulas in $...$ (e.g., "$7.5\\text{{ cm}}$, towards East").
        3. In 'correct_answer': Specify the correct option ("A", "B", "C", "D", or combination like "A, C").
        4. In 'solution_steps':
           ### Key Concepts
           ### Mathematical Formulation
           ### Step-by-Step Derivation
           Put derivations on separate lines using display math ($$...$$).
           ### Option Verification
           Thoroughly verify why the correct choice matches and analyze any incorrect choices.
        """

    for attempt in range(1, 3):
        try:
            response = client.models.generate_content(
                model=PRIMARY_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FramedQuestion
                ),
            )
            data = json.loads(response.text)
            framed = raw_q.copy()
            framed["question_type"] = target_type
            framed["question_text"] = data.get("question_text", raw_q.get("question_text"))
            framed["options"] = data.get("options") or []
            framed["column_1_items"] = data.get("column_1_items")
            framed["column_2_items"] = data.get("column_2_items")
            framed["correct_answer"] = data.get("correct_answer", raw_q.get("correct_answer"))
            framed["solution_steps"] = data.get("solution_steps", raw_q.get("solution_steps"))
            return framed
        except Exception:
            if attempt == 2:
                fallback = raw_q.copy()
                fallback["question_type"] = "numerical"
                return fallback

def build_html_paper(selected, topic_name):
    q_html_parts = []
    sol_html_parts = []

    for idx, q in enumerate(selected, 1):
        q_type_raw = q.get("question_type", "numerical")
        type_labels = {
            "single_choice": "One Option Correct",
            "multi_choice": "One or More Than One Option Correct",
            "numerical": "Numerical Value Answer",
            "matrix_match": "Match The Column (Matrix Match)"
        }
        q_type_badge = type_labels.get(q_type_raw, "Physics Problem")
        q_text = clean_question_body(q.get("question_text", ""))

        interactive_content = ""

        # Matrix Match Rendering
        if q_type_raw == "matrix_match" and q.get("column_1_items") and q.get("column_2_items"):
            c1_list = q.get("column_1_items", [])
            c2_list = q.get("column_2_items", [])
            opts = q.get("options", [])

            c1_labels = ["A", "B", "C", "D"]
            c2_labels = ["P", "Q", "R", "S"]

            table_rows = ""
            for i in range(min(len(c1_list), len(c2_list), 4)):
                txt1 = clean_question_body(c1_list[i])
                txt2 = clean_question_body(c2_list[i])
                table_rows += f"""
                <tr>
                  <td style="padding:10px 14px; border:1px solid #d1d5db; width:50%;"><strong>({c1_labels[i]})</strong> {txt1}</td>
                  <td style="padding:10px 14px; border:1px solid #d1d5db; width:50%;"><strong>({c2_labels[i]})</strong> {txt2}</td>
                </tr>"""

            opts_rendered = ""
            labels = ["(A)", "(B)", "(C)", "(D)"]
            for i, opt in enumerate(opts[:4]):
                lbl = labels[i]
                c_opt = clean_option_item(str(opt))
                opts_rendered += f'''
                <div class="option-box">
                  <span class="option-label">{lbl}</span>
                  <span class="option-content">{c_opt}</span>
                </div>'''

            interactive_content = f"""
            <table style="width:100%; border-collapse:collapse; margin:14px 0; font-family:'Times New Roman',serif; font-size:15px; background:#fff;">
              <thead>
                <tr style="background:#f3f4f6;">
                  <th style="padding:10px 14px; border:1px solid #d1d5db; text-align:left;">Column I</th>
                  <th style="padding:10px 14px; border:1px solid #d1d5db; text-align:left;">Column II</th>
                </tr>
              </thead>
              <tbody>{table_rows}</tbody>
            </table>
            <div class="options-grid">{opts_rendered}</div>
            """
        # Single and Multi Correct Rendering
        elif q_type_raw in ["single_choice", "multi_choice"]:
            options = q.get("options")
            if options and isinstance(options, list) and len(options) > 0:
                labels = ["(A)", "(B)", "(C)", "(D)"]
                opts_rendered = ""
                for i, opt in enumerate(options[:4]):
                    lbl = labels[i]
                    cleaned = clean_option_item(str(opt))
                    opts_rendered += f'''
                    <div class="option-box">
                      <span class="option-label">{lbl}</span>
                      <span class="option-content">{cleaned}</span>
                    </div>'''
                interactive_content = f'<div class="options-grid">{opts_rendered}</div>'

        q_block = f"""
        <div class="question-container">
          <div class="q-header">
            <span class="q-num">Q{idx}.</span>
            <span class="q-badge">{q_type_badge}</span>
          </div>
          <div class="q-body">{q_text}</div>
          {interactive_content}
        </div>
        """
        q_html_parts.append(q_block)

        ans = ensure_math_delimiters(clean_question_body(q.get("correct_answer", "N/A")))
        formatted_sol_html = format_solution_to_html(clean_question_body(q.get("solution_steps", "")))

        sol_block = f"""
        <div class="sol-container">
          <div class="sol-header">
            <span class="sol-title">Question {idx} Detailed Solution</span>
            <span class="sol-badge">Correct Answer: {ans}</span>
          </div>
          <div class="sol-content">
            {formatted_sol_html}
          </div>
        </div>
        """
        sol_html_parts.append(sol_block)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script>
window.MathJax = {{
  tex: {{
    inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
    displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    processEscapes: true
  }},
  svg: {{ fontCache: 'global' }}
}};
</script>
<script type="text/javascript" id="MathJax-script" async
  src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js">
</script>
<style>
  body {{
    font-family: 'Times New Roman', Times, Georgia, serif;
    font-size: 15.5px;
    line-height: 1.7;
    color: #111827;
    background: #ffffff;
    max-width: 880px;
    margin: 0 auto;
    padding: 30px;
    text-transform: none !important;
  }}
  .header-box {{
    text-align: center;
    border-bottom: 2px solid #111827;
    padding-bottom: 14px;
    margin-bottom: 24px;
  }}
  .header-box h1 {{
    margin: 0;
    font-size: 21px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    font-family: Arial, Helvetica, sans-serif;
  }}
  .header-box p {{
    margin: 4px 0 0 0;
    font-weight: 600;
    font-size: 13px;
    color: #4b5563;
    font-family: Arial, Helvetica, sans-serif;
  }}
  .section-tag {{
    background: #f3f4f6;
    color: #111827;
    font-family: Arial, Helvetica, sans-serif;
    font-weight: bold;
    font-size: 12px;
    letter-spacing: 0.5px;
    padding: 7px 12px;
    border-left: 4px solid #1d4ed8;
    margin-bottom: 20px;
  }}
  .question-container {{
    margin-bottom: 26px;
    padding-bottom: 20px;
    border-bottom: 1px dotted #cbd5e1;
    page-break-inside: avoid;
  }}
  .q-header {{
    margin-bottom: 8px;
    font-family: Arial, Helvetica, sans-serif;
  }}
  .q-num {{
    font-size: 15px;
    font-weight: bold;
    color: #0f172a;
  }}
  .q-badge {{
    font-size: 11px;
    background: #eff6ff;
    color: #1e40af;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
    margin-left: 6px;
  }}
  .q-body {{
    font-size: 15.5px;
    color: #111827;
    line-height: 1.7;
    text-align: justify;
  }}
  .options-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-top: 14px;
    font-family: 'Times New Roman', Times, Georgia, serif;
  }}
  .option-box {{
    background: #ffffff;
    border: 1px solid #d1d5db;
    padding: 10px 14px;
    border-radius: 4px;
    display: flex;
    align-items: baseline;
    gap: 8px;
  }}
  .option-label {{
    font-family: Arial, Helvetica, sans-serif;
    font-weight: bold;
    color: #111827;
    min-width: 24px;
  }}
  .option-content {{
    font-size: 15px;
    color: #111827;
  }}
  .sol-container {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-left: 5px solid #16a34a;
    padding: 18px 22px;
    margin-bottom: 26px;
    border-radius: 4px;
    page-break-inside: avoid;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  .sol-header {{
    font-family: Arial, Helvetica, sans-serif;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 10px;
  }}
  .sol-title {{
    font-size: 15px;
    font-weight: bold;
    color: #0f172a;
  }}
  .sol-badge {{
    background: #dcfce7;
    color: #166534;
    font-weight: bold;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 13.5px;
  }}
  .sol-content {{
    font-size: 15px;
    color: #1e293b;
    text-transform: none !important;
  }}
  .sol-section-heading {{
    font-family: Arial, Helvetica, sans-serif;
    font-size: 13px;
    font-weight: 700;
    color: #1d4ed8;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-top: 16px;
    margin-bottom: 6px;
    border-bottom: 1px solid #eff6ff;
    padding-bottom: 3px;
  }}
  .sol-paragraph {{
    margin: 4px 0 10px 0;
    line-height: 1.75;
    text-align: justify;
    text-transform: none !important;
  }}
  .sol-display-math {{
    margin: 12px 0;
    text-align: center;
    overflow-x: auto;
  }}
  .sol-bullet {{
    margin: 4px 0 4px 16px;
    line-height: 1.7;
  }}
  @page {{ size: A4; margin: 15mm; }}
  @media print {{
    .no-print {{ display: none !important; }}
    body {{ padding: 0; max-width: 100%; }}
  }}
</style>
</head>
<body>
<div class="no-print" style="margin-bottom:20px; text-align:right;">
  <button onclick="window.print()" style="background:#1d4ed8; color:white; border:none; padding:8px 18px; border-radius:4px; font-weight:600; cursor:pointer; font-family:Arial,sans-serif; font-size:13px;">🖨️ Print / Save as PDF</button>
</div>
<div class="header-box">
  <h1>JEE (Advanced) Physics Practice Test</h1>
  <p>Topic: {topic_name} | Target: JEE Advanced</p>
</div>
<div class="section-tag">SECTION I: QUESTIONS</div>
{''.join(q_html_parts)}
<div style="page-break-before: always; margin-top:35px;"></div>
<div class="header-box" style="margin-top:25px;">
  <h1>Answer Key & Detailed Solutions</h1>
</div>
{''.join(sol_html_parts)}
</body>
</html>"""
    return full_html

st.title("⚛️ JEE Advanced Physics Question Engine")

tabs = st.tabs(["📥 1. Ingest Physics Book", "📝 2. Assemble Test Paper", "📚 3. Question Bank Management"])

# --- TAB 1: INGESTION ---
with tabs[0]:
    st.subheader("Upload Reference Book & Ingest Raw Physics Problems")
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])
        book_title = st.text_input("Book Identifier", value="Irodov")
        
    with col2:
        start_p = st.number_input("Start Page", min_value=1, value=14, step=1)
        end_p = st.number_input("End Page", min_value=1, value=16, step=1)
    
    if st.button("🚀 Start Extraction", type="primary", use_container_width=True):
        if not uploaded_file:
            st.error("Please upload a PDF file first.")
        elif end_p < start_p:
            st.error("End page cannot be smaller than start page.")
        else:
            with st.spinner(f"Ingesting pages {start_p} to {end_p}..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name
                
                try:
                    process_book_pdf(tmp_path, book_title, int(start_p), int(end_p), db_path=DB_PATH)
                    st.cache_data.clear()
                    st.success(f"Extracted pages {start_p}-{end_p} successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Extraction failed: {e}")
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

# --- TAB 2: GENERATION ---
with tabs[1]:
    st.subheader("Configure & Assemble JEE Advanced Test Paper")
    questions = load_db()
    
    if not questions:
        st.warning("Database empty. Run Ingest in Tab 1 first.")
    else:
        available_books = sorted(list(set([q.get("source_book", "General") for q in questions if q.get("source_book")])))
        raw_topics = [q.get("topic", "").strip() for q in questions if q.get("topic")]
        available_topics = sorted(list(set([t for t in raw_topics if t])))
        if not available_topics:
            available_topics = ["General Physics"]

        f1, f2, f3 = st.columns(3)
        with f1:
            selected_book = st.selectbox("Filter Book", ["All Books"] + available_books)
        with f2:
            selected_topic = st.selectbox("Filter Topic", ["All Topics"] + available_topics)
        with f3:
            custom_title = st.text_input("Header Title", value="Comprehensive Physics Test" if selected_topic == "All Topics" else selected_topic)

        filtered_pool = questions
        if selected_book != "All Books":
            filtered_pool = [q for q in filtered_pool if q.get("source_book") == selected_book]
        if selected_topic != "All Topics":
            filtered_pool = [q for q in filtered_pool if q.get("topic", "").strip().lower() == selected_topic.lower()]

        total_avail = len(filtered_pool)
        st.info(f"Available Base Problems: **{total_avail}**")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            num_single = st.number_input("Single Correct", min_value=0, max_value=max(total_avail, 1), value=min(2, total_avail))
        with c2:
            num_multi = st.number_input("One or More Correct", min_value=0, max_value=max(total_avail, 1), value=min(2, total_avail))
        with c3:
            num_matrix = st.number_input("Match The Column", min_value=0, max_value=max(total_avail, 1), value=min(1, total_avail))
        with c4:
            num_numeric = st.number_input("Numerical Value", min_value=0, max_value=max(total_avail, 1), value=min(2, total_avail))
            
        total_requested = num_single + num_multi + num_matrix + num_numeric

        if st.button("📄 Assemble Paper with Detailed Solutions", type="primary", use_container_width=True):
            if total_requested == 0:
                st.warning("Please select at least 1 question.")
            elif total_requested > total_avail:
                st.error(f"Requested {total_requested}, but only {total_avail} available.")
            else:
                seen_texts = set()
                unique_pool = []
                for q in filtered_pool:
                    clean_q = "".join(q.get("question_text", "").split()).lower()
                    if clean_q not in seen_texts and len(clean_q) > 10:
                        seen_texts.add(clean_q)
                        unique_pool.append(q)

                random.shuffle(unique_pool)

                i1 = num_single
                i2 = i1 + num_multi
                i3 = i2 + num_matrix
                
                single_raw = unique_pool[:i1]
                multi_raw = unique_pool[i1:i2]
                matrix_raw = unique_pool[i2:i3]
                numeric_raw = unique_pool[i3:total_requested]

                framed_questions = []
                progress_bar = st.progress(0, text="Framing questions and composing descriptive solutions...")
                step_total = max(total_requested, 1)
                curr_step = 0

                for item in single_raw:
                    curr_step += 1
                    progress_bar.progress(curr_step / step_total, text=f"Generating Single Correct ({curr_step}/{step_total})...")
                    framed_questions.append(frame_question_dynamically(item, "single_choice"))

                for item in multi_raw:
                    curr_step += 1
                    progress_bar.progress(curr_step / step_total, text=f"Generating Multi Correct ({curr_step}/{step_total})...")
                    framed_questions.append(frame_question_dynamically(item, "multi_choice"))

                for item in matrix_raw:
                    curr_step += 1
                    progress_bar.progress(curr_step / step_total, text=f"Generating Match The Column ({curr_step}/{step_total})...")
                    framed_questions.append(frame_question_dynamically(item, "matrix_match"))

                for item in numeric_raw:
                    curr_step += 1
                    progress_bar.progress(curr_step / step_total, text=f"Composing Numerical Derivation ({curr_step}/{step_total})...")
                    framed_questions.append(frame_question_dynamically(item, "numerical"))

                progress_bar.empty()

                html_doc = build_html_paper(framed_questions, custom_title)
                st.success(f"Generated {len(framed_questions)} questions with descriptive textbook solutions!")

                st.download_button(
                    label="⬇️ Download Paper (HTML / Printable)",
                    data=html_doc,
                    file_name=f"{custom_title.replace(' ', '_')}_Paper.html",
                    mime="text/html",
                    use_container_width=True
                )

                components.html(html_doc, height=900, scrolling=True)

# --- TAB 3: MANAGEMENT ---
with tabs[2]:
    st.subheader("Raw Problem Bank Repository")
    db_items = load_db()
    
    col_stat, col_btn = st.columns([3, 1])
    with col_stat:
        st.write(f"Total Problems in DB: **{len(db_items)}**")
    with col_btn:
        if st.button("🗑️ Clear Entire Database", type="secondary", use_container_width=True):
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            st.cache_data.clear()
            st.success("Database cleared!")
            st.rerun()

    if db_items:
        for i, item in enumerate(db_items[:15], 1):
            p_no = item.get("page_number", "N/A")
            top = item.get("topic", "General")
            with st.expander(f"Q{i} [{item.get('source_book', 'Book')} - Page {p_no}] | Topic: {top}"):
                st.markdown(f"**Question:** {item.get('question_text')}")
                st.markdown(f"**Answer:** `{item.get('correct_answer')}`")
                st.markdown(f"**Derivation:** {item.get('solution_steps')}")