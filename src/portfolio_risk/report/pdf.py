"""PDF export with reportlab: vector charts and tables on A4, light paper style.

The report is meant to be printed or attached to an email, so it uses a white page with one
accent colour rather than the dark interface theme. The person chooses which sections to
include; sections whose material does not exist (for example no simulation has been run) are
left out and never fabricated.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from xml.sax.saxutils import escape

from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from portfolio_risk.analysis import AnalysisResult
from portfolio_risk.report.inputs import ReportInputs, resolve
from portfolio_risk.report.look import look, make_look, use
from portfolio_risk.report.meta import ReportMeta
from portfolio_risk.report.pdf_parts import MARGIN, PAGE_H, PAGE_W, make_styles
from portfolio_risk.report.pdf_sections import BUILDERS, Context
from portfolio_risk.report.style import ReportStyle
from portfolio_risk.ui import formatting


def _footer(meta: ReportMeta):  # type: ignore[no-untyped-def]
    def draw(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setFillColor(look().paper)  # the page tone, drawn before the content
        canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canvas.setFont(look().font, 7)
        canvas.setFillColor(look().muted)
        canvas.drawString(
            MARGIN, 10 * mm, f"Portfolio Risk Lab {meta.version}  |  not investment advice"
        )
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def build_pdf(
    result: AnalysisResult,
    meta: ReportMeta | None = None,
    inputs: ReportInputs | None = None,
    sections: Iterable[str] | None = None,
    style: ReportStyle | None = None,
) -> bytes:
    """Return the report as PDF bytes.

    ``sections`` lists the section keys to include (see :data:`report.inputs.SECTIONS`);
    ``None`` means every section that has the material it needs. ``style`` sets colours, line
    weights, paper tone and font; ``None`` is the Classic style following ``meta.accent``.
    """
    meta = meta or ReportMeta()
    inputs = inputs or ReportInputs()
    chosen = resolve(sections, result, inputs)
    with use(make_look(style or ReportStyle(), meta.accent)) as active:
        return _render(result, meta, inputs, chosen, active.accent)


def _render(
    result: AnalysisResult,
    meta: ReportMeta,
    inputs: ReportInputs,
    chosen: list[str],
    accent: Color,
) -> bytes:
    context = Context(result, meta, inputs, accent, make_styles(accent))
    st = context.styles
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=meta.title,
        author=f"Portfolio Risk Lab {meta.version}",
    )
    story: list[object] = [
        Paragraph(escape(meta.title), st["title"]),
        Spacer(1, 3),
        Paragraph(
            escape(
                f"{formatting.day(result.start)} to {formatting.day(result.end)}  |  "
                f"{result.observations} observations  |  "
                f"{result.config.periods_per_year} periods per year  |  "
                f"{meta.source_note}"
            ),
            st["sub"],
        ),
        Paragraph(escape(f"Generated {meta.generated:%Y-%m-%d %H:%M} UTC"), st["sub"]),
        Spacer(1, 8),
    ]
    for key in chosen:
        story += BUILDERS[key](context)
    footer = _footer(meta)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
