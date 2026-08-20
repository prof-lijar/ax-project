from __future__ import annotations

import unittest

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


class FileExtractionTests(unittest.TestCase):
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

        document = file_extraction.extract_document("report.PDF", content)

        self.assertEqual(
            document,
            "First page line one\nFirst page line two\n\nSecond page text",
        )

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

    def test_pdf_without_extractable_text_is_rejected_without_ocr(self) -> None:
        blank_pdf = build_text_pdf([[]])

        with self.assertRaisesRegex(
            file_extraction.EmptyDocumentError,
            "scanned/image-only PDFs are not supported",
        ):
            file_extraction.extract_document("scan.pdf", blank_pdf)

    def test_unsupported_extension_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            file_extraction.UnsupportedFileTypeError,
            "Only UTF-8 .txt/.md and text-based .pdf files are supported",
        ):
            file_extraction.extract_document("document.docx", b"content")


if __name__ == "__main__":
    unittest.main()
