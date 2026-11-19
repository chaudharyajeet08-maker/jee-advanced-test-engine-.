# NTA JEE Main 2026 paper -> question bank (agent brief)

Project: /home/user/jee-paper-system. Read data/EXTRACTION_BRIEF.md "Schema rules" section and data/taxonomy.json first, and look at
data/extracted/air_test00_12_main.py as the format example. THIS brief overrides EXTRACTION_BRIEF.md where they differ (no Drive, no solution PDF).

## Input
One official NTA paper = 75 question images at data/nta_img/<paper_slug>/q01.png ... q75.png (view them with the Read tool, one at a time or a few per turn).
Each image is the FULL question as printed (figures, tables and the 4 options are inside the image; options appear in order (1)-(4) = A-D).
Normal layout: Q1-25 Mathematics, Q26-50 Physics, Q51-75 Chemistry; in each subject the first 20 are MCQ (single correct, 4 options) and the last 5 are numerical
(Q21-25, Q46-50, Q71-75; no options, integer/decimal answer). VERIFY the subject from the image content, do not trust the layout blindly.
The images contain no answers.

## There is NO official answer key
You must solve every question yourself, carefully (work it out fully; double-check arithmetic; for MCQ check the chosen option really matches).
Every item gets needs_check=True and flags=("answer_unverified_no_official_key",) plus any other flag that applies (figure_described, ...).
If the question is ambiguous, has a printing error, or you cannot get a clean answer, still give your best answer and add flag "ambiguous_or_error_suspected".
Numerical answers: give the number as a string (e.g. "4", "2.5"), rounded as the question asks. Never invent facts. Never copy answers from memory of coaching keys
unless your own working agrees.

## Output (only create files with YOUR prefix)
data/extracted/<prefix>.py  using:
    items, q = make(src="NTA JEE Main 2026 - <date> <shift> (B.Tech)", uid_prefix="<UID>", year=2026, level="main",
                    paper_url="<official pdf url>", exam="jee_main")
    q(no, subject, chapter, qtype, difficulty, text, options, answer, solution, flags=(...), needs_check=True, topic="...")
    save("<prefix>.json", items)
- no = question number in the paper (1..75). qtype: mcq_single (A-D) or numerical (options=None).
- subject physics|chemistry|maths; chapter EXACTLY as in data/taxonomy.json; topic = short specific topic; difficulty 2-4 (JEE Main).
- text/options/solution: transcribe faithfully in LaTeX with $...$ in raw strings (r"..."). Options WITHOUT (A)/(1) labels. Solution: concise and correct.
- Figures/tables you can describe in words: describe them inside the text (flag figure_described). If a question cannot be expressed without its figure,
  SKIP it and list its number in data/extracted/skipped_<prefix>.txt (one line: number + reason). Skipping should be rare.
- Run `cd /home/user/jee-paper-system/data/extracted && python3 <prefix>.py` then `cd /home/user/jee-paper-system && python3 tools/validate_json.py data/extracted/<prefix>.json` -> must report PROBLEMS: 0.
- Do NOT run tools/build_bank.py, do NOT touch web/, do NOT deploy, do not edit other agents' files.
- Write the .py in several chunks if it is long (create the file with the first part, then append with Bash `cat >> file <<'EOF'`), saving progress often.

## Final reply (under 120 words)
Counts per subject, how many skipped (numbers), how many you flagged ambiguous_or_error_suspected (numbers), validator result.
