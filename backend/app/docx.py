"""Минимальная запись документов Word (.docx) без сторонних библиотек.

.docx — это zip с XML (ECMA-376). Нужны абзацы, заголовки, жирный текст, ссылки и простые таблицы — этого
достаточно для обоснования и сводного отчёта, а новая зависимость (и пересборка образа) не требуется.
"""
import io
import zipfile
from xml.sax.saxutils import escape, quoteattr

FONT = "Times New Roman"
W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
HEADING_SIZE = {1: 32, 2: 26}  # в полупунктах: 16 и 13 пт
PAGE_WIDTH = 9638  # ширина текста на A4 при полях 2 см, в двадцатых долях пункта

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W_NS}>
<w:docDefaults>
<w:rPrDefault><w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}" w:eastAsia="{FONT}"/><w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="ru-RU"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="160"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="{HEADING_SIZE[1]}"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="{HEADING_SIZE[2]}"/></w:rPr></w:style>
</w:styles>"""
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
LINK_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"

# Часть абзаца: строка или (строка, {"bold": True, "url": "https://…"})
Run = str | tuple[str, dict]


def _text(value: str) -> str:
    """Текст для XML: управляющие символы, недопустимые в XML 1.0, убираются (Word такой файл не откроет)."""
    clean = "".join(ch for ch in str(value) if ch in "\t\n" or ord(ch) >= 32)
    return escape(clean)


class Document:
    def __init__(self) -> None:
        self._body: list[str] = []
        self._links: list[str] = []

    def _run(self, run: Run, size: int | None = None) -> str:
        text, opts = (run, {}) if isinstance(run, str) else run
        url = opts.get("url")
        # порядок элементов в rPr задан схемой: b, color, sz, u
        props = (("<w:b/>" if opts.get("bold") else "") + ('<w:color w:val="0563C1"/>' if url else "")
                 + (f'<w:sz w:val="{size}"/>' if size else "") + ('<w:u w:val="single"/>' if url else ""))
        # перенос строки внутри текста — разрыв строки в том же абзаце
        pieces = "<w:br/>".join(f'<w:t xml:space="preserve">{_text(part)}</w:t>' for part in text.split("\n"))
        xml = f"<w:r>{f'<w:rPr>{props}</w:rPr>' if props else ''}{pieces}</w:r>"
        if url:
            self._links.append(url)
            xml = f'<w:hyperlink r:id="rLink{len(self._links)}" w:history="1">{xml}</w:hyperlink>'
        return xml

    def _para(self, runs: list[Run], style: str = "", size: int | None = None, align: str = "") -> str:
        props = (f'<w:pStyle w:val="{style}"/>' if style else "") + (f'<w:jc w:val="{align}"/>' if align else "")
        return f"<w:p>{f'<w:pPr>{props}</w:pPr>' if props else ''}{''.join(self._run(r, size) for r in runs)}</w:p>"

    def heading(self, text: str, level: int = 1) -> None:
        self._body.append(self._para([text], style=f"Heading{level}"))

    def para(self, *runs: Run, align: str = "") -> None:
        self._body.append(self._para(list(runs), align=align))

    def field(self, label: str, value: str, url: str = "") -> None:
        """Абзац вида «Подпись: значение» с жирной подписью."""
        self.para((f"{label}: ", {"bold": True}), (value, {"url": url}) if url else value)

    def table(self, rows: list[list[Run]], widths: list[int], header: bool = True) -> None:
        """Таблица с рамками. widths — доли ширины колонок (любые числа), первая строка — шапка."""
        total = sum(widths)
        cols = [round(PAGE_WIDTH * w / total) for w in widths]
        border = "".join(f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
                         for side in ("top", "left", "bottom", "right", "insideH", "insideV"))
        xml = [f'<w:tbl><w:tblPr><w:tblW w:w="{PAGE_WIDTH}" w:type="dxa"/><w:tblBorders>{border}</w:tblBorders>'
               '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/>'
               '</w:tblCellMar></w:tblPr><w:tblGrid>' + "".join(f'<w:gridCol w:w="{c}"/>' for c in cols) + "</w:tblGrid>"]
        for i, row in enumerate(rows):
            head = header and i == 0
            cells = []
            for cell, width in zip(row, cols):
                run: Run = (cell, {"bold": True}) if head and isinstance(cell, str) else cell
                shade = '<w:shd w:val="clear" w:color="auto" w:fill="E7E6E6"/>' if head else ""
                cells.append(f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shade}</w:tcPr>'
                             f"{self._para([run], size=20)}</w:tc>")
            xml.append(f"<w:tr>{'<w:trPr><w:tblHeader/></w:trPr>' if head else ''}{''.join(cells)}</w:tr>")
        xml.append("</w:tbl>")
        self._body.append("".join(xml))
        self._body.append("<w:p/>")  # Word требует абзац после таблицы

    def page_break(self) -> None:
        self._body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def to_bytes(self) -> bytes:
        document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>'
                    + "".join(self._body)
                    + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                      '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>'
                      "</w:sectPr></w:body></w:document>")
        rels = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{RELS_NS}">'
                '<Relationship Id="rStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                + "".join(f'<Relationship Id="rLink{i}" Type="{LINK_TYPE}" Target={quoteattr(url)} TargetMode="External"/>'
                          for i, url in enumerate(self._links, 1))
                + "</Relationships>")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", ROOT_RELS)
            z.writestr("word/document.xml", document)
            z.writestr("word/styles.xml", STYLES)
            z.writestr("word/_rels/document.xml.rels", rels)
        return buf.getvalue()
