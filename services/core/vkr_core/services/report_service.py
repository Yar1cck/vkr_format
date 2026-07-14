from __future__ import annotations

import difflib
import tempfile
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from services.core.vkr_core.engine.violation_labels import violation_type_label
from services.core.vkr_core.engine.violations import PipelineViolation
from services.core.vkr_core.models.enums import ViolationStatus

# ── Бренд МИИГАиК ─────────────────────────────────────────────────────────────
_NAVY    = "#001a72"
_RED     = "#d6001c"
_GRAY    = "#8996a0"
_LIGHT   = "#f3f3f1"
_NAVY_L  = "#e7e9f3"
_ORANGE  = "#ed6900"

_C_NAVY   = colors.HexColor(_NAVY)
_C_RED    = colors.HexColor(_RED)
_C_GRAY   = colors.HexColor(_GRAY)
_C_LIGHT  = colors.HexColor(_LIGHT)
_C_NAVY_L = colors.HexColor(_NAVY_L)
_C_WHITE  = colors.white
_C_BLACK  = colors.HexColor("#1a1a2e")

_SEV_COLOR = {"critical": _C_RED,  "warning": colors.HexColor(_ORANGE), "info": _C_NAVY}
_SEV_BG    = {"critical": colors.HexColor("#fdf0f1"), "warning": colors.HexColor("#fff4ec"), "info": _C_NAVY_L}
_SEV_LABEL = {"critical": "Критично", "warning": "Предупреждение", "info": "Информация"}
_STATUS_LABEL = {
    ViolationStatus.auto_fixed:      "Автоисправлено",
    ViolationStatus.manual_required: "Требует проверки",
    ViolationStatus.accepted:        "Принято",
    ViolationStatus.rejected:        "Отклонено",
}

# ── Шрифты ────────────────────────────────────────────────────────────────────
_ASSETS   = Path(__file__).parents[1] / "assets" / "fonts"
_F_REG    = _ASSETS / "Montserrat-Regular.ttf"
_F_SEMI   = _ASSETS / "Montserrat-SemiBold.ttf"
_F_BOLD   = _ASSETS / "Montserrat-Bold.ttf"
_FB_REG   = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FB_BOLD  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _register() -> tuple[str, str, str]:
    if _F_REG.exists():
        pdfmetrics.registerFont(TTFont("M",     str(_F_REG)))
        pdfmetrics.registerFont(TTFont("M-SB",  str(_F_SEMI) if _F_SEMI.exists() else str(_F_BOLD)))
        pdfmetrics.registerFont(TTFont("M-B",   str(_F_BOLD)))
        return "M", "M-SB", "M-B"
    if Path(_FB_REG).exists():
        pdfmetrics.registerFont(TTFont("M",    _FB_REG))
        pdfmetrics.registerFont(TTFont("M-SB", _FB_BOLD))
        pdfmetrics.registerFont(TTFont("M-B",  _FB_BOLD))
    return "M", "M-SB", "M-B"


_R, _SB, _B = _register()


def _safe(t: object) -> str:
    return escape(str(t or ""))


def _counts(violations: list[PipelineViolation]) -> dict[str, int]:
    return {
        "total":    len(violations),
        "fixed":    sum(1 for v in violations if v.status == ViolationStatus.auto_fixed),
        "manual":   sum(1 for v in violations if v.status == ViolationStatus.manual_required),
        "critical": sum(1 for v in violations if v.severity == "critical"),
        "warning":  sum(1 for v in violations if v.severity == "warning"),
        "info":     sum(1 for v in violations if v.severity == "info"),
    }


def _st(name, font=None, size=10, leading=None, color=None, **kw) -> ParagraphStyle:
    return ParagraphStyle(
        name,
        fontName=font or _R,
        fontSize=size,
        leading=leading or round(size * 1.45),
        textColor=color or _C_BLACK,
        **kw,
    )


# ── Кастомный page-template с синей боковой полосой ───────────────────────────
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate  # noqa: E402


