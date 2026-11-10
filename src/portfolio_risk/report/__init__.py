"""Optional exports (PDF and Excel). Needs the ``report`` extra; the core never imports this."""

from portfolio_risk.report.meta import ReportMeta

__all__ = ["ReportMeta"]
