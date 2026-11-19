## NTA official JEE Main 2026 papers (added 2026-11-19)
Source: https://jeemain.nta.nic.in/2026-archive/ -> "Question Papers" (9 B.Tech papers: 2, 4, 5, 6 Apr both shifts, 8 Apr Shift 2 = 675 questions; 8 Apr Shift 1 is not published).
The PDFs hold every question/option as an IMAGE and no answers. Images (one per question) were cropped with a script and transcribed/solved by agents -> data/extracted/nta26_*.py|json
(uid NTA26-<MMDD>S<shift>-Qnn, exam jee_main, level main). NO official key was available on the NTA site (Final Answer Key page empty; keys sit behind the candidate portal / coaching sites),
so EVERY item has needs_check=True + flag answer_unverified_no_official_key; ambiguous ones also carry ambiguous_or_error_suspected, figure/structure questions figure_described.
Next step: when the official final key (released 20 Apr 2026) is obtained, compare with each answer, fix mismatches, then clear needs_check. NTA reportedly dropped / multi-accepted a few questions (e.g. 4 Apr Shift 1 Physics Sec B Q13 dropped).
data/NTA_BRIEF.md holds the agent brief; data/nta_img/ (question images) is NOT included in project.zip (re-crop from the PDFs).
