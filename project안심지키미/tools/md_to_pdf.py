#!/usr/bin/env python3
"""Convert simple Markdown notes to a Korean-capable PDF without external packages.

Usage:
    python3 tools/md_to_pdf.py /mnt/c/Windows/Fonts/malgun.ttf input.md output.pdf

The converter supports headings, paragraphs, unordered/ordered lists, inline
code marker cleanup, and simple pipe tables. It embeds the given TrueType font,
which is important for Korean text in minimal Linux/WSL environments.
"""

import os
import re
import struct
import sys
import zlib


PAGE_W = 595.28
PAGE_H = 841.89
MARGIN_L = 54
MARGIN_R = 54
MARGIN_T = 54
MARGIN_B = 54
BODY_W = PAGE_W - MARGIN_L - MARGIN_R


def u16(data, off):
    return struct.unpack_from(">H", data, off)[0]


def i16(data, off):
    return struct.unpack_from(">h", data, off)[0]


def u32(data, off):
    return struct.unpack_from(">I", data, off)[0]


class TrueTypeFont:
    def __init__(self, path):
        self.path = path
        self.data = open(path, "rb").read()
        self.tables = {}
        table_count = u16(self.data, 4)
        for i in range(table_count):
            off = 12 + i * 16
            tag = self.data[off:off + 4].decode("latin1")
            self.tables[tag] = (u32(self.data, off + 8), u32(self.data, off + 12))

        head = self.table("head")
        hhea = self.table("hhea")
        maxp = self.table("maxp")
        self.units = u16(head, 18)
        self.bbox = (i16(head, 36), i16(head, 38), i16(head, 40), i16(head, 42))
        self.ascent = i16(hhea, 4)
        self.descent = i16(hhea, 6)
        self.num_hmetrics = u16(hhea, 34)
        self.num_glyphs = u16(maxp, 4)
        self.advances = self._read_advances()
        self.cmap = self._read_cmap()

    def table(self, tag):
        off, length = self.tables[tag]
        return self.data[off:off + length]

    def _read_advances(self):
        hmtx = self.table("hmtx")
        advances = []
        last = 0
        for i in range(self.num_hmetrics):
            last = u16(hmtx, i * 4)
            advances.append(last)
        while len(advances) < self.num_glyphs:
            advances.append(last)
        return advances

    def _read_cmap(self):
        cmap = self.table("cmap")
        records = []
        count = u16(cmap, 2)
        for i in range(count):
            off = 4 + i * 8
            platform = u16(cmap, off)
            encoding = u16(cmap, off + 2)
            suboff = u32(cmap, off + 4)
            fmt = u16(cmap, suboff)
            records.append((fmt, platform, encoding, suboff))

        preferred = [(12, 3, 10), (12, 0, 4), (4, 3, 1), (4, 3, 10), (4, 0, 3)]
        for wanted in preferred:
            for fmt, platform, encoding, suboff in records:
                if (fmt, platform, encoding) == wanted:
                    return self._parse_cmap_format(cmap, suboff, fmt)

        fmt, _platform, _encoding, suboff = records[0]
        return self._parse_cmap_format(cmap, suboff, fmt)

    def _parse_cmap_format(self, cmap, off, fmt):
        result = {}
        if fmt == 12:
            group_count = u32(cmap, off + 12)
            pos = off + 16
            for _ in range(group_count):
                start = u32(cmap, pos)
                end = u32(cmap, pos + 4)
                start_gid = u32(cmap, pos + 8)
                for cp in range(start, end + 1):
                    gid = start_gid + cp - start
                    if gid < self.num_glyphs:
                        result[cp] = gid
                pos += 12
            return result

        if fmt == 4:
            seg_count = u16(cmap, off + 6) // 2
            end_codes = off + 14
            start_codes = end_codes + 2 * seg_count + 2
            id_deltas = start_codes + 2 * seg_count
            id_range_offsets = id_deltas + 2 * seg_count
            for i in range(seg_count):
                end = u16(cmap, end_codes + 2 * i)
                start = u16(cmap, start_codes + 2 * i)
                delta = i16(cmap, id_deltas + 2 * i)
                range_offset = u16(cmap, id_range_offsets + 2 * i)
                if start == 0xFFFF and end == 0xFFFF:
                    continue
                for cp in range(start, end + 1):
                    if range_offset == 0:
                        gid = (cp + delta) & 0xFFFF
                    else:
                        glyph_off = id_range_offsets + 2 * i + range_offset + 2 * (cp - start)
                        if glyph_off + 2 > len(cmap):
                            continue
                        raw = u16(cmap, glyph_off)
                        gid = 0 if raw == 0 else (raw + delta) & 0xFFFF
                    if gid:
                        result[cp] = gid
            return result

        raise RuntimeError(f"Unsupported cmap format: {fmt}")

    def glyph(self, ch):
        return self.cmap.get(ord(ch), 0)

    def width1000(self, gid):
        if gid < len(self.advances):
            return int(round(self.advances[gid] * 1000 / self.units))
        return 500

    def text_width(self, text, size):
        total = 0
        for ch in text:
            if ch == "\t":
                total += self.width1000(self.glyph(" ")) * 4
            else:
                total += self.width1000(self.glyph(ch))
        return total * size / 1000

    def metric1000(self, value):
        return int(round(value * 1000 / self.units))


