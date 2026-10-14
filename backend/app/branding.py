"""codencode.my wordmark for exported workbooks: "codencode" in black, ".my" in mint."""

from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.worksheet.worksheet import Worksheet

MINT = "FF00DCB4"
BLACK = "FF000000"


def wordmark() -> CellRichText:
    return CellRichText(
        TextBlock(InlineFont(rFont="Calibri", sz=11, b=True, color=BLACK), "codencode"),
        TextBlock(InlineFont(rFont="Calibri", sz=11, b=True, color=MINT), ".my"),
    )


def stamp_wordmark(ws: Worksheet, cell: str = "A2") -> None:
    ws[cell] = wordmark()
