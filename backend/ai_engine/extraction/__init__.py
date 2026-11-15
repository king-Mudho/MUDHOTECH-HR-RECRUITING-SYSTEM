"""Document text extraction (docs/05 §2-3). Pure Python, no Django.

Entry points: :func:`ai_engine.extraction.extract.extract_document` (in-process) and
:func:`ai_engine.extraction.sandbox.run_extraction` (isolated subprocess with limits; use this
for untrusted uploads).
"""
