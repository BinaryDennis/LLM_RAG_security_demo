"""Pattern screen for instruction-like text in documents (prompt-injection heuristics).

This is a cheap, deterministic first line of defence. It only catches known phrasings; a
paraphrased instruction passes. It does not replace treating all retrieved text as untrusted.
"""

import re

_FLAGS = re.IGNORECASE
PATTERNS = [
    re.compile(p, _FLAGS)
    for p in (
        (
            r"\b(ignore|disregard|forget|override)\b[^.!?]{0,40}?\b(previous|prior|above|earlier|all)"
            r"\b[^.!?]{0,30}?\b(instructions?|rules|prompts?|guidelines)\b"
        ),
        (
            r"\b(ignorera|bortse från|glöm|strunta i)\b[^.!?]{0,40}?\b(tidigare|föregående|ovanstående"
            r"|alla)\b[^.!?]{0,30}?\b(instruktion\w*|regler\w*|anvisning\w*)"
        ),
        r"\bsystem\s?(prompt|instruktion\w*|instruction\w*|meddelande\w*|message)\b",
        r"\b(du är nu|you are now)\s+(i|in|en|ett|a|an)\b",
        r"\b(underhållsläge|utvecklarläge)\w*|\b(maintenance|developer|god) mode\b",
        r"\b(nya|new)\s+(instruktion\w*|instructions?)\b",
        r"\b(inled|börja|starta|avsluta)\b[^.!?]{0,20}?\b(varje|alla|ditt|dina)\s+svar\w*",
        (
            r"\b(begin|start|prefix|end)\b[^.!?]{0,20}?\b(every|each|all|your)\s+"
            r"(answers?|responses?|repl(y|ies))\b"
        ),
        (
            r"\b(alla|all)\s+(dokument\w*|documents?)\b[^.!?]{0,80}?"
            r"\b(begränsad\w*|restricted|confidential|hemlig\w*)"
        ),
    )
]

REDACTED = "[removed: suspected instruction]"
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def find_injection(text: str) -> list[str]:
    """Return the instruction-like phrases found in text (empty if none)."""
    return [m.group(0) for p in PATTERNS for m in p.finditer(text)]


def redact_injection(text: str) -> tuple[str, int]:
    """Replace each sentence that contains an instruction-like phrase. Returns (text, count)."""
    sentences = _SENTENCE_END.split(text)
    flagged = [bool(find_injection(s)) for s in sentences]
    if not any(flagged):
        return text, 0
    kept = [REDACTED if bad else s for s, bad in zip(sentences, flagged, strict=True)]
    return " ".join(kept), sum(flagged)
