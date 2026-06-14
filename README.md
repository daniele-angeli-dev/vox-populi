# vox-populi 🔮

> You shipped the update at 11pm on a Friday.
>
> By Sunday morning, 47 new 1-star reviews were waiting for you.
>
> You opened the App Store dashboard, scrolled through the wall of complaints — *crash on login*, *notifications broken*, *what happened to the profile screen?* — and closed the tab.
>
> You know there are real bugs in there. You know users are frustrated. But reading 200 reviews one by one, figuring out which issues are most frequent, estimating what's worth fixing first, and then writing individual replies to each complaint... you have a sprint to plan and a PR queue to clear.
>
> So the reviews sit there. Unread. Unanswered.
>
> I built vox-populi for that moment. Point it at any App Store or Google Play URL, and it reads every review, finds the patterns, prioritizes what to fix, estimates the effort, and writes the replies — in whatever tone you want, in seconds.
>
> No spreadsheets. No copy-pasting. No pretending you'll get to it later.

---

## How it works

```
Store URL ──► load_reviews ──► analyze (LLM) ──► report + fix list
                                                         │
                                            gen_replies (LLM) ──► auto-replies
                                                         │
                                            compute_stats (Python) ──► dashboard.html
```

Each step is a node in a [LangGraph](https://github.com/langchain-ai/langgraph) graph. The LLM handles the reasoning — categorization, prioritization, tone. Python handles the rest.

---

## Usage

Run the wizard. It asks four questions and does everything else automatically:

```bash
python main.py
```

```
🔮 vox-populi — wizard

──────────────────────────────────────────────────
🔗 App link (App Store or Google Play):
  https://play.google.com/store/apps/details?id=com.example.app
  ✅ Detected: 🤖 Google Play — ID: com.example.app

📊 How many reviews do you want to analyze? (default: 500)

📈 Generate an HTML dashboard? [Y/n]

🎭 Reply tone:
  ❯ Formal — professional and detached
    Friendly — warm and close to the user
    Direct — short and to the point
    Empathetic — understanding, acknowledges the issue
```

All output lands in `reports/`. Open the `.md` files in any editor, the `.html` in any browser.

---

## What it generates

**`report_TIMESTAMP.md`** — the full analysis:
- Sentiment breakdown (positive / negative / neutral)
- Categories (bug, UX, performance, feature requests, compliments)
- Recurring patterns ranked by frequency and severity
- Prioritized fix list with effort estimates in hours

**`release_TIMESTAMP.md`** — replies and release notes:
- Auto-generated responses to every negative review, in the tone you chose
- Release notes from git history, grouped by feature / fix / performance

**`dashboard_TIMESTAMP.html`** — four interactive charts:
- Average rating per version (bar chart, color-coded green/yellow/red)
- Review volume over time (line chart)
- Star distribution across all reviews (doughnut)
- Positive vs negative vs neutral per version (stacked bar)

---

## Advanced usage

```bash
# Analyze only, from a local file
python main.py --command analyze --file samples/reviews.csv

# Release notes + auto-replies (from a real repo)
python main.py --command release --repo C:\path\to\myapp --store https://apps.apple.com/...

# Historical dashboard, limit to 100 reviews
python main.py --command dashboard --store https://play.google.com/... --max-reviews 100
```

---

## Setup

```bash
git clone https://github.com/daniele-angeli-dev/vox-populi
cd vox-populi

python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate  # Mac/Linux

pip install -r requirements.txt

cp .env.example .env
# Set MODEL_PROVIDER and the matching API key in .env
# Default: MODEL_PROVIDER=anthropic → set ANTHROPIC_API_KEY
```

---

## Options

| Option | Description |
|---|---|
| `--command analyze\|release\|dashboard` | Run a specific phase (omit for wizard) |
| `--file PATH` | Local reviews file (CSV or JSON) |
| `--store URL` | App Store or Google Play URL (auto-detected) |
| `--max-reviews N` | Max reviews to fetch from store (default: 500) |
| `--repo PATH` | Git repo path for release notes |
| `--git-log PATH` | Pre-exported git log file (alternative to `--repo`) |

---

## Store limits

| Store | Default | Hard limit |
|---|---|---|
| App Store | 500 | ~500 (iTunes RSS, 10 pages × 50) |
| Google Play | 500 | ~3000+ (above that, it slows down) |

---

## Project structure

```
vox-populi/
├── main.py       # CLI + wizard
├── agent.py      # LangGraph graph definition
├── state.py      # shared state between nodes
├── nodes.py      # all graph nodes (Phase 1, 2, 3)
├── tools.py      # I/O: file loading, store scraping, report writing
├── prompts.py    # Claude prompts
├── samples/      # test data (reviews.csv, git_log.txt, reviews_history.csv)
└── reports/      # generated output (gitignored)
```

---

## Key concepts demonstrated

- **LangGraph** — multi-node graph with conditional routing across three phases
- **Agentic analysis** — LLM as reasoning engine over unstructured user feedback
- **Store scraping** — iTunes RSS API (no auth) + `google-play-scraper`
- **Dynamic prompting** — tone injected at runtime into the reply prompt
- **Pure Python aggregation** — dashboard stats computed without LLM calls
- **Interactive CLI** — `questionary` for guided wizard UX

---

## Tech stack

- Python 3.10+
- [LangGraph](https://github.com/langchain-ai/langgraph) — agent graph framework
- Any LangChain-compatible LLM — Anthropic Claude (default), OpenAI, Groq, Gemini, Ollama
- [Chart.js](https://www.chartjs.org) — embedded in the generated HTML dashboard
- [google-play-scraper](https://github.com/JoMingyu/google-play-scraper) — Play Store reviews
- [questionary](https://github.com/tmbo/questionary) — interactive CLI prompts
- [python-dotenv](https://github.com/theskumar/python-dotenv) — environment config
