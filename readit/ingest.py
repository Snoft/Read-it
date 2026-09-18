"""Turn a deck into pages of text, with images for the pages that have none.

Done for you. The one design decision worth knowing: a page whose text layer is
almost empty is a graphic, so it is rasterised and sent to the model as an image
instead. Most pitch decks are 60-80% graphics.
"""
from dataclasses import dataclass, field
from pathlib import Path
import base64
import io
import logging

# pdfminer logs a warning per malformed font PER PAGE. Real decks are full of
# odd embedded fonts, so one 30-page file can print hundreds of identical lines
# and bury the output. None of it matters here: a page whose text layer is
# broken is exactly a page we send to the model as an image anyway.
logging.getLogger("pdfminer").setLevel(logging.ERROR)

TEXT_THRESHOLD = 80  # chars; below this a page is treated as a graphic


@dataclass
class Page:
    number: int
    text: str = ""
    image_b64: str | None = None

    @property
    def is_graphic(self) -> bool:
        return len(self.text.strip()) < TEXT_THRESHOLD


@dataclass
class Deck:
    path: Path
    pages: list[Page] = field(default_factory=list)

    def page_text(self, n: int) -> str:
        for p in self.pages:
            if p.number == n:
                return p.text
        return ""

    @property
    def all_text(self) -> str:
        return "\n\n".join(f"[page {p.number}]\n{p.text}" for p in self.pages)


def load(path: str | Path, rasterise_dpi: int = 110) -> Deck:
    import pdfplumber
    import pypdfium2 as pdfium

    path = Path(path)
    deck = Deck(path=path)

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            deck.pages.append(Page(number=i, text=page.extract_text() or ""))

    graphics = [p.number for p in deck.pages if p.is_graphic]
    if graphics:
        doc = pdfium.PdfDocument(str(path))
        scale = rasterise_dpi / 72
        for n in graphics:
            bitmap = doc[n - 1].render(scale=scale)
            buf = io.BytesIO()
            bitmap.to_pil().save(buf, format="PNG")
            deck.pages[n - 1].image_b64 = base64.b64encode(buf.getvalue()).decode()
        doc.close()

    return deck
