"""Small genuine documents for local preview integration checks."""
from io import BytesIO
from zipfile import ZipFile

from docx import Document
from PIL import Image
from pypdf import PdfWriter


def preview_files():
    image = BytesIO()
    Image.new('RGB', (640, 360), '#d9e9f7').save(image, format='PNG')
    document = BytesIO()
    word = Document()
    word.add_heading('Project brief', 0)
    word.add_paragraph('Read-only Word preview integration check.')
    word.save(document)
    pdf = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    writer.write(pdf)
    excel = BytesIO()
    with ZipFile(excel, 'w') as archive:
        archive.writestr('[Content_Types].xml', '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>''')
        archive.writestr('_rels/.rels', '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        archive.writestr('xl/workbook.xml', '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Budget" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        archive.writestr('xl/_rels/workbook.xml.rels', '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''')
        archive.writestr('xl/worksheets/sheet1.xml', '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Budget</t></is></c><c r="B1"><v>123</v></c></row></sheetData></worksheet>''')
    return [('Preview image.png', image.getvalue(), 'image/png'),
            ('Preview document.docx', document.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
            ('Preview budget.xlsx', excel.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Preview document.pdf', pdf.getvalue(), 'application/pdf')]
