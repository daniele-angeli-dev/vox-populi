"""
nodes.py — all functions that make up the LangGraph graph.

Every node:
  - receives the full VoxState
  - does ONE thing
  - returns a dict with only the keys it modified
    (LangGraph automatically merges them back into the global state)
"""
import json
import os
import subprocess

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from prompts import (
    ANALYZE_SYSTEM_PROMPT,
    RELEASE_NOTES_SYSTEM_PROMPT,
    get_replies_system_prompt,
)
from state import VoxState
from tools import load_reviews_from_file, load_reviews_from_store, write_html_to_file, write_report_to_file


# ── LLM factory ─────────────────────────────────────────────────────────────

def _get_llm(max_tokens: int = 4096):
    """
    Build a LangChain chat model from env vars.
    MODEL          — model name  (default: claude-sonnet-4-6)
    MODEL_PROVIDER — provider    (default: anthropic)
    Swap in any provider supported by langchain: openai, google-genai, groq…
    """
    model    = os.getenv("MODEL", "claude-sonnet-4-6")
    provider = os.getenv("MODEL_PROVIDER", "anthropic")
    return init_chat_model(model, model_provider=provider, max_tokens=max_tokens)


# ── Phase 1 ──────────────────────────────────────────────────────────────────

def router_node(state: VoxState) -> dict:
    """
    Entry node. Does nothing concrete:
    actual routing happens in the conditional edges defined in agent.py.
    """
    return {}


def load_reviews_node(state: VoxState) -> dict:
    """Load reviews from a store URL or a local file."""
    if state.get("store_url"):
        print(f"🏪 Loading reviews from store: {state['store_url']}")
        reviews = load_reviews_from_store(state["store_url"], max_reviews=state.get("max_reviews", 500))
    else:
        print(f"📂 Loading reviews from: {state['reviews_file']}")
        reviews = load_reviews_from_file(state["reviews_file"])
    print(f"✅ Loaded {len(reviews)} reviews")
    return {"reviews": reviews}


def analyze_node(state: VoxState) -> dict:
    """
    Send reviews to the LLM and get a structured JSON analysis back.

    Returns:
      - summary
      - sentiment breakdown (positive/negative/neutral)
      - categories
      - recurring patterns
      - prioritized fix list with effort estimates
    """
    reviews = state["reviews"]
    print(f"🔍 Analyzing {len(reviews)} reviews with {os.getenv('MODEL', 'claude-sonnet-4-6')}...")

    llm = _get_llm(max_tokens=4096)
    reviews_text = _format_reviews(reviews)

    response = llm.invoke([
        SystemMessage(content=ANALYZE_SYSTEM_PROMPT),
        HumanMessage(content=f"Analyze these reviews:\n\n{reviews_text}"),
    ])

    raw = response.content if isinstance(response.content, str) else ""

    if not raw.strip():
        raise ValueError("LLM returned an empty response")

    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]).strip()

    try:
        analysis = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"\n❌ LLM response is not valid JSON:\n{raw[:500]}")
        raise e

    print("✅ Analysis complete")
    return {
        "analysis": analysis,
        "fixes": analysis.get("fixes", []),
    }


def write_report_node(state: VoxState) -> dict:
    """Build the markdown report and save it to disk."""
    print("📝 Generating report...")
    report = _build_report_markdown(state["analysis"])
    output_path = write_report_to_file(report, prefix="report")
    print(f"✅ Report saved to: {output_path}")
    return {"report": report}


# ── Phase 2 ──────────────────────────────────────────────────────────────────

