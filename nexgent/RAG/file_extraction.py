"""Extract text from the file types supported by the RAG embed endpoint."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

import pdf_ocr


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MEBIBYTE = 1024 * 1024
MAX_DOCX_UPLOAD_BYTES = 25 * MEBIBYTE
MAX_DOCX_UNCOMPRESSED_BYTES = 100 * MEBIBYTE
MAX_DOCX_MEMBERS = 2_000
MAX_DOCX_MEMBER_BYTES = 50 * MEBIBYTE
DOCX_REQUIRED_MEMBERS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
}


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


class InvalidDocxError(FileExtractionError):
    """Raised when a DOCX cannot be parsed for text extraction."""


class DocxResourceLimitError(FileExtractionError):
    """Raised when a DOCX exceeds the bounded Phase 1 processing limits."""


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
    """Use native PDF text per page, with OCR only for empty pages."""
    try:
        reader = PdfReader(BytesIO(content))
        page_texts: list[str] = []
        ocr_session: pdf_ocr.PdfOcrSession | None = None
        try:
            for page_index, page in enumerate(reader.pages):
                native_text = (page.extract_text() or "").strip()
                if native_text:
                    page_texts.append(native_text)
                    continue

                if ocr_session is None:
                    ocr_session = pdf_ocr.PdfOcrSession(content)
                ocr_text = ocr_session.extract_page_text(page_index).strip()
                if ocr_text:
                    page_texts.append(ocr_text)
        finally:
            if ocr_session is not None:
                ocr_session.close()
    except pdf_ocr.PdfOcrError:
        raise
    except PdfReadError:
        raise InvalidPdfError("Uploaded PDF could not be read") from None
    except Exception:
        raise InvalidPdfError("Uploaded PDF could not be read") from None

    document = "\n\n".join(page_texts)
    if not document.strip():
        raise EmptyDocumentError(
            "Uploaded PDF contains no extractable or OCR-recognizable text"
        )
    return document


def validate_docx_archive(content: bytes) -> None:
    """Reject malformed, encrypted, or excessively large DOCX packages."""
    if len(content) > MAX_DOCX_UPLOAD_BYTES:
        raise DocxResourceLimitError(
            "Uploaded DOCX exceeds supported processing limits"
        )

    try:
        with ZipFile(BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > MAX_DOCX_MEMBERS:
                raise DocxResourceLimitError(
                    "Uploaded DOCX exceeds supported processing limits"
                )

            total_uncompressed = 0
            member_names: set[str] = set()
            for member in members:
                if member.flag_bits & 0x1:
                    raise InvalidDocxError("Uploaded DOCX could not be read")
                if member.file_size > MAX_DOCX_MEMBER_BYTES:
                    raise DocxResourceLimitError(
                        "Uploaded DOCX exceeds supported processing limits"
                    )
                total_uncompressed += member.file_size
                if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise DocxResourceLimitError(
                        "Uploaded DOCX exceeds supported processing limits"
                    )
                member_names.add(member.filename)

            if not DOCX_REQUIRED_MEMBERS.issubset(member_names):
                raise InvalidDocxError("Uploaded DOCX could not be read")
    except (InvalidDocxError, DocxResourceLimitError):
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError):
        raise InvalidDocxError("Uploaded DOCX could not be read") from None


def _extract_docx_table(table: Table) -> str:
    """Flatten one ordinary top-level table while preserving row/cell order."""
    return "\n".join("\t".join(cell.text for cell in row.cells) for row in table.rows)


def extract_docx_text(content: bytes) -> str:
    """Extract top-level DOCX paragraphs and tables in document order."""
    validate_docx_archive(content)
    try:
        document = Document(BytesIO(content))
        blocks: list[str] = []
        for item in document.iter_inner_content():
            if isinstance(item, Paragraph):
                block = item.text
            elif isinstance(item, Table):
                block = _extract_docx_table(item)
            else:
                continue
            if block.strip():
                blocks.append(block)
    except Exception:
        raise InvalidDocxError("Uploaded DOCX could not be read") from None

    extracted = "\n\n".join(blocks)
    if not extracted.strip():
        raise EmptyDocumentError(
            "Uploaded DOCX contains no extractable text. "
            "OCR for images embedded in DOCX is not supported"
        )
    return extracted


def extract_document(filename: str, content: bytes) -> str:
    """Route an upload to its extension-specific text extractor."""
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            "Only UTF-8 .txt/.md, .docx, and .pdf files are supported; "
            "legacy .doc is not supported"
        )
    if not content:
        raise EmptyDocumentError("Uploaded file is empty")
    if extension in {".txt", ".md"}:
        format_name = "Markdown" if extension == ".md" else "TXT"
        return extract_txt_text(content, format_name)
    if extension == ".docx":
        return extract_docx_text(content)
    return extract_pdf_text(content)
