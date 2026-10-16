"""Isolated PDF text extraction; no document paths or provider secrets in output."""

import io
import json
import sys

from pypdf import PdfReader, apply_configuration


def parse_pdf(data: bytes) -> dict:
    limits = {
        "maximum_declared_stream_length": 4 * 1024 * 1024,
        "array_based_stream_maximum_output_length": 4 * 1024 * 1024,
        "lzw_maximum_output_length": 4 * 1024 * 1024,
        "run_length_maximum_output_length": 4 * 1024 * 1024,
        "zlib_maximum_output_length": 4 * 1024 * 1024,
        "stream_decoding_work_maximum_length": 16 * 1024 * 1024,
        "page_tree_maximum_entries": 1000,
        "xform_maximum_invocations_per_extraction": 100,
        "jbig2dec_binary": None,
    }
    with apply_configuration(**limits):
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return {"error": "不支持加密 PDF，请先解除加密后上传"}
        if len(reader.pages) > 100:
            return {"error": "PDF 超过 100 页，请拆分后上传"}
        pieces = []
        pages = []
        offset = 0
        for number, page in enumerate(reader.pages, 1):
            content = page.get_contents()
            if content is not None and len(content.get_data()) > 4 * 1024 * 1024:
                return {"error": "PDF 页面内容过大，请简化文档后上传"}
            text = (page.extract_text() or "").replace("\r\n", "\n").replace("\r", "\n").strip()
            if any(ord(char) < 32 and char not in "\n\t" for char in text):
                return {"error": "PDF 文本包含非法控制字符，请另存为有效文本 PDF"}
            if not text:
                continue
            if pieces:
                offset += 2
            pages.append({"page": number, "start": offset, "end": offset + len(text)})
            pieces.append(text)
            offset += len(text)
            if offset > 2_000_000:
                return {"error": "PDF 提取文本过大，请拆分后上传"}
        if not pieces:
            return {"error": "PDF 未提取到有效文本，可能是扫描件；当前不支持 OCR"}
        return {
            "text": "\n\n".join(pieces),
            "metadata": {
                "pages": pages,
                "page_count": len(reader.pages),
                "empty_pages": len(reader.pages) - len(pages),
            },
        }


def main():
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    try:
        if len(data) > 10 * 1024 * 1024:
            payload = {"error": "PDF 超过 10 MiB"}
        else:
            payload = parse_pdf(data)
    except Exception:
        payload = {"error": "PDF 解析失败，请检查文件是否损坏或过于复杂"}
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
