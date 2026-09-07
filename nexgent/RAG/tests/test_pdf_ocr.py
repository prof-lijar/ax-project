from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pdf_ocr


class FakeImage:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeBitmap:
    def __init__(self, image: FakeImage) -> None:
        self.image = image
        self.closed = False

    def to_pil(self) -> FakeImage:
        return self.image

    def close(self) -> None:
        self.closed = True


class FakePage:
    def __init__(self, bitmap: FakeBitmap) -> None:
        self.bitmap = bitmap
        self.render_scales: list[float] = []
        self.closed = False

    def render(self, *, scale: float) -> FakeBitmap:
        self.render_scales.append(scale)
        return self.bitmap

    def close(self) -> None:
        self.closed = True


class FakeDocument:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.requested_indexes: list[int] = []
        self.closed = False

    def __getitem__(self, page_index: int) -> FakePage:
        self.requested_indexes.append(page_index)
        return self.page

    def close(self) -> None:
        self.closed = True


class PdfOcrTests(unittest.TestCase):
    def setUp(self) -> None:
        pdf_ocr.ensure_ocr_runtime.cache_clear()

    def tearDown(self) -> None:
        pdf_ocr.ensure_ocr_runtime.cache_clear()

    def test_runtime_requires_korean_and_english_language_data(self) -> None:
        with patch.object(
            pdf_ocr.pytesseract,
            "get_languages",
            return_value=["eng"],
        ):
            with self.assertRaisesRegex(
                pdf_ocr.OcrLanguageUnavailableError,
                "requires Korean and English",
            ):
                pdf_ocr.ensure_ocr_runtime()

    def test_missing_engine_returns_sanitized_error(self) -> None:
        with patch.object(
            pdf_ocr.pytesseract,
            "get_languages",
            side_effect=pdf_ocr.pytesseract.TesseractNotFoundError(),
        ):
            with self.assertRaisesRegex(
                pdf_ocr.OcrEngineUnavailableError,
                "OCR engine is not installed",
            ) as raised:
                pdf_ocr.ensure_ocr_runtime()

        self.assertNotIn("/", str(raised.exception))

    def test_page_uses_production_dpi_language_and_psm_configuration(self) -> None:
        image = FakeImage()
        bitmap = FakeBitmap(image)
        page = FakePage(bitmap)
        document = FakeDocument(page)

        with (
            patch.object(pdf_ocr, "ensure_ocr_runtime"),
            patch.object(pdf_ocr.pdfium, "PdfDocument", return_value=document),
            patch.object(
                pdf_ocr.pytesseract,
                "image_to_string",
                return_value="인식된 OCR text",
            ) as recognize,
        ):
            with pdf_ocr.PdfOcrSession(b"pdf") as session:
                text = session.extract_page_text(4)

        self.assertEqual(text, "인식된 OCR text")
        self.assertEqual(document.requested_indexes, [4])
        self.assertEqual(page.render_scales, [pdf_ocr.OCR_DPI / 72])
        recognize.assert_called_once_with(
            image,
            lang="kor+eng",
            config="--psm 6",
            timeout=pdf_ocr.OCR_TIMEOUT_SECONDS,
        )
        self.assertTrue(image.closed)
        self.assertTrue(bitmap.closed)
        self.assertTrue(page.closed)
        self.assertTrue(document.closed)

    def test_timeout_returns_sanitized_error_and_closes_page_resources(self) -> None:
        image = FakeImage()
        bitmap = FakeBitmap(image)
        page = FakePage(bitmap)
        document = FakeDocument(page)

        with (
            patch.object(pdf_ocr, "ensure_ocr_runtime"),
            patch.object(pdf_ocr.pdfium, "PdfDocument", return_value=document),
            patch.object(
                pdf_ocr.pytesseract,
                "image_to_string",
                side_effect=RuntimeError("internal timeout details"),
            ),
            self.assertRaisesRegex(
                pdf_ocr.OcrTimeoutError,
                "30-second page timeout",
            ) as raised,
        ):
            with pdf_ocr.PdfOcrSession(b"pdf") as session:
                session.extract_page_text(0)

        self.assertNotIn("internal", str(raised.exception))
        self.assertTrue(image.closed)
        self.assertTrue(bitmap.closed)
        self.assertTrue(page.closed)
        self.assertTrue(document.closed)

    def test_rasterization_failure_returns_sanitized_error(self) -> None:
        page = MagicMock()
        page.render.side_effect = RuntimeError("/private/path")
        document = FakeDocument(page)

        with (
            patch.object(pdf_ocr, "ensure_ocr_runtime"),
            patch.object(pdf_ocr.pdfium, "PdfDocument", return_value=document),
            self.assertRaisesRegex(
                pdf_ocr.OcrRenderError,
                "could not be prepared for OCR",
            ) as raised,
        ):
            with pdf_ocr.PdfOcrSession(b"pdf") as session:
                session.extract_page_text(0)

        self.assertNotIn("/private/path", str(raised.exception))
        page.close.assert_called_once_with()
        self.assertTrue(document.closed)

    def test_recognition_failure_returns_sanitized_error(self) -> None:
        image = FakeImage()
        bitmap = FakeBitmap(image)
        page = FakePage(bitmap)
        document = FakeDocument(page)

        with (
            patch.object(pdf_ocr, "ensure_ocr_runtime"),
            patch.object(pdf_ocr.pdfium, "PdfDocument", return_value=document),
            patch.object(
                pdf_ocr.pytesseract,
                "image_to_string",
                side_effect=pdf_ocr.pytesseract.TesseractError(
                    1,
                    "/private/tessdata failure",
                ),
            ),
            self.assertRaisesRegex(
                pdf_ocr.OcrRecognitionError,
                "could not be recognized by OCR",
            ) as raised,
        ):
            with pdf_ocr.PdfOcrSession(b"pdf") as session:
                session.extract_page_text(0)

        self.assertNotIn("/private", str(raised.exception))

    def test_ocr_page_limit_is_enforced_before_an_extra_render(self) -> None:
        image = FakeImage()
        bitmap = FakeBitmap(image)
        page = FakePage(bitmap)
        document = FakeDocument(page)

        with (
            patch.object(pdf_ocr, "MAX_OCR_PAGES", 1),
            patch.object(pdf_ocr, "ensure_ocr_runtime"),
            patch.object(pdf_ocr.pdfium, "PdfDocument", return_value=document),
            patch.object(pdf_ocr.pytesseract, "image_to_string", return_value="text"),
        ):
            with pdf_ocr.PdfOcrSession(b"pdf") as session:
                self.assertEqual(session.extract_page_text(0), "text")
                with self.assertRaisesRegex(
                    pdf_ocr.OcrPageLimitError,
                    "limited to 1 pages",
                ):
                    session.extract_page_text(1)

        self.assertEqual(document.requested_indexes, [0])


if __name__ == "__main__":
    unittest.main()
