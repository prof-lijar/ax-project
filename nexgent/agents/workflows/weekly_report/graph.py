"""Compiled map-reduce graph for personal weekly reports."""

from ax_contracts import WeeklyReportBatchResult, WeeklyReportRequest
from langgraph.graph import END, START, StateGraph

from workflows.weekly_report.nodes import (
    aggregate_reports,
    calculate_metrics,
    compose_markdown_report,
    fan_out_users,
    generate_korean_narrative,
    load_mock_activity,
    validate_request,
)
from workflows.weekly_report.state import (
    UserReportBranchOutputState,
    UserReportBranchState,
    WeeklyReportState,
)

_branch_builder = StateGraph(
    UserReportBranchState,
    output_schema=UserReportBranchOutputState,
)
_branch_builder.add_node("calculate_metrics", calculate_metrics)
_branch_builder.add_node("generate_korean_narrative", generate_korean_narrative)
_branch_builder.add_node("compose_markdown_report", compose_markdown_report)
_branch_builder.add_edge(START, "calculate_metrics")
_branch_builder.add_edge("calculate_metrics", "generate_korean_narrative")
_branch_builder.add_edge("generate_korean_narrative", "compose_markdown_report")
_branch_builder.add_edge("compose_markdown_report", END)
_user_report_graph = _branch_builder.compile(name="weekly_report_user_branch")

_builder = StateGraph(
    WeeklyReportState,
    input_schema=WeeklyReportRequest,
    output_schema=WeeklyReportBatchResult,
)
_builder.add_node("validate_request", validate_request)
_builder.add_node("load_mock_activity", load_mock_activity)
_builder.add_node("build_user_report", _user_report_graph)
_builder.add_node("aggregate_reports", aggregate_reports)

_builder.add_edge(START, "validate_request")
_builder.add_edge("validate_request", "load_mock_activity")
_builder.add_conditional_edges("load_mock_activity", fan_out_users)
_builder.add_edge("build_user_report", "aggregate_reports")
_builder.add_edge("aggregate_reports", END)

graph = _builder.compile(name="ansimk_weekly_reporter")
