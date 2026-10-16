from langchain_core.documents import Document
from langchain_text_splitters import (
    ExperimentalMarkdownSyntaxTextSplitter,
    RecursiveCharacterTextSplitter,
)

SPLITTER_VERSION = "markdown-pdf-utf8bytes-2000-200-v2"


class ChunkLimitError(ValueError):
    pass


def split_document(text: str, file_type: str, source_metadata: dict) -> list[dict]:
    if file_type == "pdf":
        units = [
            Document(
                page_content=text[page["start"] : page["end"]], metadata={"page": page["page"]}
            )
            for page in source_metadata.get("pages", [])
        ]
    elif file_type == "md":
        units = ExperimentalMarkdownSyntaxTextSplitter(strip_headers=False).split_text(text)
        # The syntax splitter can discard an unclosed fence; fall back instead of losing EOF text.
        if not units or not text.rstrip().endswith(units[-1].page_content.rstrip()):
            units = [
                Document(page_content=text, metadata={"markdown_fallback": "plain_text_preserved"})
            ]
    else:
        units = [Document(page_content=text)]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000,
        chunk_overlap=200,
        length_function=lambda value: len(value.encode("utf-8")),
        separators=["\n\n", "\n", " ", ""],
        strip_whitespace=False,
    )
    chunks = []
    for unit in units:
        for item in splitter.split_documents([unit]):
            if item.page_content.strip():
                chunks.append({"content": item.page_content, "metadata": item.metadata})
                if len(chunks) > 200:
                    raise ChunkLimitError("文档超过 200 个片段，请拆分文档后建立索引")
    if not chunks:
        raise ChunkLimitError("没有可建立索引的文本，请重新解析文档")
    return chunks
