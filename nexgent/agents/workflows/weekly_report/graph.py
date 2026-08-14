"""Compiled map-reduce graph for bounded ward-risk weekly reports."""

from ax_contracts import WardWeeklyReportBatchResult, WeeklyReportRequest
from langgraph.graph import END, START, StateGraph

from workflows.weekly_report.nodes import (
    aggregate_reports,
    calculate_metrics,
    compose_markdown_report,
    fan_out_wards,
    generate_korean_narrative,
    load_risk_windows,
    validate_request,
)
from workflows.weekly_report.state import (
    WardReportBranchOutputState,
    WardReportBranchState,
    WeeklyReportState,
)

_branch_builder = StateGraph(
    WardReportBranchState,
    output_schema=WardReportBranchOutputState,
)
_branch_builder.add_node("calculate_metrics", calculate_metrics)
_branch_builder.add_node("generate_korean_narrative", generate_korean_narrative)
_branch_builder.add_node("compose_markdown_report", compose_markdown_report)
_branch_builder.add_edge(START, "calculate_metrics")
_branch_builder.add_edge("calculate_metrics", "generate_korean_narrative")
_branch_builder.add_edge("generate_korean_narrative", "compose_markdown_report")
_branch_builder.add_edge("compose_markdown_report", END)
_ward_report_graph = _branch_builder.compile(name="weekly_report_ward_branch")

_builder = StateGraph(
    WeeklyReportState,
    input_schema=WeeklyReportRequest,
    output_schema=WardWeeklyReportBatchResult,
)
_builder.add_node("validate_request", validate_request)
_builder.add_node("load_risk_windows", load_risk_windows)
_builder.add_node("build_ward_report", _ward_report_graph)
_builder.add_node("aggregate_reports", aggregate_reports)

_builder.add_edge(START, "validate_request")
_builder.add_edge("validate_request", "load_risk_windows")
_builder.add_conditional_edges("load_risk_windows", fan_out_wards)
_builder.add_edge("build_ward_report", "aggregate_reports")
_builder.add_edge("aggregate_reports", END)

graph = _builder.compile(name="ansimk_weekly_reporter")