def _make_doc(output: Path) -> BaseDocTemplate:
    W, H = A4

    def on_page(canvas, doc):
        canvas.saveState()
        # Левая синяя полоса
        canvas.setFillColor(_C_NAVY)
        canvas.rect(0, 0, 6 * mm, H, fill=1, stroke=0)
        # Верхняя полоса
        canvas.rect(0, H - 8 * mm, W, 8 * mm, fill=1, stroke=0)
        # Логотип / название в верхней полосе
        canvas.setFillColor(_C_WHITE)
        canvas.setFont(_B, 9)
        canvas.drawString(12 * mm, H - 5.5 * mm, "ВКР.Формат  •  МИИГАиК")
        # Номер страницы внизу
        canvas.setFillColor(_C_GRAY)
        canvas.setFont(_R, 7.5)
        canvas.drawRightString(W - 15 * mm, 8 * mm, f"Стр. {doc.page}")
        canvas.restoreState()

    frame = Frame(
        12 * mm, 14 * mm,          # x, y (отступы от края с учётом полос)
        W - 24 * mm, H - 28 * mm, # w, h
        leftPadding=0, rightPadding=0,
        topPadding=0,  bottomPadding=0,
    )
    tmpl = PageTemplate(id="main", frames=[frame], onPage=on_page)
    doc  = BaseDocTemplate(
        str(output),
        pagesize=A4,
        pageTemplates=[tmpl],
    )
    return doc


