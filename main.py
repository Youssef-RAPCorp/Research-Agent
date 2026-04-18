#!/usr/bin/env python3
"""
Physics Discovery System v3.0 — Entry Point
RAP Corp | Renaissance of American Physics

Usage:
    python main.py                                    # interactive mode
    python main.py "query"                            # single query
    python main.py "hypothesis" --mode discovery      # discovery mode
    python main.py --overnight                        # start overnight scheduler
    python main.py "query" --pattern lats_mcts        # specific thinking pattern
"""

import asyncio
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def main():
    parser = argparse.ArgumentParser(
        description="Physics Discovery System v3.0"
    )
    parser.add_argument("query", nargs="?", help="Research query or hypothesis")
    parser.add_argument("--mode", choices=["quick","standard","comprehensive","deep","discovery"],
                        default="standard")
    parser.add_argument("--pattern",
                        choices=["self_refine","reflection","reflexion_vrl","tree_of_thoughts",
                                 "lats_mcts","multi_agent_debate","chat_eval","down_adaptive"],
                        default="down_adaptive",
                        help="Thinking pattern to use")
    parser.add_argument("--overnight", action="store_true",
                        help="Start the continuous overnight discovery scheduler")
    parser.add_argument("--output", metavar="FILE",
                        help="Save results to this file (default: auto-named in results/)")
    parser.add_argument("--no-save", action="store_true",
                        help="Do not save results to disk (terminal only)")
    args = parser.parse_args()

    print("\n+==========================================+")
    print("|  Physics Discovery System v3.0           |")
    print("|  RAPCorp | Renaissance of American Physics  |")
    print("+==========================================+\n")

    if args.overnight:
        print("Starting overnight discovery scheduler...")
        print("Press Ctrl+C to stop.\n")
        from discovery.scheduler import DiscoveryScheduler
        async def _run_overnight():
            _sched = DiscoveryScheduler()
            await _sched.start()
            try:
                while True:
                    await asyncio.sleep(60)
            except (asyncio.CancelledError, KeyboardInterrupt):
                await _sched.stop()
        asyncio.run(_run_overnight())
        return

    if not args.query:
        print("Interactive mode — type your physics query:")
        print("  Examples:")
        print("  • Are Maxwell\'s equations complete at high energies?")
        print("  • Derive quantum corrections to gravity from first principles")
        print("  • What if dark matter is emergent from modified gravity?\n")
        try:
            query = input("Query > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return
    else:
        query = args.query

    print(f"\nMode: {args.mode} | Pattern: {args.pattern}")
    print(f"Query: {query}\n")

    try:
        from agents.orchestrator import PhysicsOrchestrator
    except ImportError as e:
        print("[ Orchestrator not yet connected — run the installer to generate all modules ]")
        print(f"[ Import error: {e} ]")
        return

    orchestrator = PhysicsOrchestrator()
    try:
        result = asyncio.run(orchestrator.run(
            query=query,
            mode=args.mode,
            pattern=args.pattern,
        ))
    except TypeError:
        # Fallback if orchestrator uses positional args or sync interface
        result = orchestrator.run(query=query, mode=args.mode, pattern=args.pattern)

    if result:
        try:
            print(result)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((str(result) + '\n').encode('utf-8', errors='replace'))

        if not args.no_save:
            _save_result(result, query, args)

def _save_result(result, query: str, args) -> None:
    """Save result dict (or string) to results/ as .json + .md"""
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = "".join(c if c.isalnum() else "_" for c in query[:40]).strip("_")

    if args.output:
        base = Path(args.output).with_suffix("")
    else:
        base = results_dir / f"{timestamp}_{slug}"

    # ── JSON ──────────────────────────────────────────────────────────────────
    json_path = base.with_suffix(".json")
    try:
        data = result if isinstance(result, dict) else {"output": str(result)}
        data.setdefault("query", query)
        data.setdefault("timestamp", timestamp)
        json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        print(f"\n[output] Could not write JSON: {e}")
        return

    # ── Markdown ──────────────────────────────────────────────────────────────
    md_path = base.with_suffix(".md")
    try:
        lines = [
            f"# Physics Research Report",
            f"",
            f"**Query:** {query}  ",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
            f"**Mode:** {getattr(args, 'mode', '—')} | **Pattern:** {getattr(args, 'pattern', '—')}  ",
            f"",
        ]
        if isinstance(result, dict):
            content = result.get("content", "")
            confidence = result.get("confidence")
            key_findings = result.get("insights", {}).get("key_findings", []) if isinstance(result.get("insights"), dict) else []

            if content:
                lines.append(content)
                lines.append("")
            if key_findings:
                lines.append("## Key Findings")
                for f in key_findings:
                    lines.append(f"- {f}")
                lines.append("")
            if confidence is not None:
                lines.append(f"**Confidence:** {confidence:.0%}")
        else:
            lines.append(str(result))

        md_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as e:
        print(f"\n[output] Could not write Markdown: {e}")
        return

    print(f"\n[output] Saved → {json_path}")
    print(f"[output]         {md_path}")


if __name__ == "__main__":
    main()

EOFError = type('EOFError', (), {})  # auto-stub: not found in project

KeyboardInterrupt = type('KeyboardInterrupt', (), {})  # auto-stub: not found in project

UnicodeEncodeError = type('UnicodeEncodeError', (), {})  # auto-stub: not found in project