def load_git_log_node(state: VoxState) -> dict:
    """
    Load the git log in two ways:
    - If repo_path is set → run `git log` on the repo
    - If git_log_file is set → read from file (useful for testing)
    """
    repo_path    = state.get("repo_path", "")
    git_log_file = state.get("git_log_file", "")

    if repo_path:
        print(f"📦 Running git log on: {repo_path}")
        result = subprocess.run(
            [
                "git", "log",
                "--pretty=format:%h %ad %s",
                "--date=short",
                "--no-merges",
                "--max-count=50",
            ],
            capture_output=True,
            text=True,
            cwd=repo_path,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git log failed: {result.stderr}")
        git_log = result.stdout

    elif git_log_file:
        print(f"📂 Loading git log from file: {git_log_file}")
        with open(git_log_file, "r", encoding="utf-8") as f:
            git_log = f.read()

    else:
        raise ValueError("Provide --repo or --git-log for the 'release' command")

    commit_count = len([l for l in git_log.strip().split("\n") if l])
    print(f"✅ Loaded {commit_count} commits")
    return {"git_log": git_log}


def gen_release_notes_node(state: VoxState) -> dict:
    """Generate structured release notes from the git log using the configured LLM."""
    print("📋 Generating release notes...")

    llm = _get_llm(max_tokens=2048)

    response = llm.invoke([
        SystemMessage(content=RELEASE_NOTES_SYSTEM_PROMPT),
        HumanMessage(content=f"Generate release notes from this git log:\n\n{state['git_log']}"),
    ])

    raw = response.content.strip() if isinstance(response.content, str) else ""
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]).strip()

    release_data = json.loads(raw)
    print("✅ Release notes generated")
    return {"release_notes_data": release_data}


def gen_replies_node(state: VoxState) -> dict:
    """
    Generate automatic replies for negative reviews (rating ≤ 3).
    Skips silently if no reviews are loaded in state.
    """
    reviews = state.get("reviews", [])
    if not reviews:
        print("ℹ️  No reviews loaded, skipping replies")
        return {"replies": []}

    # Filter only negative reviews
    negative = []
    for i, r in enumerate(reviews):
        try:
            rating = int(r.get("rating") or r.get("stars") or 5)
        except (ValueError, TypeError):
            rating = 5
        if rating <= 3:
            negative.append((i, r))

    if not negative:
        print("ℹ️  No negative reviews found, skipping replies")
        return {"replies": []}

    tone = state.get("tone", "Formal")
    print(f"💬 Generating replies for {len(negative)} negative reviews (tone: {tone})...")

    llm = _get_llm(max_tokens=8096)

    release_notes_md = _build_release_notes_markdown(state.get("release_notes_data", {}))
    reviews_text     = _format_negative_reviews(negative)

    response = llm.invoke([
        SystemMessage(content=get_replies_system_prompt(tone)),
        HumanMessage(content=(
            f"Release notes:\n{release_notes_md}"
            f"\n\n---\n\nReviews to reply to:\n{reviews_text}"
        )),
    ])

    raw = response.content.strip() if isinstance(response.content, str) else ""
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]).strip()

    try:
        replies_data = json.loads(raw)
    except json.JSONDecodeError:
        # Truncated JSON — recover completed replies before the cut
        cut = raw.rfind("},")
        if cut == -1:
            cut = raw.rfind("}")
        if cut != -1:
            raw = raw[: cut + 1] + "]}"
            try:
                replies_data = json.loads(raw)
            except json.JSONDecodeError:
                print("⚠️  Could not recover replies. Try lowering --max-reviews.")
                return {"replies": []}
        else:
            print("⚠️  Invalid response from model. Try lowering --max-reviews.")
            return {"replies": []}

    replies = replies_data.get("replies", [])
    print(f"✅ Generated {len(replies)} replies")
    return {"replies": replies}


def write_release_output_node(state: VoxState) -> dict:
    """Write the final output file with release notes and (optionally) replies."""
    print("📝 Writing output...")

    release_notes_md = _build_release_notes_markdown(state.get("release_notes_data", {}))
    replies = state.get("replies", [])

    lines = [
        "# vox-populi 🔮 — Release Notes & Replies",
        "",
        release_notes_md,
    ]

    if replies:
        lines += [
            "",
            "---",
            "",
            f"## 💬 Auto-generated Replies — tone: {state.get('tone', 'Formal')}",
            "",
            f"*{len(replies)} replies generated for negative reviews*",
            "",
        ]
        for r in replies:
            preview = r.get("original_text", "")
            lines += [
                f"### ⭐{r.get('rating')} — *\"{preview}...\"*",
                "",
                f"> {r.get('reply', '')}",
                "",
            ]

    lines += ["---", "*Generated by vox-populi 🔮*"]

    output = "\n".join(lines)
    output_path = write_report_to_file(output, prefix="release")
    print(f"✅ Output saved to: {output_path}")

    return {"release_notes": release_notes_md}


