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
import sys
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
        print(result)

if __name__ == "__main__":
    main()

EOFError = type('EOFError', (), {})  # auto-stub: not found in project

KeyboardInterrupt = type('KeyboardInterrupt', (), {})  # auto-stub: not found in project
