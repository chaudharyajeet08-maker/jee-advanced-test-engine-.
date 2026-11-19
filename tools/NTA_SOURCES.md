# NTA question-bank sources

Imported with `python tools/import_nta_papers.py <pdf_dir>` (re-runnable, skips duplicates).

| Source | What was imported |
|---|---|
| https://jeemain.nta.nic.in/2026-archive/ -> "Question Papers" | JEE Main 2026 B.Tech papers: 2, 4, 5, 6 Apr (both shifts) and 8 Apr Shift 2 = 9 papers x 75 questions = 675 questions |

Notes
- NTA's PDFs store every question/option as an image and contain **no answer key** (the "Possible Answers: 1" in numeric items is a placeholder). `correct_answer` is therefore `N/A` until official keys are added.
- Questions are stored as images (`question_image`) and untagged by topic. To convert to LaTeX text + topic tags, run them through `extractor.py` (needs `GEMINI_API_KEY`).
- Not found on NTA's site (as of import): 8 Apr Shift 1 paper, papers for earlier years, downloadable mock tests (nta.ac.in/Quiz is online-only; the "Download Test" page needs a browser session).
