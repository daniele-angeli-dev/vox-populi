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

## CI/CD Integration

Drop it into any pipeline. Run it automatically after every release to catch review spikes before they compound.

```yaml
# .github/workflows/review-check.yml
name: Review Analysis
on:
  release:
    types: [published]
  schedule:
    - cron: '0 9 * * 1'  # every Monday at 9am

jobs:
  review-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: |
          python main.py --command analyze \
            --store ${{ secrets.APP_STORE_URL }} \
            --max-reviews 200
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - uses: actions/upload-artifact@v3
        with:
          name: review-report
          path: reports/
```

Reports are saved as pipeline artifacts — open them directly from the GitHub Actions run page.

---

## How it works

```
Store URL ──► load_reviews ──► analyze (LLM) ──► report + fix list
                                                         │
                                            gen_replies (LLM) ──► auto-replies
                                                         │
                                            compute_stats (Python) ──► dashboard.html
```

The agent (LLM via LangChain) drives a [LangGraph](https://github.com/langchain-ai/langgraph) graph across three phases:

| Phase | Nodes | What happens |
|-------|-------|--------------|
| 1 — Analyze | `load_reviews` → `analyze` → `write_report` | Scrapes reviews, classifies them, builds a prioritized fix list |
| 2 — Release | `load_git_log` → `gen_release_notes` → `gen_replies` → `write_release_output` | Generates release notes from git history and auto-replies for negative reviews |
| 3 — Dashboard | `load_history` → `compute_stats` → `gen_dashboard` | Aggregates per-version stats and renders an interactive HTML dashboard |

The LLM handles the reasoning — categorization, prioritization, tone. Python handles the rest.

---

## Features

- **Wizard mode** — four questions, fully automated run; no flags needed
- **Store scraping** — App Store (iTunes RSS, no auth) and Google Play out of the box
- **Sentiment analysis** — classifies every review as positive, negative, or neutral
- **Pattern detection** — finds recurring issues ranked by frequency and severity
- **Prioritized fix list** — ordered by urgency with realistic hour estimates for a senior dev
- **Auto-replies** — generates a tailored response for every negative review
- **Four reply tones** — Formal, Friendly, Direct, Empathetic; injected at runtime
- **Release notes** — structured from git history, grouped by feature / fix / performance
- **Interactive HTML dashboard** — four Chart.js charts, no server needed, opens in any browser
- **Provider-agnostic** — powered by LangChain; swap models via env vars without touching the code

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/daniele-angeli-dev/vox-populi
cd vox-populi

# 2. Create virtual environment
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1
# Mac/Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
cp .env.example .env
# Set MODEL_PROVIDER and the matching API key in .env
# Default: MODEL_PROVIDER=anthropic → set ANTHROPIC_API_KEY
```

---

## Usage

```bash
# Interactive wizard (recommended)
python main.py

# Analyze reviews from a store URL
python main.py --command analyze --store https://apps.apple.com/app/id123456789

# Analyze from a local file
python main.py --command analyze --file samples/reviews.csv

# Generate release notes + auto-replies
python main.py --command release --repo C:\path\to\myapp --store https://apps.apple.com/...

# Historical dashboard only
python main.py --command dashboard --store https://play.google.com/... --max-reviews 100
```

---

## All options

| Option | Description |
|--------|-------------|
| `--command analyze\|release\|dashboard` | Run a specific phase (omit to launch the wizard) |
| `--file PATH` | Local reviews file (CSV or JSON) |
| `--store URL` | App Store or Google Play URL (auto-detected) |
| `--max-reviews N` | Max reviews to fetch from store (default: 500) |
| `--repo PATH` | Git repo path for release notes |
| `--git-log PATH` | Pre-exported git log file (alternative to `--repo`) |

---

## Example output

```
🔮 vox-populi — command: analyze

──────────────────────────────────────────────────
🏪 Loading reviews from store: https://apps.apple.com/app/id123456789
  🍎 App Store — app ID: 123456789 (max 200 reviews)
✅ Loaded 200 reviews
🔍 Analyzing 200 reviews with claude-sonnet-4-6...
✅ Analysis complete
📝 Generating report...
✅ Report saved to: reports/report_20260614_175129.md
──────────────────────────────────────────────────

✅ Done! 9 fixes identified.
📁 Check reports/ for the full report.

🛠  Top 3 most urgent fixes:
   1. Fix critical crash on app launch in v2.1.0 — 16h
   2. Restore social login functionality (Google & Facebook) — 8h
   3. Fix crash when opening the user profile section — 6h
```

The full report includes sentiment breakdown, category analysis, recurring patterns, and the complete fix list with effort estimates.

---

## What it actually generates

Running against a sample dataset of 25 reviews, vox-populi autonomously produced:

**Sentiment breakdown:** 10 positive / 12 negative / 3 neutral

**Recurring patterns identified:**
- App crashes on launch after v2.1.0 update — appears 8 times (critical)
- Social login (Google & Facebook) broken — appears 6 times (high)
- Profile screen blank or missing after update — appears 5 times (high)
- Push notifications not delivered — appears 4 times (medium)

**Top fix from the prioritized list:**
> **Fix critical crash on app launch in v2.1.0** — 16h estimate
> Crash reproducible on cold start after updating to v2.1.0. Affects all devices. Related to 8 reviews.

**Auto-generated reply (Empathetic tone):**
> *"Thank you for taking the time to leave this review — we're truly sorry for the experience you had after updating to v2.1.0. The crash on launch is a known issue we identified shortly after release, and our team is working on a fix as the top priority. We expect to have it out within the next few days. We appreciate your patience."*

Zero hardcoded logic. The LLM reasoned about each review and produced the output from scratch.

---

## Project structure

```
vox-populi/
├── main.py       # CLI + wizard
├── agent.py      # LangGraph graph definition
├── state.py      # shared state between nodes
├── nodes.py      # all graph nodes (Phase 1, 2, 3)
├── tools.py      # I/O: file loading, store scraping, report writing
├── prompts.py    # LLM prompts
├── samples/      # test data (reviews.csv, git_log.txt, reviews_history.csv)
└── reports/      # generated output (gitignored)
```

---

## Switching models

vox-populi uses [LangChain](https://github.com/langchain-ai/langchain) — swap providers without changing any code:

```bash
# Use GPT-4o instead
MODEL_PROVIDER=openai MODEL=gpt-4o python main.py --command analyze --file samples/reviews.csv

# Use Gemini
MODEL_PROVIDER=google-genai MODEL=gemini-1.5-pro python main.py --command analyze --file samples/reviews.csv

# Use Groq (fast + cheap)
MODEL_PROVIDER=groq MODEL=llama-3.3-70b-versatile python main.py --command analyze --file samples/reviews.csv
```

Install the matching provider package first:
```bash
pip install langchain-openai      # OpenAI
pip install langchain-google-genai # Gemini
pip install langchain-groq        # Groq
```

---

## Store limits

| Store | Default | Hard limit |
|-------|---------|------------|
| App Store | 500 | ~500 (iTunes RSS, 10 pages × 50) |
| Google Play | 500 | ~3000+ (above that, it slows down) |

---

## Key concepts demonstrated

- **LangGraph** — multi-node graph with conditional routing across three phases
- **Agentic analysis** — LLM as reasoning engine over unstructured user feedback
- **Store scraping** — iTunes RSS API (no auth) + `google-play-scraper`
- **Dynamic prompting** — tone injected at runtime into the reply prompt
- **Pure Python aggregation** — dashboard stats computed without LLM calls
- **Interactive CLI** — `questionary` for guided wizard UX
- **Provider abstraction** — LangChain for model-agnostic integration

---

## Tech stack

- Python 3.10+
- [LangGraph](https://github.com/langchain-ai/langgraph) — agent graph framework
- [LangChain](https://github.com/langchain-ai/langchain) — provider-agnostic LLM client (Anthropic, OpenAI, Groq, Gemini, Ollama…)
- [Chart.js](https://www.chartjs.org) — embedded in the generated HTML dashboard
- [google-play-scraper](https://github.com/JoMingyu/google-play-scraper) — Play Store reviews
- [questionary](https://github.com/tmbo/questionary) — interactive CLI prompts
- [python-dotenv](https://github.com/theskumar/python-dotenv) — environment config

---

## Roadmap

- [ ] Exit code support for CI/CD (`0` = no critical issues, `1` = critical issues found)
- [ ] YAML support for App Store Connect API (higher review limits)
- [ ] Slack / webhook notification with report summary
- [ ] Multi-app comparison (same analysis across two different app IDs)
- [ ] Reply export in CSV format (ready to paste into store console)
