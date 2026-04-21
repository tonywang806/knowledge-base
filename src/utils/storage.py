"""Storage utility module."""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from config import RAW_DIR, ARTICLES_DIR
from utils.logger import get_logger

logger = get_logger(__name__)


def generate_id() -> str:
    """Generate a unique UUID."""
    return str(uuid.uuid4())


def get_timestamp() -> str:
    """Get current timestamp in ISO8601 format."""
    return datetime.now().isoformat()


def save_json(data: dict, directory: Path, prefix: str = "") -> Path:
    """Save data as JSON file.

    Args:
        data: Data to save.
        directory: Target directory.
        prefix: Filename prefix.

    Returns:
        Path to saved file.
    """
    directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"{prefix}{timestamp}-{generate_id()[:8]}.json" if prefix else f"{timestamp}-{generate_id()[:8]}.json"
    filepath = directory / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved to {filepath}")
    return filepath


def load_json(filepath: Path) -> dict:
    """Load data from JSON file.

    Args:
        filepath: Path to JSON file.

    Returns:
        Loaded data.
    """
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def list_files(directory: Path, pattern: str = "*.json") -> list[Path]:
    """List JSON files in directory.

    Args:
        directory: Directory to search.
        pattern: File pattern.

    Returns:
        List of file paths.
    """
    if not directory.exists():
        return []
    return sorted(directory.glob(pattern), reverse=True)


def read_pending_items(source_dir: Path) -> list[dict]:
    """Read all pending items from directory.

    Args:
        source_dir: Source directory.

    Returns:
        List of pending items.
    """
    items = []
    for filepath in list_files(source_dir):
        data = load_json(filepath)
        if data.get("status") == "pending":
            data["_filepath"] = filepath
            items.append(data)
    return items


def update_item_status(item: dict, status: str) -> dict:
    """Update item status.

    Args:
        item: Item to update.
        status: New status.

    Returns:
        Updated item.
    """
    item["status"] = status
    item["updated_at"] = get_timestamp()
    return item