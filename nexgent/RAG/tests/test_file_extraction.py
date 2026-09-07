from __future__ import annotations

from io import BytesIO
import unittest
from unittest.mock import Mock, patch
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from docx.document import Document as DocumentObject
from PIL import Image

import file_extraction


def build_text_pdf(pages: list[list[str]]) -> bytes:
    """Build a small deterministic PDF with extractable Helvetica text."""
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    page_ids: list[int] = []
    next_object_id = 4

    for lines in pages:
        page_id = next_object_id
        content_id = next_object_id + 1
        next_object_id += 2
        page_ids.append(page_id)

        operations = [b"BT", b"/F1 12 Tf", b"72 720 Td"]
        for index, line in enumerate(lines):
            if index:
                operations.append(b"0 -18 Td")
            escaped = (
                line.replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)")
                .encode("ascii")
            )
            operations.append(b"(" + escaped + b") Tj")
        operations.append(b"ET")
        stream = b"\n".join(operations) + b"\n"

        objects[page_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> "
            + f"/Contents {content_id} 0 R >>".encode("ascii")
        )
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"endstream"
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode(
            "ascii"
        )
    )

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (max(objects) + 1)
    for object_id in range(1, len(offsets)):
        offsets[object_id] = len(output)
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(objects[object_id])
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def build_docx(configure=None) -> bytes:
    """Build one deterministic in-memory DOCX fixture."""
    document = Document()
    if configure is not None:
        configure(document)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def build_zip(entries: dict[str, bytes]) -> bytes:
    """Build a small arbitrary ZIP for DOCX preflight tests."""
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def mark_first_central_zip_member_encrypted(content: bytes) -> bytes:
    """Set the encrypted flag in the first central-directory entry."""
    value = bytearray(content)
    offset = value.find(b"PK\x01\x02")
    if offset < 0:
        raise AssertionError("Fixture has no central-directory entry")
    flags_offset = offset + 8
    flags = int.from_bytes(value[flags_offset : flags_offset + 2], "little")
    value[flags_offset : flags_offset + 2] = (flags | 0x1).to_bytes(2, "little")
    return bytes(value)