def generate_report_pdf(
    violations: list[PipelineViolation],
    toc_warning: str | None = None,
    volume_pages: int | None = None,
) -> Path:
    tmp  = Path(tempfile.mkdtemp(prefix="vkr-report-pdf-"))
    out  = tmp / "report.pdf"
    doc  = _make_doc(out)
    W    = A4[0] - 24 * mm   # рабочая ширина фрейма

    cnt  = _counts(violations)
    story: list = []

    # ── Заголовок ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Отчёт о проверке ВКР",
        _st("h1", font=_B, size=22, leading=27, color=_C_NAVY, spaceAfter=1)))
    story.append(Paragraph("Автоматический анализ оформления по Приказу МИИГАиК №697-01 и ГОСТ 7.32",
        _st("sub", size=9, color=_C_GRAY, spaceAfter=6)))
    story.append(HRFlowable(width="100%", thickness=1, color=_C_NAVY_L, spaceAfter=10))

    # ── Сводка ─────────────────────────────────────────────────────────────────
    col = W / 3

    def _kpi(label: str, value: str, bg: colors.Color) -> list:
        return [
            Paragraph(label, _st("kl", size=7.5, color=_C_GRAY, leading=10)),
            Paragraph(value, _st("kv", font=_B,  size=22, leading=26, color=_C_NAVY)),
        ]

    kpi_data = [[
        _kpi("Всего замечаний",  str(cnt["total"]),  _C_NAVY_L),
        _kpi("Автоисправлено",   str(cnt["fixed"]),  colors.HexColor("#e6f4ea")),
        _kpi("Требует проверки", str(cnt["manual"]), colors.HexColor("#fdf0f1")),
    ]]
    kpi_tbl = Table(kpi_data, colWidths=[col, col, col])
    kpi_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), _C_NAVY_L),
        ("BACKGROUND",    (1, 0), (1, 0), colors.HexColor("#e6f4ea")),
        ("BACKGROUND",    (2, 0), (2, 0), colors.HexColor("#fdf0f1")),
        ("LINEAFTER",     (0, 0), (1, 0), 1, colors.HexColor("#d0d5e8")),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [3]),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 6 * mm))

    # Строка деталей сводки
    detail_parts = [
        f"<font color='#{_RED[1:]}'><b>Критично: {cnt['critical']}</b></font>",
        f"<font color='#{_ORANGE[1:]}'><b>Предупреждений: {cnt['warning']}</b></font>",
        f"<font color='#{_NAVY[1:]}'><b>Информационных: {cnt['info']}</b></font>",
    ]
    if volume_pages:
        detail_parts.append(f"Объём: {volume_pages} стр.")
    story.append(Paragraph("  ·  ".join(detail_parts),
        _st("det", size=9, spaceAfter=4)))

    if toc_warning:
        story.append(Paragraph(f"⚠  {_safe(toc_warning)}",
            _st("warn", size=8.5, color=colors.HexColor(_ORANGE), spaceAfter=6,
                borderPad=4, borderColor=colors.HexColor(_ORANGE), borderWidth=0.5, borderRadius=3)))

    # ── Детализация ────────────────────────────────────────────────────────────
    if not violations:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("Замечаний не обнаружено.",
            _st("ok", size=11, color=_C_GRAY)))
    else:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Детализация замечаний",
            _st("h2", font=_SB, size=13, color=_C_NAVY, spaceBefore=4, spaceAfter=5)))
        story.append(HRFlowable(width="100%", thickness=0.8, color=_C_NAVY_L, spaceAfter=6))

        cw_tag  = 2.4 * cm
        cw_body = W - cw_tag

        for idx, v in enumerate(violations, 1):
            sev_bg    = _SEV_BG.get(v.severity,    _C_NAVY_L)
            sev_color = _SEV_COLOR.get(v.severity, _C_NAVY)
            sev_label = _SEV_LABEL.get(v.severity, v.severity)
            stat_lbl  = _STATUS_LABEL.get(v.status, str(v.status))
            hex_sev   = sev_color.hexval()[2:] if hasattr(sev_color, "hexval") else "001a72"

            # Строка-заголовок нарушения
            hdr = Table([[
                Paragraph(
                    f"<font color='#{hex_sev}'><b>{idx}</b></font>",
                    _st("ni", font=_B, size=9, color=_C_GRAY, alignment=TA_LEFT)),
                Paragraph(
                    f"<font color='#{hex_sev}'><b>{_safe(sev_label)}</b></font>"
                    f"<font color='#4a5568'>  {_safe(violation_type_label(v.type))}</font>",
                    _st("vt", font=_SB, size=9.5)),
                Paragraph(
                    _safe(stat_lbl),
                    _st("vs", size=8, color=_C_GRAY, alignment=TA_RIGHT)),
            ]], colWidths=[0.6 * cm, cw_body - 3.2 * cm, 3.2 * cm])
            hdr.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), sev_bg),
                ("TOPPADDING",    (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ]))

            # Тело нарушения
            rows = [
                [Paragraph("Норматив",  _st("lbl", font=_SB, size=8, color=_C_GRAY)),
                 Paragraph(_safe(v.rule_reference), _st("val", size=9))],
                [Paragraph("Описание",  _st("lbl", font=_SB, size=8, color=_C_GRAY)),
                 Paragraph(_safe(v.description),    _st("val", size=9))],
            ]
            if v.section_title:
                rows.append([
                    Paragraph("Раздел", _st("lbl", font=_SB, size=8, color=_C_GRAY)),
                    Paragraph(_safe(v.section_title), _st("val", size=9)),
                ])
            if v.original_text:
                rows.append([
                    Paragraph("Было",  _st("lbl", font=_SB, size=8, color=_C_GRAY)),
                    Paragraph(_safe(v.original_text), _st("val_mono", font=_R, size=8.5,
                        backColor=colors.HexColor("#f8f8f8"))),
                ])
            if v.fixed_text:
                rows.append([
                    Paragraph("Стало", _st("lbl", font=_SB, size=8, color=colors.HexColor("#2d6a4f"))),
                    Paragraph(_safe(v.fixed_text), _st("val_fix", font=_R, size=8.5,
                        backColor=colors.HexColor("#f0fdf4"))),
                ])

            body = Table(rows, colWidths=[cw_tag, cw_body])
            body.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), _C_WHITE),
                ("TOPPADDING",    (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING",   (0, 0), (0, -1),  8),
                ("LEFTPADDING",   (1, 0), (1, -1),  6),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW",     (0, -1), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
            ]))

            card = Table([[hdr], [body]], colWidths=[W])
            card.setStyle(TableStyle([
                ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d5e8")),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ]))
            story.append(card)
            story.append(Spacer(1, 4 * mm))

    doc.build(story)
    return out


def generate_diff_text(original_text: str, processed_text: str) -> str:
    diff = difflib.unified_diff(
        original_text.splitlines(),
        processed_text.splitlines(),
        fromfile="original",
        tofile="processed",
        lineterm="",
    )
    return "\n".join(diff)
