"""Folder structure management service."""

from pathlib import Path
from typing import List


# Standard folder structure for iterations
ITERATION_FOLDERS = [
    "results",
    "reports",
    "source_data/instances",
    "source_data/holdings",
    "source_data/items",
    "source_data/users",
    "source_data/loans",
    "source_data/courses",
]


def create_iteration_folders(base_path: Path, iteration_name: str) -> Path:
    """
    Create the standard folder structure for a migration iteration.

    Args:
        base_path: The client project base directory
        iteration_name: Name of the iteration (e.g., "thu_migration")

    Returns:
        Path to the created iteration directory
    """
    iteration_path = base_path / "iterations" / iteration_name

    for folder in ITERATION_FOLDERS:
        folder_path = iteration_path / folder
        folder_path.mkdir(parents=True, exist_ok=True)

    return iteration_path


def get_iteration_folders(client_path: Path) -> List[str]:
    """
    Get list of iteration folder names for a client.

    Args:
        client_path: The client project directory

    Returns:
        List of iteration names
    """
    iterations_path = client_path / "iterations"
    if not iterations_path.exists():
        return []

    return [
        d.name
        for d in iterations_path.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]


def get_source_data_folders(client_path: Path, iteration: str) -> dict:
    """
    Get information about source data folders for an iteration.

    Returns dict with folder name -> file count mapping.
    """
    source_data_path = client_path / "iterations" / iteration / "source_data"
    if not source_data_path.exists():
        return {}

    result = {}
    for folder in source_data_path.iterdir():
        if folder.is_dir():
            files = list(folder.glob("*"))
            result[folder.name] = {
                "file_count": len([f for f in files if f.is_file()]),
                "files": [f.name for f in files if f.is_file()][:10],  # First 10 files
            }

    return result