class FileExtractionTests(unittest.TestCase):
    def test_docx_paragraphs_preserve_korean_and_mixed_language_text(self) -> None:
        def configure(document: DocumentObject) -> None:
            document.add_paragraph("첫 번째 한국어 문단입니다.")
            document.add_paragraph("Nextor AI와 RAG Server를 함께 사용합니다.")

        content = build_docx(configure)

        extracted = file_extraction.extract_document("source.DOCX", content)

        self.assertEqual(
            extracted,
            "첫 번째 한국어 문단입니다.\n\n"
            "Nextor AI와 RAG Server를 함께 사용합니다.",
        )

    def test_docx_heading_table_and_paragraph_keep_top_level_order(self) -> None:
        def configure(document: DocumentObject) -> None:
            document.add_heading("관측 결과", level=1)
            table = document.add_table(rows=3, cols=2)
            values = (("Name", "Value"), ("Temperature", "24"), ("Humidity", "55"))
            for row, row_values in zip(table.rows, values, strict=True):
                for cell, value in zip(row.cells, row_values, strict=True):
                    cell.text = value
            document.add_paragraph("표 다음 문단입니다.")

        extracted = file_extraction.extract_docx_text(build_docx(configure))

        self.assertEqual(
            extracted,
            "관측 결과\n\n"
            "Name\tValue\nTemperature\t24\nHumidity\t55\n\n"
            "표 다음 문단입니다.",
        )

    def test_whitespace_only_docx_is_rejected(self) -> None:
        content = build_docx(lambda document: document.add_paragraph(" \t "))

        with self.assertRaisesRegex(
            file_extraction.EmptyDocumentError,
            "contains no extractable text",
        ):
            file_extraction.extract_document("blank.docx", content)

    def test_image_only_docx_is_rejected_without_embedded_image_ocr(self) -> None:
        def configure(document: DocumentObject) -> None:
            image = BytesIO()
            Image.new("RGB", (2, 2), "white").save(image, format="PNG")
            image.seek(0)
            document.add_picture(image)

        with self.assertRaisesRegex(
            file_extraction.EmptyDocumentError,
            "OCR for images embedded in DOCX is not supported",
        ):
            file_extraction.extract_document("image-only.docx", build_docx(configure))

    def test_malformed_and_arbitrary_zip_docx_are_sanitized(self) -> None:
        fixtures = (b"not a ZIP", build_zip({"notes.txt": b"not a DOCX"}))

        for content in fixtures:
            with self.subTest(content=content[:12]), self.assertRaisesRegex(
                file_extraction.InvalidDocxError,
                "Uploaded DOCX could not be read",
            ) as raised:
                file_extraction.extract_document("broken.docx", content)
            self.assertNotIn("notes.txt", str(raised.exception))

    def test_encrypted_docx_member_is_rejected_without_internal_details(self) -> None:
        encrypted = mark_first_central_zip_member_encrypted(
            build_docx(lambda document: document.add_paragraph("secret"))
        )

        with self.assertRaisesRegex(
            file_extraction.InvalidDocxError,
            "Uploaded DOCX could not be read",
        ):
            file_extraction.extract_document("protected.docx", encrypted)

    def test_docx_member_count_limit_is_enforced(self) -> None:
        content = build_zip({"one": b"1", "two": b"2", "three": b"3"})

        with (
            patch.object(file_extraction, "MAX_DOCX_MEMBERS", 2),
            self.assertRaisesRegex(
                file_extraction.DocxResourceLimitError,
                "exceeds supported processing limits",
            ),
        ):
            file_extraction.validate_docx_archive(content)

    def test_docx_total_uncompressed_limit_is_enforced(self) -> None:
        content = build_docx(lambda document: document.add_paragraph("content"))

        with (
            patch.object(file_extraction, "MAX_DOCX_UNCOMPRESSED_BYTES", 10),
            self.assertRaisesRegex(
                file_extraction.DocxResourceLimitError,
                "exceeds supported processing limits",
            ),
        ):
            file_extraction.validate_docx_archive(content)

    def test_docx_single_member_limit_is_enforced(self) -> None:
        content = build_docx(lambda document: document.add_paragraph("content"))

        with (
            patch.object(file_extraction, "MAX_DOCX_MEMBER_BYTES", 10),
            self.assertRaisesRegex(
                file_extraction.DocxResourceLimitError,
                "exceeds supported processing limits",
            ),
        ):
            file_extraction.validate_docx_archive(content)

    def test_valid_utf8_txt_preserves_multiline_content(self) -> None:
        source = "첫 문단입니다.\n\n둘째 문단입니다.\n마지막 줄입니다."

        document = file_extraction.extract_document("source.TXT", source.encode())

        self.assertEqual(document, source)

    def test_valid_korean_markdown_preserves_source_structure(self) -> None:
        source = (
            "# 해양 관측 안내\n\n"
            "센서 자료를 확인합니다.\n\n"
            "- 수온 기록\n"
            "- 파고 기록\n\n"
            "## 참고\n\n"
            "**원본 Markdown 문법**을 유지합니다."
        )

        document = file_extraction.extract_document("guide.MD", source.encode())

        self.assertEqual(document, source)

    def test_empty_markdown_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            file_extraction.EmptyDocumentError, "Uploaded file is empty"
        ):
            file_extraction.extract_document("empty.md", b"")

    def test_whitespace_only_markdown_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            file_extraction.EmptyDocumentError,
            "Uploaded Markdown file contains no text",
        ):
            file_extraction.extract_document("blank.md", b" \n\t")

    def test_invalid_utf8_markdown_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            file_extraction.InvalidTextEncodingError,
            "Uploaded Markdown file is not valid UTF-8",
        ):
            file_extraction.extract_document("invalid.md", b"\xff\xfe")

    def test_text_pdf_preserves_line_and_page_order(self) -> None:
        content = build_text_pdf(
            [
                ["First page line one", "First page line two"],
                ["Second page text"],
            ]
        )

        with patch.object(file_extraction.pdf_ocr, "PdfOcrSession") as session:
            document = file_extraction.extract_document("report.PDF", content)

        self.assertEqual(
            document,
            "First page line one\nFirst page line two\n\nSecond page text",
        )
        session.assert_not_called()

    def test_scanned_pdf_uses_ocr_for_its_empty_native_page(self) -> None:
        content = build_text_pdf([[]])
        session = Mock()
        session.extract_page_text.return_value = "스캔 페이지 OCR 텍스트"

        with patch.object(
            file_extraction.pdf_ocr,
            "PdfOcrSession",
            return_value=session,
        ):
            document = file_extraction.extract_document("scan.pdf", content)

        self.assertEqual(document, "스캔 페이지 OCR 텍스트")
        session.extract_page_text.assert_called_once_with(0)
        session.close.assert_called_once_with()

    def test_mixed_pdf_preserves_page_order_without_native_ocr_duplication(
        self,
    ) -> None:
        content = build_text_pdf(
            [["First native page"], [], ["Third native page"]]
        )
        session = Mock()
        session.extract_page_text.return_value = "둘째 스캔 페이지"

        with patch.object(
            file_extraction.pdf_ocr,
            "PdfOcrSession",
            return_value=session,
        ):
            document = file_extraction.extract_document("mixed.pdf", content)

        self.assertEqual(
            document,
            "First native page\n\n둘째 스캔 페이지\n\nThird native page",
        )
        self.assertEqual(document.count("First native page"), 1)
        self.assertEqual(document.count("둘째 스캔 페이지"), 1)
        self.assertEqual(document.count("Third native page"), 1)
        session.extract_page_text.assert_called_once_with(1)

    def test_blank_ocr_pages_are_skipped_when_another_page_has_text(self) -> None:
        content = build_text_pdf([[], ["Native page"]])
        session = Mock()
        session.extract_page_text.return_value = " \n\t "

        with patch.object(
            file_extraction.pdf_ocr,
            "PdfOcrSession",
            return_value=session,
        ):
            document = file_extraction.extract_document("mixed.pdf", content)

        self.assertEqual(document, "Native page")
        session.extract_page_text.assert_called_once_with(0)

    def test_empty_txt_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            file_extraction.EmptyDocumentError, "Uploaded file is empty"
        ):
            file_extraction.extract_document("empty.txt", b"")

    def test_whitespace_only_txt_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            file_extraction.EmptyDocumentError, "contains no text"
        ):
            file_extraction.extract_document("blank.txt", b" \n\t")

    def test_invalid_utf8_txt_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            file_extraction.InvalidTextEncodingError, "not valid UTF-8"
        ):
            file_extraction.extract_document("invalid.txt", b"\xff\xfe")

    def test_pdf_without_native_or_ocr_text_is_rejected(self) -> None:
        blank_pdf = build_text_pdf([[]])
        session = Mock()
        session.extract_page_text.return_value = " \n\t "

        with (
            patch.object(
                file_extraction.pdf_ocr,
                "PdfOcrSession",
                return_value=session,
            ),
            self.assertRaisesRegex(
                file_extraction.EmptyDocumentError,
                "no extractable or OCR-recognizable text",
            ),
        ):
            file_extraction.extract_document("scan.pdf", blank_pdf)

    def test_invalid_pdf_is_rejected_without_internal_parser_details(self) -> None:
        with self.assertRaisesRegex(
            file_extraction.InvalidPdfError,
            "Uploaded PDF could not be read",
        ) as raised:
            file_extraction.extract_document("broken.pdf", b"not a PDF")

        self.assertNotIn("EOF", str(raised.exception))

    def test_legacy_doc_extension_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            file_extraction.UnsupportedFileTypeError,
            "legacy .doc is not supported",
        ):
            file_extraction.extract_document("document.doc", b"content")


if __name__ == "__main__":
    unittest.main()
