"""Extract text from the file types supported by the RAG embed endpoint."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


class FileExtractionError(ValueError):
    """Base class for client-correctable file extraction errors."""


class UnsupportedFileTypeError(FileExtractionError):
    """Raised when a filename has an unsupported extension."""


class EmptyDocumentError(FileExtractionError):
    """Raised when an upload contains no usable text."""


class InvalidTextEncodingError(FileExtractionError):
    """Raised when a TXT upload is not valid UTF-8."""


class InvalidPdfError(FileExtractionError):
    """Raised when a PDF cannot be parsed for text extraction."""


def extract_txt_text(content: bytes, format_name: str = "TXT") -> str:
    """Decode one plain-text document strictly as UTF-8."""
    try:
        document = content.decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidTextEncodingError(
            f"Uploaded {format_name} file is not valid UTF-8"
        ) from None
    if not document.strip():
        raise EmptyDocumentError(f"Uploaded {format_name} file contains no text")
    return document


def extract_pdf_text(content: bytes) -> str:
    """Extract page-ordered text from a normal text-based PDF without OCR."""
    try:
        reader = PdfReader(BytesIO(content))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError:
        raise InvalidPdfError("Uploaded PDF could not be read") from None

    document = "\n\n".join(text.strip() for text in page_texts if text.strip())
    if not document.strip():
        raise EmptyDocumentError(
            "Uploaded PDF contains no extractable text; "
            "scanned/image-only PDFs are not supported"
        )
    return document


def extract_document(filename: str, content: bytes) -> str:
    """Route an upload to its extension-specific text extractor."""
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            "Only UTF-8 .txt/.md and text-based .pdf files are supported"
        )
    if not content:
        raise EmptyDocumentError("Uploaded file is empty")
    if extension in {".txt", ".md"}:
        format_name = "Markdown" if extension == ".md" else "TXT"
        return extract_txt_text(content, format_name)
    return extract_pdf_text(content)
