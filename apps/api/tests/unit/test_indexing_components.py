import pytest


def test_split_markdown_preserves_indent_headers_and_byte_budget():
    from app.rag.splitter import split_document

    text = (
        "# Python\n\n## Functions\n\n```python\ndef add(x):\n    return x + 1\n```\n\n"
        + "中文段落。" * 800
    )
    chunks = split_document(text, "md", {})
    assert len(chunks) > 1
    assert all(0 < len(chunk["content"].encode()) <= 2000 for chunk in chunks)
    assert any("    return x + 1" in chunk["content"] for chunk in chunks)
    assert any("Functions" in str(chunk["metadata"]) for chunk in chunks)


def test_pdf_source_ranges_keep_page_numbers():
    from app.rag.splitter import split_document

    chunks = split_document(
        "Page one\n\nPage two",
        "pdf",
        {
            "pages": [{"page": 1, "start": 0, "end": 8}, {"page": 2, "start": 10, "end": 18}],
        },
    )
    assert [chunk["metadata"]["page"] for chunk in chunks] == [1, 2]


def test_oversized_chunk_count_fails_before_embedding():
    from app.rag.splitter import ChunkLimitError, split_document

    with pytest.raises(ChunkLimitError):
        split_document("a " * 250000, "txt", {})


def test_pdf_invalid_scan_and_encrypted_are_safe_failures():
    import io

    from pypdf import PdfWriter

    from app.rag.loaders import TextParseError, extract_document

    with pytest.raises(TextParseError):
        extract_document(b"not a pdf", "pdf")
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(TextParseError, match="扫描"):
        extract_document(buffer.getvalue(), "pdf")
    writer.encrypt("test-password")
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(TextParseError, match="加密"):
        extract_document(buffer.getvalue(), "pdf")


def test_unclosed_markdown_code_fence_never_drops_tail():
    from app.rag.splitter import split_document

    text = "# Guide\n\nIntro\n\n```python\ncritical_tail = 42\n"
    chunks = split_document(text, "md", {})
    assert any("critical_tail = 42" in chunk["content"] for chunk in chunks)


def test_pdf_nul_is_rejected_before_database_write(make_pdf):
    from app.rag.loaders import TextParseError, extract_document

    with pytest.raises(TextParseError, match="控制字符"):
        extract_document(make_pdf(["hello\\000world"]), "pdf")


def test_pdf_page_limit(make_pdf):
    from app.rag.loaders import TextParseError, extract_document

    with pytest.raises(TextParseError, match="100"):
        extract_document(make_pdf(["text"] * 101), "pdf")


def test_pdf_decompression_limit(make_pdf):
    from app.rag.loaders import TextParseError, extract_document
    data = make_pdf(["a" * (4 * 1024 * 1024 + 1)], compress=True)
    assert len(data) < 10 * 1024 * 1024
    with pytest.raises(TextParseError):
        extract_document(data, "pdf")


def test_pdf_text_budget(monkeypatch):
    from app.rag import pdf_worker

    class Page:
        def get_contents(self):
            return None

        def extract_text(self):
            return "a" * 1_000_000

    class Reader:
        is_encrypted = False
        pages = [Page(), Page(), Page()]

    monkeypatch.setattr(pdf_worker, "PdfReader", lambda *args: Reader())
    assert "文本过大" in pdf_worker.parse_pdf(b"sample")["error"]


def test_pdf_timeout_terminates_and_reaps_child(monkeypatch):
    import subprocess
    import sys

    from app.rag import loaders

    original_run = subprocess.run
    original_popen = subprocess.Popen
    children = []

    def record_child(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child

    def timeout_run(args, **kwargs):
        kwargs["timeout"] = 0.2
        return original_run([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", record_child)
    monkeypatch.setattr(subprocess, "run", timeout_run)
    with pytest.raises(loaders.TextParseError, match="超时"):
        loaders.extract_document(b"%PDF-test", "pdf")
    assert len(children) == 1 and children[0].poll() is not None
