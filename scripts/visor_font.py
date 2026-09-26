"""Turns text into SVG paths so every visual renders the same on any device."""
from pathlib import Path
from xml.sax.saxutils import escape
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Palette
BASE, PANEL, EDGE = "#05070E", "#0B1120", "#1B2540"
RED, CYAN, STEEL, WHITE = "#FF2D46", "#5CE1FF", "#7A86A3", "#EEF2FA"


def _n(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


class Font:
    def __init__(self, name):
        self.f = TTFont(FONTS / name)
        self.gs = self.f.getGlyphSet()
        self.cmap = self.f.getBestCmap()
        self.upm = self.f["head"].unitsPerEm
        self.hmtx = self.f["hmtx"]

    def _g(self, ch):
        return self.cmap.get(ord(ch)) or self.cmap.get(ord("?"))

    def width(self, text, size, ls=0):
        if not text:
            return 0
        return sum(self.hmtx[self._g(c)][0] * size / self.upm + ls for c in text) - ls

    def d(self, text, size, x, y, anchor="start", ls=0):
        w = self.width(text, size, ls)
        x -= w / 2 if anchor == "middle" else w if anchor == "end" else 0
        sc, out = size / self.upm, []
        for ch in text:
            g = self._g(ch)
            pen = SVGPathPen(self.gs, ntos=_n)
            self.gs[g].draw(TransformPen(pen, (sc, 0, 0, -sc, x, y)))
            cmd = pen.getCommands()
            if cmd:
                out.append(cmd)
            x += self.hmtx[g][0] * sc + ls
        return " ".join(out)

    def text(self, text, size, x, y, fill, anchor="start", ls=0, extra=""):
        return f'<path d="{self.d(text, size, x, y, anchor, ls)}" fill="{fill}" {extra}/>'


def svg(w, h, body, style="", title=""):
    t = f"<title>{escape(title)}</title>" if title else ""
    rm = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f"{t}<style>{style}{rm}</style>{body}</svg>")
