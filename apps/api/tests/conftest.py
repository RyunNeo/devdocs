import io

import pytest


@pytest.fixture(autouse=True)
def isolate_provider_credentials(monkeypatch):
    # Tests must never inherit a developer's live provider key from .env.
    monkeypatch.setenv("SILICONFLOW_API_KEY", "")


def build_pdf(texts, compress=False):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 240 Td ({text}) Tj ET".encode())
        if compress:
            stream = stream.flate_encode()
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def make_pdf():
    return build_pdf


@pytest.fixture
def text_pdf():
    return build_pdf(["Page one: React components.", "Page two: Python functions."])
