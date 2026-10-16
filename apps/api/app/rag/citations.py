import re
from dataclasses import dataclass

INSUFFICIENT = "当前文档中未找到足够依据，请补充相关文档或明确问题。"


class CitationError(ValueError):
    pass


@dataclass
class ValidatedAnswer:
    content: str
    citations: list[dict]
    insufficient: bool = False


def validate_answer(text, sources):
    # A mixed speculative answer is still a refusal, even when it cites a real source.
    if re.search(r"\[\[\s*INSUFFICIENT_EVIDENCE\s*\]\]", text, re.IGNORECASE):
        return ValidatedAnswer(INSUFFICIENT, [], True)
    numbers = list(dict.fromkeys(int(n) for n in re.findall(r"\[(\d+)\]", text)))
    available = {source.number: source for source in sources}
    if not text.strip() or not numbers or any(n not in available for n in numbers):
        raise CitationError("引用校验失败，当前回答仅供核对")
    citations = []
    for n in numbers:
        source = available[n]
        citations.append(
            {
                "number": n,
                "document_id": str(source.document_id),
                "chunk_id": str(source.chunk_id),
                "chunk_index": source.chunk_index,
                "filename": source.filename,
                "content": source.content,
                "metadata": source.metadata,
                "index_fingerprint": source.index_fingerprint,
                "source_status": "current",
            }
        )
    return ValidatedAnswer(text, citations)