# ── Phase 3 ──────────────────────────────────────────────────────────────────

def load_history_node(state: VoxState) -> dict:
    """Load multi-version review history from a file or store URL."""
    if state.get("store_url"):
        print(f"🏪 Loading history from store: {state['store_url']}")
        reviews = load_reviews_from_store(state["store_url"], max_reviews=state.get("max_reviews", 500))
    else:
        print(f"📂 Loading review history from: {state['reviews_file']}")
        reviews = load_reviews_from_file(state["reviews_file"])
    print(f"✅ Loaded {len(reviews)} reviews")
    return {"reviews": reviews}


def compute_stats_node(state: VoxState) -> dict:
    """
    Aggregate reviews by version.
    Pure Python — no LLM call.
    Computes: average rating, star distribution, positive/negative/neutral per version.
    """
    from collections import defaultdict

    print("📊 Computing per-version statistics...")
    reviews = state["reviews"]
    by_version: dict[str, list[int]] = defaultdict(list)

    for r in reviews:
        version = r.get("version") or "unknown"
        try:
            rating = int(float(r.get("rating") or r.get("stars") or 0))
        except (ValueError, TypeError):
            rating = 0
        by_version[version].append(rating)

    versions = sorted(by_version.keys())

    version_stats = {}
    for v in versions:
        ratings = by_version[v]
        valid = [r for r in ratings if 1 <= r <= 5]
        version_stats[v] = {
            "count":       len(ratings),
            "avg_rating":  round(sum(valid) / len(valid), 2) if valid else 0,
            "distribution": {str(i): ratings.count(i) for i in range(1, 6)},
            "positive":    len([r for r in valid if r >= 4]),
            "negative":    len([r for r in valid if r <= 2]),
            "neutral":     len([r for r in valid if r == 3]),
        }

    all_ratings = [r for rs in by_version.values() for r in rs if 1 <= r <= 5]

    stats = {
        "versions":             versions,
        "version_stats":        version_stats,
        "total_reviews":        len(reviews),
        "overall_avg":          round(sum(all_ratings) / len(all_ratings), 2) if all_ratings else 0,
        "overall_distribution": {str(i): all_ratings.count(i) for i in range(1, 6)},
        "latest_version":       versions[-1] if versions else "N/A",
    }

    print(f"✅ {len(versions)} versions, {len(reviews)} total reviews, avg rating: {stats['overall_avg']}")
    return {"stats": stats}


