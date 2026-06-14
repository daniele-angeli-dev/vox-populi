"""
main.py — vox-populi CLI entry point.

Quick start (interactive wizard):
    python main.py

Advanced usage:
    python main.py --command analyze --file samples/reviews.csv
    python main.py --command analyze --store https://apps.apple.com/...
    python main.py --command release --git-log samples/git_log.txt --store https://...
    python main.py --command dashboard --file samples/reviews_history.csv
"""
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

TONES = [
    ("Formal",     "professional and detached"),
    ("Friendly",   "warm and close to the user"),
    ("Direct",     "short and to the point"),
    ("Empathetic", "understanding, acknowledges the issue"),
]


def ask_tone() -> str:
    """Interactive menu for selecting the reply tone."""
    try:
        import questionary
        choices = [
            questionary.Choice(title=f"{name} — {desc}", value=name)
            for name, desc in TONES
        ]
        return questionary.select("🎭 Reply tone:", choices=choices).ask() or "Formal"
    except ImportError:
        print("\n🎭 Choose reply tone:")
        for i, (name, desc) in enumerate(TONES, 1):
            print(f"  {i}. {name} — {desc}")
        while True:
            choice = input("\nNumber (1-4): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(TONES):
                return TONES[int(choice) - 1][0]
            print("Invalid choice.")


def ask_int(prompt: str, default: int) -> int:
    try:
        import questionary
        raw = questionary.text(prompt, default=str(default)).ask()
    except ImportError:
        raw = input(f"{prompt} (default {default}): ").strip()
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def ask_confirm(prompt: str, default: bool = True) -> bool:
    try:
        import questionary
        return questionary.confirm(prompt, default=default).ask()
    except ImportError:
        suffix = "[Y/n]" if default else "[y/N]"
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default
        return raw in ("y", "yes")


# ── Wizard ────────────────────────────────────────────────────────────────────

def wizard_mode(graph):
    """
    Interactive mode: guides the user through all options,
    then runs the agent with the chosen settings.
    """
    print("\n🔮 vox-populi — wizard\n")
    print("─" * 50)

    # 1. App link
    try:
        import questionary
        store_url = questionary.text("🔗 App link (App Store or Google Play):").ask()
    except ImportError:
        store_url = input("🔗 App link (App Store or Google Play): ").strip()

    if not store_url:
        print("❌ No link provided. Exiting.")
        return

    # Validate URL
    from tools import parse_store_url
    try:
        store_type, app_id = parse_store_url(store_url)
        store_label = "🍎 App Store" if store_type == "appstore" else "🤖 Google Play"
        print(f"  ✅ Detected: {store_label} — ID: {app_id}\n")
    except ValueError as e:
        print(f"  ❌ {e}")
        return

    # 2. Max reviews
    max_reviews = ask_int("📊 How many reviews do you want to analyze?", default=500)

    # 3. HTML dashboard
    want_dashboard = ask_confirm("📈 Generate an HTML dashboard?", default=True)

    # 4. Reply tone
    tone = ask_tone()

    print()
    print("─" * 50)

    initial_state = {
        "command":      "wizard",
        "error":        None,
        "reviews_file": "",
        "store_url":    store_url,
        "max_reviews":  max_reviews,
        "reviews":      [],
        "analysis":     {},
        "report":       "",
        "fixes":        [],
        "repo_path":    "",
        "git_log_file": "",
        "git_log":      "",
        "tone":         tone,
        "release_notes_data": {},
        "release_notes":      "",
        "replies":      [],
        "want_dashboard": want_dashboard,
        "stats":        {},
        "html":         "",
    }

    result = graph.invoke(initial_state)

    print("─" * 50)

    if result.get("error"):
        print(f"\n❌ Error: {result['error']}")
        return

    fixes   = result.get("fixes",   [])
    replies = result.get("replies", [])

    print(f"\n✅ All done!")
    print(f"   📋 {len(fixes)} fixes identified")
    print(f"   💬 {len(replies)} replies generated (tone: {tone})")
    if want_dashboard:
        print("   📊 HTML dashboard generated")
    print("\n📁 Check the reports/ folder for all output files.\n")

    if fixes:
        print("🛠  Top 3 most urgent fixes:")
        for fix in fixes[:3]:
            print(f"   {fix.get('priority')}. {fix.get('title')} — {fix.get('estimated_hours')}h")
        print()


# ── Advanced mode (flags) ─────────────────────────────────────────────────────

def advanced_mode(args, graph):
    from tools import load_reviews_from_file, load_reviews_from_store

    reviews_source = args.file or args.store

    # Validations
    if args.command == "analyze" and not reviews_source:
        print("❌ --file or --store is required for 'analyze'")
        return
    if args.command == "release" and not args.repo and not args.git_log_file:
        print("❌ --repo or --git-log is required for 'release'")
        return
    if args.command == "dashboard" and not reviews_source:
        print("❌ --file or --store is required for 'dashboard'")
        return

    print(f"\n🔮 vox-populi — command: {args.command}\n")
    print("─" * 50)

    # Ask for tone only when release has a reviews source
    tone = "Formal"
    if args.command == "release" and reviews_source:
        tone = ask_tone()
        print()

    # Pre-load reviews for release (load_reviews_node is not in the release flow)
    preloaded_reviews = []
    if args.command == "release" and reviews_source:
        if args.store:
            print(f"🏪 Loading reviews from store: {args.store}")
            preloaded_reviews = load_reviews_from_store(args.store, max_reviews=args.max_reviews)
        else:
            print(f"📂 Loading reviews from: {args.file}")
            preloaded_reviews = load_reviews_from_file(args.file)
        print(f"✅ Loaded {len(preloaded_reviews)} reviews\n")

    initial_state = {
        "command":      args.command,
        "error":        None,
        "reviews_file": args.file or "",
        "store_url":    args.store or "",
        "max_reviews":  args.max_reviews,
        "reviews":      preloaded_reviews,
        "analysis":     {},
        "report":       "",
        "fixes":        [],
        "repo_path":    args.repo or "",
        "git_log_file": args.git_log_file or "",
        "git_log":      "",
        "tone":         tone,
        "release_notes_data": {},
        "release_notes":      "",
        "replies":      [],
        "want_dashboard": False,
        "stats":        {},
        "html":         "",
    }

    result = graph.invoke(initial_state)

    print("─" * 50)

    if result.get("error"):
        print(f"\n❌ Error: {result['error']}")
        return

    if args.command == "analyze":
        fixes = result.get("fixes", [])
        print(f"\n✅ Done! {len(fixes)} fixes identified.")
        print("📁 Check reports/ for the full report.\n")
        if fixes:
            print("🛠  Top 3 most urgent fixes:")
            for fix in fixes[:3]:
                print(f"   {fix.get('priority')}. {fix.get('title')} — {fix.get('estimated_hours')}h")

    elif args.command == "release":
        replies = result.get("replies", [])
        rn_data = result.get("release_notes_data", {})
        print(f"\n✅ Done!")
        print(f"📦 Release notes: {rn_data.get('version', 'latest')}")
        if replies:
            print(f"💬 {len(replies)} replies generated (tone: {tone})")
        print("📁 Check reports/ for the full output.\n")

    elif args.command == "dashboard":
        stats = result.get("stats", {})
        print(f"\n✅ Done!")
        print(f"📊 {stats.get('total_reviews', 0)} reviews across {len(stats.get('versions', []))} versions")
        print("🌐 Open the .html file in reports/ in your browser.\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    provider = os.getenv("MODEL_PROVIDER", "anthropic").lower()
    key_map = {
        "anthropic":   "ANTHROPIC_API_KEY",
        "openai":      "OPENAI_API_KEY",
        "groq":        "GROQ_API_KEY",
        "google-genai": "GOOGLE_API_KEY",
    }
    required_key = key_map.get(provider)
    if required_key and not os.getenv(required_key):
        print(f"❌ {required_key} not found in .env. Set MODEL_PROVIDER={provider} and add the key.")
        return

    parser = argparse.ArgumentParser(
        prog="vox-populi",
        description="🔮 vox-populi — the voice of the people, at your service",
    )
    parser.add_argument(
        "--command",
        choices=["analyze", "release", "dashboard"],
        help="Specific command to run (omit to launch the interactive wizard)",
    )
    parser.add_argument("--file",    help="Path to local reviews file (CSV or JSON)")
    parser.add_argument("--store",   help="App Store or Google Play URL")
    parser.add_argument("--repo",    help="Git repo path (for 'release')")
    parser.add_argument(
        "--git-log",
        dest="git_log_file",
        help="Path to a pre-exported git log file (alternative to --repo)",
    )
    parser.add_argument(
        "--max-reviews",
        dest="max_reviews",
        type=int,
        default=500,
        help="Max reviews to fetch from store (default: 500)",
    )

    args = parser.parse_args()

    if args.file and args.store:
        parser.error("--file and --store are mutually exclusive")

    from agent import build_graph
    graph = build_graph()

    if args.command is None:
        wizard_mode(graph)
    else:
        advanced_mode(args, graph)


if __name__ == "__main__":
    main()
