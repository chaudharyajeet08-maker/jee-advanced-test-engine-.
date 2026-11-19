"""Import NTA JEE Main "question paper" PDFs into the question bank.

NTA publishes these PDFs with every question and option stored as an embedded
image (no text layer), and without answers. So each question is cropped into
one PNG (stitched across page breaks) and added to database/questions_db.json
with a `question_image` field. The app/generator embed that image when
rendering. Re-running is safe: questions already imported are skipped.

Usage:  python tools/import_nta_papers.py <pdf_dir> [--db database/questions_db.json]
"""
import argparse
import io
import json
import os
import re
import sys

import fitz  # PyMuPDF
from PIL import Image

HEADER_RE = re.compile(r"Question Number\s*:\s*(\d+)\s+Question Id\s*:\s*(\d+)\s+Question Type\s*:\s*(\w+)")
SECTION_RE = re.compile(r"^(Mathematics|Physics|Chemistry)\s+Section\s+([AB])\b", re.I)
META_RE = re.compile(r"^Response Type\s*:")
OPT_ID_RE = re.compile(r"^\d{6,}\.\s*$")
DPI = 130
TOP_MARGIN, BOTTOM_MARGIN = 28, 28


def paper_label(pdf_name):
    m = re.search(r"(\d+)(?:st|nd|rd|th)_(\w+)_(\d{4})_Shift_(\d)", pdf_name)
    if not m:
        return os.path.splitext(pdf_name)[0].replace("_", " ")
    return f"NTA JEE Main {m.group(3)} - {m.group(1)} {m.group(2)} Shift {m.group(4)}"


def page_marks(page):
    """Return [(y0, y1, kind, payload)] for question headers and section headings."""
    marks = []
    for b in page.get_text("blocks"):
        x0, y0, x1, y1, text = b[:5]
        flat = " ".join(text.split())
        h = HEADER_RE.search(flat)
        if h:
            marks.append((y0, y1, "q", (int(h.group(1)), h.group(2), h.group(3))))
            continue
        s = SECTION_RE.match(flat)
        if s:
            marks.append((y0, y1, "sec", s.group(1).capitalize()))
            continue
        if META_RE.match(flat):
            # NTA's numeric-answer metadata block (Response Type / Possible Answers = placeholder "1")
            marks.append((y0, y1, "meta", None))
    return sorted(marks, key=lambda m: m[0])


def hide_option_ids(page):
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = "".join(sp["text"] for sp in ln["spans"]).strip()
            if OPT_ID_RE.match(t):
                page.add_redact_annot(fitz.Rect(ln["bbox"]), fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)


def render_clip(page, y0, y1):
    rect = fitz.Rect(0, max(y0, 0), page.rect.width, min(y1, page.rect.height))
    if rect.height < 8:
        return None
    pix = page.get_pixmap(clip=rect, dpi=DPI, colorspace=fitz.csGRAY)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")


def trim_whitespace(img, pad=10):
    inv = img.point(lambda v: 255 - v)
    box = inv.getbbox()
    if not box:
        return None
    x0, y0, x1, y1 = box
    return img.crop((max(x0 - pad, 0), max(y0 - pad, 0), min(x1 + pad, img.width), min(y1 + pad, img.height)))


def extract_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    for page in doc:
        hide_option_ids(page)
    # flatten all marks across pages in reading order
    items = []  # (page_no, y0, y1, kind, payload)
    for pno, page in enumerate(doc):
        for y0, y1, kind, payload in page_marks(page):
            items.append((pno, y0, y1, kind, payload))
    subject = "Mathematics"
    questions = []
    for i, (pno, y0, y1, kind, payload) in enumerate(items):
        if kind == "sec":
            subject = payload
            continue
        if kind == "meta":
            continue
        qno, qid, qtype = payload
        # section heading belonging to this question: nearest previous "sec" mark
        for j in range(i - 1, -1, -1):
            if items[j][3] == "sec":
                subject = items[j][4]
                break
        # end boundary = next mark (question or section) in reading order, else end of doc
        nxt = items[i + 1] if i + 1 < len(items) else None
        parts = []
        start_p, start_y = pno, y1 + 2
        end_p, end_y = (nxt[0], nxt[1]) if nxt else (len(doc) - 1, doc[len(doc) - 1].rect.height - BOTTOM_MARGIN)
        for p in range(start_p, end_p + 1):
            top = start_y if p == start_p else TOP_MARGIN
            bot = end_y if p == end_p else doc[p].rect.height - BOTTOM_MARGIN
            im = render_clip(doc[p], top, bot)
            if im is not None:
                parts.append(im)
        if not parts:
            continue
        w = max(p.width for p in parts)
        stitched = Image.new("L", (w, sum(p.height for p in parts)), 255)
        y = 0
        for p in parts:
            stitched.paste(p, (0, y))
            y += p.height
        stitched = trim_whitespace(stitched)
        if stitched is None:
            continue
        questions.append({"qno": qno, "qid": qid, "qtype": qtype, "subject": subject, "image": stitched, "page": pno + 1})
    return questions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf_dir")
    ap.add_argument("--db", default="database/questions_db.json")
    ap.add_argument("--img-dir", default="static/questions")
    args = ap.parse_args()

    os.makedirs(args.img_dir, exist_ok=True)
    db = []
    if os.path.exists(args.db):
        with open(args.db, encoding="utf-8") as f:
            db = json.load(f)
    seen = {(q.get("source_book"), q.get("problem_number")) for q in db}

    added = 0
    for name in sorted(os.listdir(args.pdf_dir)):
        if not name.lower().endswith(".pdf"):
            continue
        label = paper_label(name)
        slug = re.sub(r"\W+", "_", label).strip("_").lower()
        qs = extract_pdf(os.path.join(args.pdf_dir, name))
        n = 0
        for q in qs:
            pn = f"Q{q['qno']}"
            if (label, pn) in seen:
                continue
            rel = f"{args.img_dir}/{slug}_q{q['qno']:02d}.png".replace("\\", "/")
            # 16 grey levels is plenty for scanned black-on-white text and cuts size ~3x
            q["image"].point(lambda v: min(v // 16, 15) * 17).save(rel, optimize=True, bits=4)
            is_mcq = q["qtype"].upper() == "MCQ"
            db.append({
                "problem_number": pn,
                "topic": f"{q['subject']} (JEE Main PYQ - topic not tagged yet)",
                "subtopic": "Untagged",
                "question_text": "",
                "question_image": rel,
                "has_diagram": False,
                "correct_answer": "N/A",
                "solution_steps": "Official answer key not imported yet; question is stored as an image.",
                "page_number": q["page"],
                "subject": q["subject"],
                "source_book": label,
                "question_type": "single_choice" if is_mcq else "numerical",
                "nta_question_id": q["qid"],
            })
            seen.add((label, pn))
            n += 1
        added += n
        print(f"{label}: {n} questions ({len(qs)} found)")

    with open(args.db, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    print(f"Added {added}; DB now has {len(db)} questions")


if __name__ == "__main__":
    sys.exit(main())
