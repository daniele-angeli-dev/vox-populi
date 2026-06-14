from typing import Optional, TypedDict


class VoxState(TypedDict):
    """
    Shared agent state. Every node reads from and writes to this object.
    LangGraph passes it from node to node, merging only the keys each node returns.
    """
    # ── Shared ───────────────────────────────────────────────────────────────
    command: str            # "analyze" | "release" | "dashboard" | "wizard"
    error: Optional[str]    # error message if something goes wrong

    # ── Phase 1: review analysis ─────────────────────────────────────────────
    reviews_file: str       # path to reviews file (CSV or JSON)
    store_url: str          # App Store or Google Play URL (alternative to reviews_file)
    max_reviews: int        # max reviews to fetch from store (default 500)
    reviews: list[dict]     # loaded reviews
    analysis: dict          # structured analysis returned by the LLM
    report: str             # generated markdown report
    fixes: list[dict]       # prioritized fix list

    # ── Phase 2: release notes + auto-replies ────────────────────────────────
    repo_path: str          # git repo path (to run git log)
    git_log_file: str       # path to a git log file (alternative to repo_path)
    git_log: str            # git log output
    tone: str               # reply tone chosen by the user
    release_notes_data: dict    # structured release notes (JSON from the LLM)
    release_notes: str          # release notes in markdown
    replies: list[dict]         # auto-generated replies for negative reviews

    # ── Phase 3: HTML dashboard ──────────────────────────────────────────────
    stats: dict             # per-version aggregations (pure Python, no LLM)
    html: str               # generated HTML dashboard
    want_dashboard: bool    # wizard: user requested the HTML dashboard