def clean_inline(text):
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    return text.strip()


def split_table_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [clean_inline(cell.strip()) for cell in line.split("|")]


def is_table_sep(line):
    cells = split_table_row(line)
    return bool(cells) and all(re.match(r"^:?-{3,}:?$", cell or "") for cell in cells)


def wrap_text(text, max_w, size, font):
    text = clean_inline(text).replace("\u00a0", " ")
    if not text:
        return [""]

    tokens = re.findall(r"\S+\s*", text)
    lines = []
    current = ""
    for token in tokens:
        candidate = current + token
        if current and font.text_width(candidate.rstrip(), size) > max_w:
            lines.append(current.rstrip())
            current = token
            while font.text_width(current.rstrip(), size) > max_w and len(current.strip()) > 1:
                bare = current.rstrip()
                part = ""
                rest = ""
                for idx, ch in enumerate(bare):
                    if font.text_width(part + ch, size) <= max_w or not part:
                        part += ch
                    else:
                        rest = bare[idx:]
                        break
                lines.append(part)
                current = rest
        else:
            current = candidate

    if current.strip():
        lines.append(current.rstrip())
    return lines or [""]


class PdfBuilder:
    def __init__(self, font):
        self.font = font
        self.pages = []
        self.ops = []
        self.y = PAGE_H - MARGIN_T
        self.used = set()

    def ensure(self, height):
        if self.y - height < MARGIN_B:
            self.new_page()

    def new_page(self):
        if self.ops:
            self.pages.append("\n".join(self.ops).encode("latin1"))
        self.ops = []
        self.y = PAGE_H - MARGIN_T

    def finish_pages(self):
        if self.ops:
            self.pages.append("\n".join(self.ops).encode("latin1"))
            self.ops = []
        if not self.pages:
            self.pages.append(b"")

    def text_op(self, x, y, text, size, color=(0, 0, 0)):
        if not text:
            return
        gids = []
        for ch in text:
            gid = self.font.glyph(ch)
            gids.append(gid)
            if gid:
                self.used.add((gid, ord(ch)))
        hex_text = "".join(f"{gid:04X}" for gid in gids)
        r, g, b = color
        self.ops.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
        self.ops.append(f"BT /F1 {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm <{hex_text}> Tj ET")

    def line(self, x1, y1, x2, y2, gray=0.7, width=0.5):
        self.ops.append(f"{gray:.3f} {gray:.3f} {gray:.3f} RG {width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def rect_fill(self, x, y, w, h, gray=0.94):
        self.ops.append(f"{gray:.3f} {gray:.3f} {gray:.3f} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def paragraph(self, text, size=10.6, indent=0, gap_after=7, color=(0.08, 0.08, 0.08)):
        lines = wrap_text(text, BODY_W - indent, size, self.font)
        line_height = size * 1.42
        self.ensure(len(lines) * line_height + gap_after)
        for line in lines:
            self.text_op(MARGIN_L + indent, self.y - size, line, size, color)
            self.y -= line_height
        self.y -= gap_after

    def list_item(self, marker, text, ordered=False):
        size = 10.4
        line_height = size * 1.42
        marker_w = 28 if ordered else 22
        lines = wrap_text(text, BODY_W - marker_w, size, self.font)
        self.ensure(len(lines) * line_height + 3)
        self.text_op(MARGIN_L, self.y - size, marker, size, (0.08, 0.08, 0.08))
        self.text_op(MARGIN_L + marker_w, self.y - size, lines[0], size, (0.08, 0.08, 0.08))
        self.y -= line_height
        for line in lines[1:]:
            self.text_op(MARGIN_L + marker_w, self.y - size, line, size, (0.08, 0.08, 0.08))
            self.y -= line_height
        self.y -= 3

    def heading(self, level, text):
        sizes = {1: 21, 2: 15.5, 3: 12.5}
        gaps_before = {1: 0, 2: 15, 3: 10}
        gaps_after = {1: 18, 2: 9, 3: 7}
        size = sizes.get(level, 11.5)
        before = gaps_before.get(level, 8)
        after = gaps_after.get(level, 6)
        self.ensure(before + size * 1.5 + after)
        self.y -= before
        lines = wrap_text(text, BODY_W, size, self.font)
        for line in lines:
            self.text_op(MARGIN_L, self.y - size, line, size, (0.02, 0.12, 0.22))
            self.y -= size * 1.35
        if level <= 2:
            self.line(MARGIN_L, self.y + 3, PAGE_W - MARGIN_R, self.y + 3, gray=0.82, width=0.6)
        self.y -= after

    def table(self, rows):
        if not rows:
            return
        cols = max(len(row) for row in rows)
        for row in rows:
            while len(row) < cols:
                row.append("")

        size = 9.0
        pad_x = 5
        pad_y = 5
        raw_widths = []
        for col in range(cols):
            raw_widths.append(max([self.font.text_width(row[col], size) for row in rows] + [35]))

        total = sum(raw_widths)
        widths = [BODY_W / cols] * cols if total <= 0 else [max(58, BODY_W * w / total) for w in raw_widths]
        scale = BODY_W / sum(widths)
        widths = [w * scale for w in widths]

        self.ensure(26)
        for row_idx, row in enumerate(rows):
            wrapped = [wrap_text(row[col], max(10, widths[col] - 2 * pad_x), size, self.font) for col in range(cols)]
            row_h = max(len(lines) for lines in wrapped) * size * 1.35 + 2 * pad_y
            self.ensure(row_h + 2)
            y0 = self.y - row_h
            if row_idx == 0:
                self.rect_fill(MARGIN_L, y0, BODY_W, row_h, gray=0.93)
            self.line(MARGIN_L, self.y, MARGIN_L + BODY_W, self.y, gray=0.76)

            x = MARGIN_L
            for col in range(cols + 1):
                xx = MARGIN_L + sum(widths[:col])
                self.line(xx, self.y, xx, y0, gray=0.82)

            for col, lines in enumerate(wrapped):
                tx = x + pad_x
                ty = self.y - pad_y - size
                for line in lines:
                    self.text_op(tx, ty, line, size, (0.06, 0.06, 0.06))
                    ty -= size * 1.35
                x += widths[col]

            self.line(MARGIN_L, y0, MARGIN_L + BODY_W, y0, gray=0.76)
            self.y = y0
        self.y -= 10

    def write_pdf(self, output):
        self.finish_pages()
        objects = []

        def stream(data, extra=""):
            compressed = zlib.compress(data)
            return f"<< /Length {len(compressed)} /Filter /FlateDecode {extra} >>\nstream\n".encode("latin1") + compressed + b"\nendstream"

        used_gids = sorted({gid for gid, _cp in self.used if gid})
        gid_to_unicode = {}
        for gid, cp in sorted(self.used):
            gid_to_unicode.setdefault(gid, cp)

        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        page_obj_ids = []
        content_obj_ids = []
        next_id = 3
        for _content in self.pages:
            page_obj_ids.append(next_id)
            content_obj_ids.append(next_id + 1)
            next_id += 2

        font_obj = next_id
        cidfont_obj = next_id + 1
        descriptor_obj = next_id + 2
        fontfile_obj = next_id + 3
        tounicode_obj = next_id + 4

        kids = " ".join(f"{page_id} 0 R" for page_id in page_obj_ids)
        objects.append(f"<< /Type /Pages /Count {len(page_obj_ids)} /Kids [{kids}] >>".encode("latin1"))

        for idx, (page_id, content_id) in enumerate(zip(page_obj_ids, content_obj_ids)):
            page = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
                f"/Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content_id} 0 R >>"
            )
            objects.append(page.encode("latin1"))
            objects.append(stream(self.pages[idx]))

        font_name = "MalgunGothic"
        objects.append(
            f"<< /Type /Font /Subtype /Type0 /BaseFont /{font_name} /Encoding /Identity-H "
            f"/DescendantFonts [{cidfont_obj} 0 R] /ToUnicode {tounicode_obj} 0 R >>".encode("latin1")
        )

        widths_parts = []
        i = 0
        while i < len(used_gids):
            start = used_gids[i]
            vals = [self.font.width1000(start)]
            j = i + 1
            while j < len(used_gids) and used_gids[j] == used_gids[j - 1] + 1:
                vals.append(self.font.width1000(used_gids[j]))
                j += 1
            widths_parts.append(f"{start} [{' '.join(str(v) for v in vals)}]")
            i = j

        objects.append(
            f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{font_name} "
            f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
            f"/FontDescriptor {descriptor_obj} 0 R /CIDToGIDMap /Identity /DW 500 "
            f"/W [{' '.join(widths_parts)}] >>".encode("latin1")
        )

        x_min, y_min, x_max, y_max = [self.font.metric1000(v) for v in self.font.bbox]
        ascent = self.font.metric1000(self.font.ascent)
        descent = self.font.metric1000(self.font.descent)
        objects.append(
            f"<< /Type /FontDescriptor /FontName /{font_name} /Flags 32 "
            f"/FontBBox [{x_min} {y_min} {x_max} {y_max}] /ItalicAngle 0 "
            f"/Ascent {ascent} /Descent {descent} /CapHeight {ascent} /StemV 80 "
            f"/FontFile2 {fontfile_obj} 0 R >>".encode("latin1")
        )
        objects.append(stream(self.font.data, f"/Length1 {len(self.font.data)}"))

        cmap_lines = [
            "/CIDInit /ProcSet findresource begin",
            "12 dict begin",
            "begincmap",
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
            "/CMapName /Adobe-Identity-UCS def",
            "/CMapType 2 def",
            "1 begincodespacerange",
            "<0000> <FFFF>",
            "endcodespacerange",
        ]
        items = sorted(gid_to_unicode.items())
        for start in range(0, len(items), 100):
            chunk = items[start:start + 100]
            cmap_lines.append(f"{len(chunk)} beginbfchar")
            for gid, cp in chunk:
                uni = chr(cp).encode("utf-16-be").hex().upper()
                cmap_lines.append(f"<{gid:04X}> <{uni}>")
            cmap_lines.append("endbfchar")
        cmap_lines += [
            "endcmap",
            "CMapName currentdict /CMap defineresource pop",
            "end",
            "end",
        ]
        objects.append(stream(("\n".join(cmap_lines) + "\n").encode("latin1")))

        out = bytearray(b"%PDF-1.7\n%\xE2\xE3\xCF\xD3\n")
        offsets = [0]
        for idx, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out.extend(f"{idx} 0 obj\n".encode("latin1"))
            out.extend(obj)
            out.extend(b"\nendobj\n")

        xref = len(out)
        out.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin1"))
        out.extend(b"0000000000 65535 f \n")
        for off in offsets[1:]:
            out.extend(f"{off:010d} 00000 n \n".encode("latin1"))
        out.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin1")
        )

        with open(output, "wb") as f:
            f.write(out)


