"""Collect Skill - wrapper for collector agent."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.collector import run as collector_run
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Main entry point for collect skill."""
    import argparse
    parser = argparse.ArgumentParser(description="Collect AI content from GitHub and HN")
    parser.add_argument("--source", default="all", help="Source: github,hn or all")
    parser.add_argument("--limit", type=int, default=10, help="Maximum items per source")
    args = parser.parse_args()

    items = collector_run(args.source, args.limit)
    logger.info(f"Collect skill completed: {len(items)} items")


if __name__ == "__main__":
    main()