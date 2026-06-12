"""
backend/reporting/__init__.py
==============================
Public surface of the Vantag reporting package.

Usage::

    from backend.reporting import ReportGenerator

    rg = ReportGenerator(output_dir="snapshots/reports")
    pdf_path = rg.generate(incident_dict)
"""

from backend.reporting.report_generator import ReportGenerator

__all__ = [
    "ReportGenerator",
]
