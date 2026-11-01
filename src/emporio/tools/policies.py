"""Keyword search over the policies manual (``data/processed/policies.md``)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from emporio.paths import POLICIES_PATH
from emporio.tools.common import tokens

STOPWORDS = {
    "de", "da", "do", "das", "dos", "o", "a", "os", "as", "um", "uma", "e", "em", "no", "na",
    "para", "por", "que", "como", "qual", "quai", "posso", "pode", "eu", "me", "meu", "minha",
    "se", "com", "sem", "ser", "tem", "ter", "voces", "voce", "sobre", "loja", "gostaria",
    "saber", "quero", "queria", "ha", "mais", "ao", "aos", "isso", "esse", "essa", "estar",
}
# Query word (normalised) -> extra words to look for.
SYNONYMS = {
    "devolver": ["devolucao", "arrependimento"],
    "arrepender": ["arrependimento", "devolucao"],
    "arrependi": ["arrependimento", "devolucao"],
    "pagar": ["pagamento"],
    "abrir": ["horario", "funcionamento"],
    "aberto": ["horario", "funcionamento"],
    "fechar": ["horario", "funcionamento"],
    "endereco": ["dados", "empresa"],
    "telefone": ["dados", "empresa"],
    "contato": ["dados", "empresa"],
    "whatsapp": ["dados", "empresa"],
    "quebrar": ["defeito", "garantia"],
    "quebrou": ["defeito", "garantia"],
    "estragar": ["defeito", "garantia"],
    "estragou": ["defeito", "garantia"],
    "chegar": ["entrega", "prazo"],
    "cobrar": ["pagamento"],
    "dado": ["privacidade", "lgpd"],
}


# Guidance attached to the tool output (the manual text itself is never edited).
OFFICIAL_CONTACT_NOTE = (
    "Contato oficial da loja: (67) 3341-4444 (telefone/WhatsApp) e "
    "contato@emporiodamusica.com.br. Se o texto trouxer outro número ou grafia de "
    "e-mail, use estes e não cite os outros."
)
DEFECT_NOTE = (
    "Defeito: troca em até 30 dias corridos da COMPRA (4.2) e garantia legal de 90 dias "
    "contados do RECEBIMENTO (8.1); as duas correm em paralelo, a garantia não começa "
    "depois da troca. Não prometa o desfecho e abra um ticket (create_ticket) para a "
    "equipe decidir."
)
CONTACT_MARKERS = ("3321-4500", "empóriodamusica", "3341-4444", "emporiodamusica")


@dataclass(frozen=True)
class Chunk:
    """One section or subsection of the manual."""

    number: str
    title: str
    parent: str
    text: str


@lru_cache(maxsize=2)
def load_chunks(path: Path = POLICIES_PATH) -> tuple[Chunk, ...]:
    """Split the policies Markdown into numbered chunks (sections and subsections)."""
    chunks: list[Chunk] = []
    number = title = parent = ""
    body: list[str] = []

    def flush() -> None:
        text = "\n".join(body).strip()
        if number and text:
            chunks.append(Chunk(number, title, parent, text))
        body.clear()

    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(#{2,3}) (\d+(?:\.\d+)*)\.? (.+)$", line)
        if m:
            flush()
            number, title = m.group(2), m.group(3)
            if m.group(1) == "##":
                parent = f"{number}. {title}"
            continue
        body.append(line)
    flush()
    return tuple(chunks)


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for tok in tokens(query):
        if tok in STOPWORDS or (len(tok) < 3 and not tok.isdigit()):
            continue
        terms.append(tok)
        terms.extend(SYNONYMS.get(tok, []))
    return terms


def search_policies(query: str, max_results: int = 3) -> dict[str, Any]:
    """Find the sections of the store manual most relevant to ``query``.

    Simple keyword scoring (accent/plural-insensitive, prefix matching, a few
    synonyms); a match in a section title weighs more than one in its body. No
    embeddings. Use it for rules about exchanges, returns, payment, shipping,
    hours, warranty, promotions, privacy and store contact data.

    Args:
        query: What the customer asked, in Portuguese.
        max_results: Number of sections to return (1 to 3).

    Returns:
        ``{"count", "results": [{"section", "title", "parent", "text", "score"}], "notes"?}``.
    """
    max_results = max(1, min(int(max_results), 3))
    terms = _query_terms(query)
    scored = []
    for chunk in load_chunks():
        title_words = tokens(chunk.title + " " + chunk.parent)
        body_words = tokens(chunk.text)
        score = 0.0
        for term in terms:
            prefix = term[:5]
            if any(w.startswith(prefix) for w in title_words):
                score += 3
            hits = sum(1 for w in body_words if w.startswith(prefix))
            score += min(hits, 3)
        if chunk.number == "0":
            score *= 0.5  # the cover only repeats data that lives in 1.2
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: (-x[0], x[1].number))
    results = [
        {"section": c.number, "title": c.title, "parent": c.parent, "text": c.text, "score": s}
        for s, c in scored[:max_results]
    ]
    out: dict[str, Any] = {"count": len(results), "results": results}
    notes = []
    if any(m in r["text"] for r in results for m in CONTACT_MARKERS):
        notes.append(OFFICIAL_CONTACT_NOTE)
    if any(r["section"].split(".")[0] in ("4", "8") for r in results):
        notes.append(DEFECT_NOTE)
    if notes:
        out["notes"] = notes
    return out
