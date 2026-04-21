"""Distribute Skill - wrapper for organizer agent."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.organizer import run as organizer_run
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Main entry point for distribute skill."""
    import argparse
    parser = argparse.ArgumentParser(description="Distribute articles to Telegram or Feishu")
    parser.add_argument("--platform", default="telegram", help="Platform: telegram, feishu, or none")
    args = parser.parse_args()

    items = organizer_run(args.platform)
    logger.info(f"Distribute skill completed: {len(items)} items")


if __name__ == "__main__":
    main()