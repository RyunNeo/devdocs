import json
import subprocess
import sys
from pathlib import Path


class TextParseError(ValueError):
    pass


def extract_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise TextParseError("无法按 UTF-8 解码，请将文件另存为 UTF-8 后重新上传") from None
    if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
        raise TextParseError("检测到二进制或非法控制字符，请上传纯文本文件")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise TextParseError("文件没有有效文本，请补充内容后重新上传")
    return text


def extract_document(data: bytes, file_type: str) -> tuple[str, dict]:
    if file_type != "pdf":
        return extract_text(data), {}
    if not data.startswith(b"%PDF-"):
        raise TextParseError("PDF 文件头无效，请上传有效的文本 PDF")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.rag.pdf_worker"],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            cwd=Path(__file__).resolve().parents[2],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode != 0:
            raise TextParseError("PDF 解析失败，请检查文件是否损坏或过于复杂")
        payload = json.loads(result.stdout)
        if "error" in payload:
            raise TextParseError(payload["error"])
        return payload["text"], payload["metadata"]
    except subprocess.TimeoutExpired:
        raise TextParseError("PDF 解析超时，请拆分或简化文档后重试") from None
    except OSError:
        raise TextParseError("PDF 解析进程无法启动，请检查运行环境") from None
    except (ValueError, KeyError) as failure:
        if isinstance(failure, TextParseError):
            raise
        raise TextParseError("PDF 解析失败，请检查文件是否损坏") from None
