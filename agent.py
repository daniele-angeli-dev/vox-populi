"""
agent.py — builds and compiles the LangGraph graph.

Available flows:
  analyze   → load_reviews → analyze → write_report → END
  release   → load_git_log → gen_release_notes → (gen_replies) → write_release_output → END
  dashboard → load_history → compute_stats → gen_dashboard → END
  wizard    → load_reviews → analyze → write_report → gen_replies → write_release_output
                                                                          → (want_dashboard) compute_stats → gen_dashboard → END
"""
from langgraph.graph import END, StateGraph

from nodes import (
    # Phase 1
    analyze_node,
    load_reviews_node,
    router_node,
    write_report_node,
    # Phase 2
    gen_release_notes_node,
    gen_replies_node,
    load_git_log_node,
    write_release_output_node,
    # Phase 3
    load_history_node,
    compute_stats_node,
    gen_dashboard_node,
)
from state import VoxState


# ── Routing functions ─────────────────────────────────────────────────────────

def _route_command(state: VoxState) -> str:
    command = state.get("command", "")
    if command in ("analyze", "wizard"):
        return "load_reviews"
    elif command == "release":
        return "load_git_log"
    elif command == "dashboard":
        return "load_history"
    return END


def _route_after_write_report(state: VoxState) -> str:
    """After the report: wizard continues to gen_replies, analyze ends."""
    if state.get("command") == "wizard":
        return "gen_replies"
    return END


def _route_after_release_notes(state: VoxState) -> str:
    """After release notes: generate replies only if reviews are loaded."""
    if state.get("reviews"):
        return "gen_replies"
    return "write_release_output"


def _route_after_release_output(state: VoxState) -> str:
    """After release output: wizard with dashboard continues to compute_stats."""
    if state.get("command") == "wizard" and state.get("want_dashboard"):
        return "compute_stats"
    return END


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(VoxState)

    # ── Nodes ─────────────────────────────────────────────────────────────────
    graph.add_node("router", router_node)

    # Phase 1
    graph.add_node("load_reviews", load_reviews_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("write_report", write_report_node)

    # Phase 2
    graph.add_node("load_git_log", load_git_log_node)
    graph.add_node("gen_release_notes", gen_release_notes_node)
    graph.add_node("gen_replies", gen_replies_node)
    graph.add_node("write_release_output", write_release_output_node)

    # Phase 3
    graph.add_node("load_history", load_history_node)
    graph.add_node("compute_stats", compute_stats_node)
    graph.add_node("gen_dashboard", gen_dashboard_node)

    # ── Entry point ───────────────────────────────────────────────────────────
    graph.set_entry_point("router")

    # ── Edges ─────────────────────────────────────────────────────────────────

    # Router → dispatch by command
    graph.add_conditional_edges(
        "router",
        _route_command,
        {
            "load_reviews": "load_reviews",
            "load_git_log": "load_git_log",
            "load_history": "load_history",
            END: END,
        },
    )

    # Phase 1 / Wizard: analyze flow
    graph.add_edge("load_reviews", "analyze")
    graph.add_edge("analyze", "write_report")

    # After write_report: analyze → END, wizard → gen_replies
    graph.add_conditional_edges(
        "write_report",
        _route_after_write_report,
        {
            "gen_replies": "gen_replies",
            END: END,
        },
    )

    # Phase 2: release notes flow
    graph.add_edge("load_git_log", "gen_release_notes")
    graph.add_conditional_edges(
        "gen_release_notes",
        _route_after_release_notes,
        {
            "gen_replies": "gen_replies",
            "write_release_output": "write_release_output",
        },
    )

    # Replies → write output (wizard and release converge here)
    graph.add_edge("gen_replies", "write_release_output")

    # After write_release_output: release → END, wizard+dashboard → compute_stats
    graph.add_conditional_edges(
        "write_release_output",
        _route_after_release_output,
        {
            "compute_stats": "compute_stats",
            END: END,
        },
    )

    # Phase 3: dashboard flow
    graph.add_edge("load_history", "compute_stats")
    graph.add_edge("compute_stats", "gen_dashboard")
    graph.add_edge("gen_dashboard", END)

    return graph.compile()
