import os
import json
import fitz  # PyMuPDF
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Multi-environment API Key Resolution (Local .env vs Streamlit Cloud Secrets)
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
    topic: str = Field(description="Broad physics chapter e.g. Mechanics, Thermodynamics, Optics")
    subtopic: str = Field(description="Specific sub-concept e.g. Coriolis Force, Work-Energy Theorem")
    question_text: str = Field(description="Complete text of the question with mathematical symbols formatted in standard inline LaTeX ($...$).")
    has_diagram: bool = Field(description="True if the problem references or requires a diagram from the page.")
    diagram_bounding_box: Optional[List[int]] = Field(default=None, description="[ymin, xmin, ymax, xmax] normalized on a 0-1000 scale if diagram is present.")
    correct_answer: str = Field(default="N/A", description="Given numerical answer or analytical expression in standard LaTeX ($...$).")
    solution_steps: str = Field(default="Standard derivation steps.", description="Step-by-step mathematical derivation.")

class BookPageExtraction(BaseModel):
    problems: List[ExtractedProblem]

def extract_problems_from_page(page_image_bytes: bytes, page_num: int) -> List[dict]:
    prompt = """
    You are an expert physics document parser and competitive exam analyst.
    Examine this physics textbook page carefully:
    1. Identify all distinct physics problems on this page.
    2. Extract the exact text of each problem cleanly into question_text. Use standard LaTeX syntax enclosed in single dollar signs ($...$) for all algebraic symbols, Greek letters, and formulas.
    3. Ensure no English prose words are accidentally lumped inside LaTeX delimiters.
    4. If the page contains a diagram or figure belonging to a problem:
       - Set has_diagram = true.
       - Provide diagram_bounding_box as [ymin, xmin, ymax, xmax] mapped on a scale of 0 to 1000.
    5. Extract the given answer (if present on the page) or provide the analytical step-by-step solution derivation in solution_steps.
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
        return problems
    except Exception as e:
        print(f"Error processing page {page_num}: {e}")
        return []

def process_book_pdf(pdf_path: str, book_title: str, start_page: int, end_page: int, db_path: str = "database/questions_db.json"):
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

        problems = extract_problems_from_page(img_bytes, page_no)

        for prob in problems:
            prob["source_book"] = book_title
            
            # Crop and save diagrams if coordinates are available
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
                    diag_filename = f"diag_{book_title}_p{page_no}_{prob.get('problem_number', 'q')}.png"
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