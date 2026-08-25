"""Rasterize and OCR individual PDF pages without RAG pipeline concerns."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pypdfium2 as pdfium
import pytesseract


OCR_LANGUAGES = "kor+eng"
OCR_CONFIG = "--psm 6"
REQUIRED_OCR_LANGUAGES = frozenset({"kor", "eng"})
OCR_DPI = 300
OCR_TIMEOUT_SECONDS = 30
MAX_OCR_PAGES = 50


class PdfOcrError(RuntimeError):
    """Base class for sanitized PDF OCR failures."""


class OcrEngineUnavailableError(PdfOcrError):
    """Raised when the Tesseract executable cannot be used."""


class OcrLanguageUnavailableError(PdfOcrError):
    """Raised when required Korean or English trained data is unavailable."""


class OcrTimeoutError(PdfOcrError):
    """Raised when one page exceeds the configured OCR timeout."""


class OcrRenderError(PdfOcrError):
    """Raised when PDFium cannot rasterize a requested page."""


class OcrRecognitionError(PdfOcrError):
    """Raised when Tesseract fails while recognizing a page."""


class OcrPageLimitError(PdfOcrError):
    """Raised when one PDF requires more OCR fallback pages than allowed."""


@lru_cache(maxsize=1)
def ensure_ocr_runtime() -> None:
    """Verify Tesseract and the required language data without fallback."""
    try:
        installed_languages = set(pytesseract.get_languages(config=""))
    except pytesseract.TesseractNotFoundError:
        raise OcrEngineUnavailableError(
            "PDF OCR is unavailable because the OCR engine is not installed"
        ) from None
    except pytesseract.TesseractError:
        raise OcrEngineUnavailableError(
            "PDF OCR is unavailable because the OCR engine could not start"
        ) from None

    missing = REQUIRED_OCR_LANGUAGES - installed_languages
    if missing:
        raise OcrLanguageUnavailableError(
            "PDF OCR requires Korean and English OCR language data"
        )


class PdfOcrSession:
    """Lazily render and OCR bounded pages from one PDF byte sequence."""

    def __init__(self, content: bytes) -> None:
        self._content = content
        self._document: Any | None = None
        self._ocr_page_count = 0

    def __enter__(self) -> PdfOcrSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._document is not None:
            self._document.close()
            self._document = None

    def extract_page_text(self, page_index: int) -> str:
        """Return `kor+eng`/PSM-6 OCR text for one zero-based PDF page."""
        if self._ocr_page_count >= MAX_OCR_PAGES:
            raise OcrPageLimitError(
                f"PDF OCR is limited to {MAX_OCR_PAGES} pages per document"
            )
        ensure_ocr_runtime()
        document = self._get_document()
        self._ocr_page_count += 1

        page = None
        bitmap = None
        image = None
        try:
            try:
                page = document[page_index]
                bitmap = page.render(scale=OCR_DPI / 72)
                image = bitmap.to_pil()
            except Exception:
                raise OcrRenderError(
                    "A PDF page could not be prepared for OCR"
                ) from None

            try:
                return pytesseract.image_to_string(
                    image,
                    lang=OCR_LANGUAGES,
                    config=OCR_CONFIG,
                    timeout=OCR_TIMEOUT_SECONDS,
                )
            except pytesseract.TesseractNotFoundError:
                raise OcrEngineUnavailableError(
                    "PDF OCR is unavailable because the OCR engine is not installed"
                ) from None
            except pytesseract.TesseractError:
                raise OcrRecognitionError(
                    "A PDF page could not be recognized by OCR"
                ) from None
            except RuntimeError:
                raise OcrTimeoutError(
                    f"PDF OCR exceeded the {OCR_TIMEOUT_SECONDS}-second page timeout"
                ) from None
        finally:
            if image is not None:
                image.close()
            if bitmap is not None:
                bitmap.close()
            if page is not None:
                page.close()

    def _get_document(self) -> Any:
        if self._document is None:
            try:
                self._document = pdfium.PdfDocument(self._content)
            except Exception:
                raise OcrRenderError(
                    "The uploaded PDF could not be prepared for OCR"
                ) from None
        return self._document
