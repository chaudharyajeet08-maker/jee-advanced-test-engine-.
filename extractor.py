import os
import json
import fitz  # PyMuPDF
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Multi-environment API Key Resolution
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try:
        import streamlit as st
        api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        api_key = None

if not api_key:
    raise ValueError("GEMINI_API_KEY not found. Please set it in .env locally or in Streamlit Secrets.")

client = genai.Client(api_key=api_key)
PRIMARY_MODEL = "gemini-3.5-flash-lite"

class ExtractedProblem(BaseModel):
    problem_number: str = Field(description="Book question number e.g. 1.25")
    topic: str = Field(description="Broad chapter e.g. Mechanics, Chemical Bonding, Calculus")
    subtopic: str = Field(description="Specific sub-concept e.g. Work-Energy, Hybridisation, Definite Integrals")
    question_text: str = Field(description="Complete text of question with formulas formatted in inline LaTeX ($...$).")
    has_diagram: bool = Field(description="True if the problem references or requires a diagram, reaction, or figure.")
    diagram_bounding_box: Optional[List[int]] = Field(default=None, description="[ymin, xmin, ymax, xmax] mapped 0-1000.")
    correct_answer: str = Field(default="N/A", description="Given answer in LaTeX ($...$).")
    solution_steps: str = Field(default="Standard derivation steps.", description="Step-by-step mathematical or conceptual derivation.")

class BookPageExtraction(BaseModel):
    problems: List[ExtractedProblem]

def extract_problems_from_page(page_image_bytes: bytes, page_num: int, subject: str = "Physics") -> List[dict]:
    prompt = f"""
    You are an expert JEE Advanced {subject} professor and exam document parser.
    Examine this {subject} textbook page carefully:
    1. Identify all distinct problems/questions on this page.
    2. Extract the exact text of each problem cleanly into question_text. Use standard LaTeX syntax enclosed in single dollar signs ($...$) for all math, Greek symbols, reactions, and chemical structures.
    3. Ensure no English prose words are accidentally lumped inside LaTeX delimiters.
    4. If the page contains a diagram, geometry figure, circuit, or chemical structure:
       - Set has_diagram = true.
       - Provide diagram_bounding_box as [ymin, xmin, ymax, xmax] mapped on a scale of 0 to 1000.
    5. Extract the answer or provide the step-by-step derivation/mechanism in solution_steps.
    """

    try:
        response = client.models.generate_content(
            model=PRIMARY_MODEL,
            contents=[
                types.Part.from_bytes(data=page_image_bytes, mime_type="image/png"),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BookPageExtraction
            ),
        )
        data = json.loads(response.text)
        problems = data.get("problems", [])
        for p in problems:
            p["page_number"] = page_num
            p["subject"] = subject
        return problems
    except Exception as e:
        print(f"Error processing page {page_num}: {e}")
        return []

def process_book_pdf(*args, **kwargs):
    pdf_path = kwargs.get("pdf_path", args[0] if len(args) > 0 else "")
    book_title = kwargs.get("book_title", args[1] if len(args) > 1 else "Book")
    subject = kwargs.get("subject", "Physics")
    
    if len(args) >= 4 and isinstance(args[2], (int, float)):
        start_page = int(args[2])
        end_page = int(args[3])
    else:
        start_page = int(kwargs.get("start_page", 1))
        end_page = int(kwargs.get("end_page", 3))

    db_path = kwargs.get("db_path", "database/questions_db.json")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    os.makedirs("static/diagrams", exist_ok=True)

    existing_data = []
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = []

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    extracted_total = 0

    start_idx = max(start_page - 1, 0)
    end_idx = min(end_page, total_pages)

    for p_idx in range(start_idx, end_idx):
        page_no = p_idx + 1
        page = doc.load_page(p_idx)
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")

        problems = extract_problems_from_page(img_bytes, page_no, subject)

        for prob in problems:
            prob["source_book"] = book_title
            prob["subject"] = subject
            
            if prob.get("has_diagram") and prob.get("diagram_bounding_box"):
                bbox = prob["diagram_bounding_box"]
                if len(bbox) == 4:
                    ymin, xmin, ymax, xmax = bbox
                    w, h = pix.width, pix.height
                    rect = fitz.Rect(
                        (xmin / 1000) * w,
                        (ymin / 1000) * h,
                        (xmax / 1000) * w,
                        (ymax / 1000) * h
                    )
                    diag_filename = f"diag_{subject}_{book_title}_p{page_no}_{prob.get('problem_number', 'q')}.png"
                    diag_path = os.path.join("static/diagrams", diag_filename)
                    try:
                        crop_pix = page.get_pixmap(clip=rect, dpi=200)
                        crop_pix.save(diag_path)
                        prob["diagram_path"] = diag_path
                    except Exception:
                        prob["diagram_path"] = None

            existing_data.append(prob)
            extracted_total += 1

    doc.close()

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)

    return extracted_total
