import os
import json
import random
import re
import subprocess
from datetime import datetime

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>JEE Advanced Physics Practice Paper</title>

<!-- KaTeX for ultra-fast, sharp mathematical typography -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.10/dist/contrib/auto-render.min.js"
    onload="renderMathInElement(document.body, {
        delimiters: [
            {left: '$$', right: '$$', display: true},
            {left: '$', right: '$', display: false},
            {left: '\\\\(', right: '\\\\)', display: false},
            {left: '\\\\[', right: '\\\\]', display: true}
        ],
        throwOnError : false
    });">
</script>

<style>
  @page { size: A4; margin: 18mm; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.65;
    color: #1a202c;
    max-width: 900px;
    margin: 0 auto;
    padding: 30px;
    background: #ffffff;
  }
  .header { text-align: center; border-bottom: 2px solid #2d3748; padding-bottom: 15px; margin-bottom: 25px; }
  .header h1 { margin: 0; font-size: 22px; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase; }
  .header p { margin: 6px 0 0 0; font-size: 13px; color: #4a5568; font-weight: 600; }
  
  .section-tag {
    background: #edf2f7;
    color: #2b6cb0;
    font-size: 13px;
    font-weight: 700;
    padding: 6px 14px;
    border-left: 4px solid #3182ce;
    margin: 30px 0 20px 0;
    text-transform: uppercase;
  }

  .question-block {
    margin-bottom: 28px;
    padding-bottom: 18px;
    border-bottom: 1px dashed #e2e8f0;
    page-break-inside: avoid;
  }
  .q-header { display: flex; align-items: baseline; gap: 8px; margin-bottom: 6px; }
  .q-num { font-weight: 800; font-size: 15px; color: #2d3748; }
  .q-type { font-size: 11px; background: #e2e8f0; color: #4a5568; padding: 2px 8px; border-radius: 4px; font-weight: 700; }
  
  .q-text { font-size: 15px; margin: 8px 0 12px 0; color: #2d3748; }
  
  .options-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-top: 10px;
    padding-left: 10px;
  }
  .option-item {
    font-size: 14.5px;
    background: #f7fafc;
    border: 1px solid #edf2f7;
    padding: 8px 12px;
    border-radius: 6px;
  }

  .sol-block {
    background: #f8fafc;
    border-left: 4px solid #38a169;
    padding: 14px 18px;
    margin-bottom: 22px;
    border-radius: 0 6px 6px 0;
    page-break-inside: avoid;
  }
  .ans-badge {
    display: inline-block;
    background: #c6f6d5;
    color: #22543d;
    font-weight: 700;
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 13px;
  }
  .sol-steps { margin-top: 10px; font-size: 14px; color: #2d3748; }
  .page-break { page-break-before: always; }
</style>
</head>
<body>

<div class="header">
  <h1>JEE (Advanced) Physics Practice Test</h1>
  <p>Topic: {{TOPIC}} &nbsp;|&nbsp; Target: JEE Advanced Pattern</p>
</div>

<div class="section-tag">Section I: Questions</div>
{{QUESTIONS}}

<div class="page-break"></div>

<div class="header" style="margin-top: 25px;">
  <h1>Answer Key & Step-by-Step Derivations</h1>
</div>
{{SOLUTIONS}}

</body>
</html>
"""

def clean_option_text(text: str) -> str:
    # Cleans duplicate labels like 'A)', '(A)', '1)' if already generated in options
    return re.sub(r"^(\([A-Da-d0-9]\)|[A-Da-d0-9][\.\)])\s*", "", text).strip()

def assemble_paper(
    topics: list,
    db_path: str = "database/questions_db.json",
    output_dir: str = "output",
    num_single: int = 4,
    num_multi: int = 4,
    num_numeric: int = 4
):
    if not os.path.exists(db_path):
        print("[!] Database not found.")
        return

    with open(db_path, "r", encoding="utf-8") as f:
        try:
            db = json.load(f)
        except Exception:
            db = []

    if not db:
        print("[!] Database is empty.")
        return

    random.shuffle(db)
    selected = db[:(num_single + num_multi + num_numeric)]

    q_html_parts = []
    sol_html_parts = []

    for idx, q in enumerate(selected, 1):
        q_type = q.get("question_type", "Question").replace("_", " ").title()
        q_text = q.get("question_text", "").strip()

        # Build clean options without duplicate letters
        options_html = ""
        options = q.get("options")
        if options and isinstance(options, list) and len(options) > 0:
            labels = ["(A)", "(B)", "(C)", "(D)"]
            opts_rendered = ""
            for i, opt in enumerate(options):
                lbl = labels[i] if i < len(labels) else f"({i+1})"
                cleaned = clean_option_text(str(opt))
                opts_rendered += f'<div class="option-item"><strong>{lbl}</strong> {cleaned}</div>'
            options_html = f'<div class="options-grid">{opts_rendered}</div>'

        q_block = f"""
        <div class="question-block">
          <div class="q-header">
            <span class="q-num">Q{idx}.</span>
            <span class="q-type">{q_type}</span>
          </div>
          <div class="q-text">{q_text}</div>
          {options_html}
        </div>
        """
        q_html_parts.append(q_block)

        ans = q.get("correct_answer", "N/A")
        sol = q.get("solution_steps", "Detailed solution not provided.").strip()
        sol_block = f"""
        <div class="sol-block">
          <div><strong>Question {idx}</strong> &nbsp; <span class="ans-badge">Correct Answer: {ans}</span></div>
          <div class="sol-steps"><strong>Derivation:</strong><br>{sol}</div>
        </div>
        """
        sol_html_parts.append(sol_block)

    rendered = HTML_TEMPLATE.replace("{{TOPIC}}", ", ".join(topics))
    rendered = rendered.replace("{{QUESTIONS}}", "\n".join(q_html_parts))
    rendered = rendered.replace("{{SOLUTIONS}}", "\n".join(sol_html_parts))

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(output_dir, f"JEE_Advanced_{timestamp}.html")

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(rendered)

    print(f"[✓] Generated clean paper: {out_file}")
    subprocess.run(["open", out_file])