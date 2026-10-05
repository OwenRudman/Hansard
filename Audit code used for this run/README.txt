Hansard auto-audit pipeline (built with Claude, Oct 2026)

hansard_auto_audit/auditor.py   Label-stage audit of a cleaned JSON against its PDF, plus flags
hansard_auto_audit/pdfparse.py  Reads headings / scenes / speaker turns out of the Hansard PDF
hansard_auto_audit/run_batch.py Batch runner: cleaned JSONs + PDFs -> ready/ and check/ (+ flag lists)
harness.js                      Loads a JSON into the Hansard tool's own page (sample.html) headlessly,
                                runs its Suggest hierarchy, and exports exactly like Download JSON
conv.js                         Turns a tool page rendered for a Mzalendo link into the raw JSON
sample.html                     Saved copy of the Hansard tool page the harness runs on

Run:  python3 hansard_auto_audit/run_batch.py <cleaned_json_dir> <pdf_dir> <out_dir>
Needs: Python 3 with pymupdf and levenshtein; Node with playwright + Chromium.

Note: run_batch.py writes its results to folders called ready/ and check/. For the 12th Senate run these were
renamed to "Finished - no issues found" and "Needs human check - each has a flags list" (in "12th Senate - audit results").
