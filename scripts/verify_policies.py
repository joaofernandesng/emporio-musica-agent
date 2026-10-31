"""Check that data/processed/policies.md is faithful to the manual PDF.

Compares the multiset of words in the Markdown with the words extracted from the
PDF (running headers/footers removed). Formatting symbols are ignored. Prints
the words present on only one side; exits non-zero if there are any.

Run with: ``python scripts/verify_policies.py``
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from emporio.paths import POLICIES_PATH, POLICIES_PDF  # noqa: E402

# Words the Markdown legitimately adds (the "0. Capa" heading we created).
ALLOWED_EXTRA_IN_MD = Counter({"0": 1, "Capa": 1})


def words(text: str) -> Counter:
    """Tokenise ``text`` into word characters only (punctuation/Markdown symbols ignored)."""
    return Counter(re.findall(r"\w+", text))


def main() -> int:
    """Return 0 when the Markdown and the PDF contain the same words."""
    pdf_text = "\n".join(page.extract_text() for page in PdfReader(POLICIES_PDF).pages)
    # Drop the running header (pages 2-8) and the "Página N" footer.
    pdf_text = re.sub(r"Empório\s+da\s+Música\s+Manual\s+de\s+Políticas\s+e\s+Procedimentos", " ", pdf_text)
    pdf_text = re.sub(r"Página\s+\d+", " ", pdf_text)
    md_text = POLICIES_PATH.read_text(encoding="utf-8")
    md_body = md_text.split("\n", 1)[1]  # skip the H1 title we added
    pdf, md = words(pdf_text), words(md_body)
    only_pdf, only_md = pdf - md, md - pdf - ALLOWED_EXTRA_IN_MD
    print("only in PDF :", dict(only_pdf))
    print("only in MD  :", dict(only_md))
    return 1 if only_pdf or only_md else 0


if __name__ == "__main__":
    sys.exit(main())
