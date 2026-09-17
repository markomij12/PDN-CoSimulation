#!/usr/bin/env python3
"""Generate the one-page PDN Design Tool portfolio write-up PDF."""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parent / "PDN_Design_Tool.pdf"
CHARTER = "/System/Library/Fonts/Supplemental/Charter.ttc"
HELVETICA_NEUE = "/System/Library/Fonts/HelveticaNeue.ttc"

INK = HexColor("#1a1a1a")
MUTED = HexColor("#4a4a4a")
RULE = HexColor("#2c2c2c")
BOX_FILL = HexColor("#f3f2ee")
BOX_EDGE = HexColor("#6a6a6a")

SUMMARY = (
    "The PDN Design Tool is a Python pipeline that takes a KiCad PCB layout and "
    "produces a cost-constrained decoupling-capacitor bill of materials and an "
    "impedance profile for hardware engineers designing PCB power rails."
)

PROBLEM = (
    "Manually selecting decoupling capacitors for a PCB power rail is slow. "
    "The usual method relies on datasheet approximations: a target-impedance "
    "formula, capacitor self-resonant frequencies, and a few standard values "
    "(100 nF, 1 µF, 22 µF). Those approximations do not use real board geometry. "
    "Plane area, dielectric thickness, via locations, and spreading inductance "
    "are left out. The resulting BOM looks correct on paper and then misses its "
    "impedance target on the layout."
)

HOW = (
    "The pipeline takes a KiCad .kicad_pcb file as input and parses the layout "
    "as text (no pcbnew). It extracts the power/ground plane cavity from the "
    "stackup and models that cavity as lumped plane capacitance plus via "
    "spreading inductance from the IC power pin to each VCC via. Capacitor "
    "selection searches a discrete catalog of real Murata MLCCs. Each part uses "
    "datasheet ESR and ESL values, not an ideal capacitor. A cost constraint "
    "bounds the search. Selected parts are assigned to VCC vias. Output is a "
    "decoupling-capacitor bill of materials and an impedance profile."
)

VALIDATION = (
    "The lumped model was cross-checked against a full-wave openEMS (FDTD) "
    "electromagnetic simulation of the same geometry. The capacitor selection "
    "was separately verified with a 2-port ngspice circuit simulation driven by "
    "extracted S-parameters. openEMS is a validator, not part of the inner "
    "search. A 100 kHz to 1 GHz PDN sweep is a poor FDTD problem, so the "
    "optimizer uses the lumped cavity."
)

WHY = (
    "This workflow connects lumped-element modeling, full-wave EM simulation, "
    "and real component selection in one automated pipeline. That is the same "
    "sequence commercial SI/PI tools run. Here it is rebuilt with KiCad, "
    "openEMS, ngspice, and Python. What I learned is that the lumped cavity, "
    "the EM check, and the real MLCC parasitics have to stay in one loop. Drop "
    "any of the three and the BOM is a guess again."
)

GITHUB = "GitHub: github.com/markomij12"


class FigurePlaceholder(Flowable):
    def __init__(self, width: float, height: float) -> None:
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return (self.width, self.height)

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(BOX_FILL)
        c.setStrokeColor(BOX_EDGE)
        c.setLineWidth(0.7)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=1)
        label = "[insert impedance profile plot here]"
        c.setFillColor(MUTED)
        c.setFont("Charter-Italic", 10)
        tw = c.stringWidth(label, "Charter-Italic", 10)
        c.drawString((self.width - tw) / 2.0, self.height / 2.0 - 3.5, label)


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("Charter", CHARTER, subfontIndex=0))
    pdfmetrics.registerFont(TTFont("Charter-Italic", CHARTER, subfontIndex=1))
    pdfmetrics.registerFont(TTFont("Charter-Bold", CHARTER, subfontIndex=3))
    pdfmetrics.registerFont(TTFont("HelveticaNeue", HELVETICA_NEUE, subfontIndex=0))
    pdfmetrics.registerFont(TTFont("HelveticaNeue-Medium", HELVETICA_NEUE, subfontIndex=10))
    pdfmetrics.registerFontFamily(
        "Charter",
        normal="Charter",
        bold="Charter-Bold",
        italic="Charter-Italic",
        boldItalic="Charter-Italic",
    )


def word_count(*parts: str) -> int:
    text = " ".join(parts)
    return len(re.findall(r"[A-Za-z0-9µ]+(?:['’][A-Za-z]+)?", text))


def assert_no_em_dash(*parts: str) -> None:
    blob = "\n".join(parts)
    if "\u2014" in blob or "---" in blob:
        raise SystemExit("em dash found in copy")


def styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title",
            fontName="HelveticaNeue-Medium",
            fontSize=17,
            leading=20,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "summary": ParagraphStyle(
            "summary",
            fontName="Charter",
            fontSize=10.5,
            leading=14.6,
            textColor=INK,
            alignment=TA_LEFT,
            spaceBefore=11,
            spaceAfter=2,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="HelveticaNeue-Medium",
            fontSize=9,
            leading=12,
            textColor=INK,
            alignment=TA_LEFT,
            spaceBefore=13,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Charter",
            fontSize=10,
            leading=13.8,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "github": ParagraphStyle(
            "github",
            fontName="HelveticaNeue",
            fontSize=8,
            leading=10,
            textColor=MUTED,
            alignment=TA_LEFT,
            spaceBefore=18,
        ),
    }


class TitleRule(Flowable):
    def __init__(self, width: float) -> None:
        super().__init__()
        self.width = width
        self.height = 8

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return (self.width, self.height)

    def draw(self) -> None:
        self.canv.setStrokeColor(RULE)
        self.canv.setLineWidth(0.6)
        self.canv.line(0, 2, self.width, 2)


def build() -> None:
    register_fonts()
    assert_no_em_dash(SUMMARY, PROBLEM, HOW, VALIDATION, WHY, GITHUB)
    n = word_count(SUMMARY, PROBLEM, HOW, VALIDATION, WHY)
    if not (300 <= n <= 400):
        raise SystemExit(f"body word count {n} is outside 300-400")

    pages: list[int] = []

    def on_page(canvas, doc) -> None:
        pages.append(doc.page)
        canvas.saveState()
        canvas.restoreState()

    margin = 0.88 * inch
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=0.82 * inch,
        bottomMargin=0.75 * inch,
        title="PDN Design Tool",
        author="Marko Mijatovic",
        subject="Technical write-up",
    )
    s = styles()
    story: list = [
        Paragraph("PDN Design Tool", s["title"]),
        TitleRule(doc.width),
        Paragraph(SUMMARY, s["summary"]),
        Paragraph("The problem", s["h2"]),
        Paragraph(PROBLEM, s["body"]),
        Paragraph("How it works", s["h2"]),
        Paragraph(HOW, s["body"]),
        Spacer(1, 12),
        FigurePlaceholder(doc.width, 1.92 * inch),
        Spacer(1, 4),
        Paragraph("Validation", s["h2"]),
        Paragraph(VALIDATION, s["body"]),
        Paragraph("Why it matters", s["h2"]),
        Paragraph(WHY, s["body"]),
        Paragraph(GITHUB, s["github"]),
    ]
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    if len(pages) != 1:
        raise SystemExit(f"expected 1 page, got {len(pages)}")
    print(f"wrote {OUT} ({n} words, {len(pages)} page)")


if __name__ == "__main__":
    build()
