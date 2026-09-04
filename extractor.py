import os
import json
import time
import pymupdf
import hashlib
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PRIMARY_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODEL = "gemini-3.5-flash"

DIAGRAMS_DIR = "static/diagrams"
os.makedirs(DIAGRAMS_DIR, exist_ok=True)

class QuestionModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_book: str = "Irodov"
    page_number: int = 0
    topic: str = "Mechanics"
    subtopic: str = "General Physics"
    question_type: str = "numerical"
    difficulty: str = "JEE_Advanced_Tough"
    question_text: str = Field(description="Exact problem statement with LaTeX math notation ($...$ inline, $$...$$ block).")
    correct_answer: str = Field(default="N/A", description="Author's exact final answer/expression.")
    solution_steps: str = Field(default="Rigorous step-by-step physical derivation.")
    has_diagram: bool = False
    diagram_path: Optional[str] = ""

class ExtractedBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: List[QuestionModel]

def get_question_hash(text: str) -> str:
    cleaned = "".join(text.split()).lower()
    return hashlib.md5(cleaned.encode("utf-8")).hexdigest()

def extract_page_diagrams(page, page_num, book_prefix):
    """Filters out scanned text strips and keeps only genuine graphical diagrams."""
    saved_images = []
    for idx, img_info in enumerate(page.get_images(full=True)):
        xref = img_info[0]
        base_image = page.parent.extract_image(xref)
        w = base_image.get("width", 0)
        h = base_image.get("height", 0)

        # Filters: Reject tiny artifacts, banner text strips, or ultra-thin scans
        aspect_ratio = w / max(h, 1)
        if w >= 120 and h >= 90 and aspect_ratio < 3.2 and (1 / aspect_ratio) < 3.2:
            filename = f"{book_prefix}_p{page_num}_fig_{idx+1}.{base_image['ext']}"
            filepath = os.path.join(DIAGRAMS_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(base_image["image"])
            saved_images.append(filepath)
    return saved_images

def process_single_page(page_num, pdf_path, book_name):
    doc = pymupdf.open(pdf_path)
    page = doc[page_num - 1]

    text_content = page.get_text().strip()
    diagram_paths = extract_page_diagrams(page, page_num, book_name.replace(" ", "_"))

    prompt = f"""
    You are an expert JEE Advanced Physics professor.
    Extract every single physics problem or exercise present on this page ({book_name}, Page {page_num}).

    Instructions:
    - Transcribe complete mathematical statements with standard LaTeX ($...$ and $$...$$).
    - Escaping rule: In JSON output, double escape all backslashes (\\\\frac, \\\\sqrt, \\\\alpha).
    - Do NOT wrap whole English sentences in $...$. Only wrap math variables and expressions.
    - Accurately classify topics (Kinematics, Dynamics, Rotational Dynamics, Electromagnetism, etc.).
    - Mark has_diagram as true ONLY if an explicit geometry or schematic figure belongs to that problem.
    """

    if len(text_content) > 60:
        contents = [f"{prompt}\n\nPAGE TEXT CONTENT:\n{text_content}"]
    else:
        pix = page.get_pixmap(dpi=110)
        img_bytes = pix.tobytes("jpeg")
        contents = [
            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
            prompt
        ]
    doc.close()

    candidate_models = [PRIMARY_MODEL, FALLBACK_MODEL]

    for model_name in candidate_models:
        for attempt in range(1, 3):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExtractedBatch
                    ),
                )
                parsed = json.loads(response.text)
                questions = parsed.get("questions", [])

                diag_idx = 0
                for q in questions:
                    q["page_number"] = page_num
                    q["source_book"] = book_name
                    q["question_type"] = "numerical"
                    if q.get("has_diagram") and diag_idx < len(diagram_paths):
                        q["diagram_path"] = diagram_paths[diag_idx]
                        diag_idx += 1
                    else:
                        q["diagram_path"] = ""
                return questions
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    time.sleep(15)
                    break
                else:
                    time.sleep(2)
    return []

def process_book_pdf(pdf_path: str, book_name: str, start_page: int, end_page: int, db_path: str = "database/questions_db.json"):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    existing_db = []
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                existing_db = json.load(f)
        except Exception:
            existing_db = []

    pages = list(range(start_page, end_page + 1))
    print(f"[*] Extracting raw problems from pages {start_page} to {end_page}...")

    new_questions = []
    for p in pages:
        try:
            res = process_single_page(p, pdf_path, book_name)
            new_questions.extend(res)
            print(f"  [+] Page {p}: Extracted {len(res)} problems.")
        except Exception as e:
            print(f"  [-] Page {p} error: {e}")
        time.sleep(1)

    seen_hashes = set()
    combined_db = []
    for q in existing_db + new_questions:
        q_hash = get_question_hash(q.get("question_text", ""))
        if q_hash not in seen_hashes and len(q.get("question_text", "").strip()) > 10:
            seen_hashes.add(q_hash)
            combined_db.append(q)

    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(combined_db, f, indent=2, ensure_ascii=False)

    print(f"[✓] Extraction finished. Total unique problems in DB: {len(combined_db)}")