def gen_dashboard_node(state: VoxState) -> dict:
    """
    Generate the HTML dashboard with Chart.js.
    Data is injected as JSON directly into the HTML — no server needed.
    """
    import json as _json
    from datetime import datetime as _dt

    print("🎨 Generating HTML dashboard...")

    stats = state["stats"]
    data_json    = _json.dumps(stats, ensure_ascii=False)
    generated_at = _dt.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>vox-populi 🔮 — Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --bg: #0f1117;
            --card: #1a1d2e;
            --border: #2d2f44;
            --text: #e2e8f0;
            --muted: #8892a4;
            --accent: #7c3aed;
            --green: #10b981;
            --red: #ef4444;
            --yellow: #f59e0b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 2rem;
        }}
        header {{ margin-bottom: 2rem; }}
        header h1 {{ font-size: 1.8rem; font-weight: 700; }}
        header p {{ color: var(--muted); margin-top: 0.4rem; font-size: 0.95rem; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.25rem;
        }}
        .stat-card .label {{
            color: var(--muted);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .stat-card .value {{
            font-size: 1.9rem;
            font-weight: 700;
            margin-top: 0.3rem;
        }}
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
            gap: 1.5rem;
        }}
        .chart-card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
        }}
        .chart-card h2 {{
            font-size: 0.95rem;
            font-weight: 600;
            margin-bottom: 1.25rem;
            color: var(--text);
        }}
        canvas {{ max-height: 260px; }}
        footer {{
            margin-top: 2.5rem;
            color: var(--muted);
            font-size: 0.78rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <header>
        <h1>vox-populi 🔮 — Review Dashboard</h1>
        <p>
            {stats['total_reviews']} reviews &middot;
            {len(stats['versions'])} versions analyzed &middot;
            Overall avg rating: ⭐ {stats['overall_avg']}
        </p>
    </header>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">Total reviews</div>
            <div class="value">{stats['total_reviews']}</div>
        </div>
        <div class="stat-card">
            <div class="label">Versions</div>
            <div class="value">{len(stats['versions'])}</div>
        </div>
        <div class="stat-card">
            <div class="label">Avg rating</div>
            <div class="value" style="color: #f59e0b;">⭐ {stats['overall_avg']}</div>
        </div>
        <div class="stat-card">
            <div class="label">Latest version</div>
            <div class="value" style="font-size: 1.3rem;">{stats['latest_version']}</div>
        </div>
    </div>

    <div class="charts-grid">
        <div class="chart-card">
            <h2>📊 Average rating per version</h2>
            <canvas id="avgRatingChart"></canvas>
        </div>
        <div class="chart-card">
            <h2>📈 Review volume per version</h2>
            <canvas id="volumeChart"></canvas>
        </div>
        <div class="chart-card">
            <h2>⭐ Star distribution (overall)</h2>
            <canvas id="distributionChart"></canvas>
        </div>
        <div class="chart-card">
            <h2>😊 Positive vs Negative per version</h2>
            <canvas id="sentimentChart"></canvas>
        </div>
    </div>

    <footer>Generated by vox-populi 🔮 &mdash; {generated_at}</footer>

    <script>
        const data = {data_json};

        Chart.defaults.color = '#8892a4';
        Chart.defaults.borderColor = '#2d2f44';

        // 1. Average rating per version
        new Chart(document.getElementById('avgRatingChart'), {{
            type: 'bar',
            data: {{
                labels: data.versions,
                datasets: [{{
                    label: 'Avg rating',
                    data: data.versions.map(v => data.version_stats[v].avg_rating),
                    backgroundColor: data.versions.map(v => {{
                        const avg = data.version_stats[v].avg_rating;
                        if (avg >= 4) return '#10b981';
                        if (avg >= 3) return '#f59e0b';
                        return '#ef4444';
                    }}),
                    borderRadius: 6,
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{ min: 0, max: 5 }},
                    x: {{ grid: {{ display: false }} }}
                }},
                plugins: {{ legend: {{ display: false }} }}
            }}
        }});

        // 2. Review volume per version
        new Chart(document.getElementById('volumeChart'), {{
            type: 'line',
            data: {{
                labels: data.versions,
                datasets: [{{
                    label: 'Reviews',
                    data: data.versions.map(v => data.version_stats[v].count),
                    borderColor: '#7c3aed',
                    backgroundColor: 'rgba(124, 58, 237, 0.15)',
                    fill: true,
                    tension: 0.35,
                    pointBackgroundColor: '#7c3aed',
                    pointRadius: 5,
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{ ticks: {{ stepSize: 1 }} }},
                    x: {{ grid: {{ display: false }} }}
                }},
                plugins: {{ legend: {{ display: false }} }}
            }}
        }});

        // 3. Star distribution
        new Chart(document.getElementById('distributionChart'), {{
            type: 'doughnut',
            data: {{
                labels: ['⭐1', '⭐2', '⭐3', '⭐4', '⭐5'],
                datasets: [{{
                    data: ['1','2','3','4','5'].map(k => data.overall_distribution[k] || 0),
                    backgroundColor: ['#ef4444','#f97316','#f59e0b','#84cc16','#10b981'],
                    borderWidth: 0,
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ position: 'right' }} }}
            }}
        }});

        // 4. Positive vs Negative per version
        new Chart(document.getElementById('sentimentChart'), {{
            type: 'bar',
            data: {{
                labels: data.versions,
                datasets: [
                    {{
                        label: '😊 Positive (4-5⭐)',
                        data: data.versions.map(v => data.version_stats[v].positive),
                        backgroundColor: '#10b981',
                        borderRadius: 4,
                    }},
                    {{
                        label: '😐 Neutral (3⭐)',
                        data: data.versions.map(v => data.version_stats[v].neutral),
                        backgroundColor: '#f59e0b',
                        borderRadius: 4,
                    }},
                    {{
                        label: '😠 Negative (1-2⭐)',
                        data: data.versions.map(v => data.version_stats[v].negative),
                        backgroundColor: '#ef4444',
                        borderRadius: 4,
                    }}
                ]
            }},
            options: {{
                responsive: true,
                scales: {{
                    x: {{ stacked: true, grid: {{ display: false }} }},
                    y: {{ stacked: true }}
                }}
            }}
        }});
    </script>
</body>
</html>"""

    output_path = write_html_to_file(html)
    print(f"✅ Dashboard saved to: {output_path}")
    return {"html": html}


# ── Private helpers ───────────────────────────────────────────────────────────

def _format_reviews(reviews: list[dict]) -> str:
    lines = []
    for i, r in enumerate(reviews, 1):
        rating  = r.get("rating") or r.get("stars") or "N/A"
        text    = r.get("text") or r.get("review") or r.get("body") or ""
        version = r.get("version") or ""
        line    = f"[{i}] ⭐{rating}"
        if version:
            line += f" (v{version})"
        line += f"\n{text}"
        lines.append(line)
    return "\n\n".join(lines)


def _format_negative_reviews(negative: list[tuple]) -> str:
    lines = []
    for orig_idx, r in negative:
        rating = r.get("rating") or r.get("stars") or "N/A"
        text   = r.get("text") or r.get("review") or r.get("body") or ""
        lines.append(f"[{orig_idx}] ⭐{rating}\n{text}")
    return "\n\n".join(lines)


def _build_release_notes_markdown(data: dict) -> str:
    if not data:
        return "*No release notes available*"

    lines = [
        f"## 📦 Release {data.get('version', 'latest')} — {data.get('date', '')}",
        "",
        f"*{data.get('summary', '')}*",
        "",
    ]

    for section in data.get("sections", []):
        lines.append(f"### {section.get('label', section.get('type', ''))}")
        for item in section.get("items", []):
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def _build_report_markdown(analysis: dict) -> str:
    s   = analysis.get("sentiment", {})
    pos = s.get("positive", 0)
    neg = s.get("negative", 0)
    neu = s.get("neutral",  0)
    total = pos + neg + neu

    SEV_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    PAT_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}

    lines = [
        "# vox-populi 🔮 — Review Analysis Report",
        "",
        "## 📊 Summary",
        "",
        analysis.get("summary", ""),
        "",
        "## 🎭 Sentiment",
        "",
        "| Positive | Negative | Neutral | Total |",
        "|---|---|---|---|",
        f"| {pos} | {neg} | {neu} | {total} |",
        "",
        "## 📂 Categories",
        "",
    ]

    for cat in analysis.get("categories", []):
        lines.append(f"### {cat['name'].upper()} — {cat['count']} reviews")
        for ex in cat.get("examples", [])[:2]:
            lines.append(f"> *\"{ex}\"*")
        lines.append("")

    lines += ["## 🔥 Recurring patterns", ""]

    for p in analysis.get("patterns", []):
        emoji = PAT_EMOJI.get(p.get("severity", ""), "⚪")
        lines.append(
            f"- {emoji} **{p['issue']}** — appears {p['frequency']} times"
        )

    lines += [
        "",
        "## 🛠 Prioritized Fix List",
        "",
        "| # | Fix | Severity | Est. hours | Reviews |",
        "|---|---|---|---|---|",
    ]

    for fix in analysis.get("fixes", []):
        sev   = fix.get("severity", "")
        emoji = SEV_EMOJI.get(sev, "⚪")
        lines.append(
            f"| {fix.get('priority', '?')} "
            f"| **{fix.get('title', '')}** "
            f"| {emoji} {sev} "
            f"| {fix.get('estimated_hours', '?')}h "
            f"| {fix.get('related_reviews', '?')} |"
        )

    lines += ["", "---", "*Generated by vox-populi 🔮*"]
    return "\n".join(lines)
