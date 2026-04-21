"""Analyze Skill - wrapper for analyzer agent."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.analyzer import run as analyzer_run
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Main entry point for analyze skill."""
    import argparse
    parser = argparse.ArgumentParser(description="Analyze collected content")
    parser.add_argument("--source", default=None, help="Source directory")
    args = parser.parse_args()

    items = analyzer_run(args.source)
    logger.info(f"Analyze skill completed: {len(items)} items")


if __name__ == "__main__":
    main()