"""Deterministic weekly-report domain behavior."""

from .derived_metrics import build_fact_package
from .rendering import render_report

__all__ = ["build_fact_package", "render_report"]