def parse_markdown(md_path, pdf):
    lines = open(md_path, encoding="utf-8").read().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            pdf.y -= 5
            i += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            pdf.heading(len(heading_match.group(1)), clean_inline(heading_match.group(2)))
            i += 1
            continue

        if "|" in line and i + 1 < len(lines) and is_table_sep(lines[i + 1]):
            rows = [split_table_row(line)]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(split_table_row(lines[i]))
                i += 1
            pdf.table(rows)
            continue

        bullet_match = re.match(r"^\s*-\s+(.*)$", line)
        if bullet_match:
            pdf.list_item("•", clean_inline(bullet_match.group(1)))
            i += 1
            continue

        ordered_match = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if ordered_match:
            pdf.list_item(f"{ordered_match.group(1)}.", clean_inline(ordered_match.group(2)), ordered=True)
            i += 1
            continue

        para = [line.strip()]
        i += 1
        while i < len(lines):
            next_line = lines[i].rstrip()
            if not next_line.strip():
                break
            if re.match(r"^(#{1,6})\s+", next_line) or re.match(r"^\s*(-|\d+\.)\s+", next_line):
                break
            if "|" in next_line and i + 1 < len(lines) and is_table_sep(lines[i + 1]):
                break
            para.append(next_line.strip())
            i += 1
        pdf.paragraph(" ".join(para))


def main():
    if len(sys.argv) != 4:
        print("usage: md_to_pdf.py FONT.ttf input.md output.pdf", file=sys.stderr)
        return 2

    font_path, md_path, out_path = sys.argv[1:]
    font = TrueTypeFont(font_path)
    pdf = PdfBuilder(font)
    parse_markdown(md_path, pdf)
    pdf.write_pdf(out_path)
    print(f"wrote {out_path} ({os.path.getsize(out_path)} bytes, {len(pdf.pages)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
