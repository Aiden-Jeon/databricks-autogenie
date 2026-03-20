"""Load benchmark questions from structured JSON files.

This module loads pre-defined benchmark questions from JSON files that have been
curated separately from the requirements document. This allows for maintaining
a separate set of high-quality benchmark questions with expected SQL queries.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional


def load_benchmarks_from_json(
    benchmarks_path: str,
    verbose: bool = True
) -> List[Dict[str, Any]]:
    """
    Load benchmark questions from a JSON file.
    
    The JSON file should have the following structure:
    {
        "benchmarks": [
            {
                "id": "unique_id",
                "question": "English question",
                "expected_sql": "SQL query",
                "korean_question": "Korean translation",
                "source_file": "source.md",
                "question_number": 1
            },
            ...
        ],
        "metadata": {
            "total_count": 20,
            "source_files": ["file1.md", "file2.md"]
        }
    }
    
    The function transforms the benchmarks into the format expected by GenieSpaceBenchmark:
    {
        "question": "English question",
        "expected_sql": "SQL query",
        "expected_accuracy": None
    }
    
    Args:
        benchmarks_path: Path to the benchmarks JSON file
        verbose: Print progress messages
        
    Returns:
        List of benchmark dictionaries in GenieSpaceBenchmark format
        
    Raises:
        FileNotFoundError: If benchmarks file doesn't exist
        ValueError: If JSON structure is invalid
        
    Example:
        >>> benchmarks = load_benchmarks_from_json("real_requirements/benchmarks/benchmarks.json")
        >>> len(benchmarks)
        20
        >>> benchmarks[0]
        {
            "question": "What are the Discord messages with the most reactions?",
            "expected_sql": "SELECT ...",
            "expected_accuracy": None
        }
    """
    benchmark_path = Path(benchmarks_path)
    
    if not benchmark_path.exists():
        raise FileNotFoundError(f"Benchmarks file not found: {benchmarks_path}")
    
    if verbose:
        print(f"\n📊 Loading benchmarks from {benchmarks_path}...")
    
    # Load JSON file
    with open(benchmark_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Validate structure
    if "benchmarks" not in data:
        raise ValueError(
            f"Invalid benchmark JSON structure. Expected 'benchmarks' key, "
            f"but found: {list(data.keys())}"
        )
    
    benchmarks = data["benchmarks"]
    
    if not isinstance(benchmarks, list):
        raise ValueError(
            f"Expected 'benchmarks' to be a list, but got: {type(benchmarks)}"
        )
    
    # Transform to GenieSpaceBenchmark format
    transformed_benchmarks = []
    for idx, benchmark in enumerate(benchmarks, 1):
        # Validate required fields
        if "question" not in benchmark:
            raise ValueError(
                f"Benchmark {idx} missing required 'question' field. "
                f"Available fields: {list(benchmark.keys())}"
            )
        
        # Transform to expected format
        transformed = {
            "question": benchmark["question"],
            "expected_sql": benchmark.get("expected_sql"),
            "expected_accuracy": None  # Not used in current format
        }
        
        transformed_benchmarks.append(transformed)
    
    if verbose:
        print(f"   ✓ Loaded {len(transformed_benchmarks)} benchmarks")
        
        # Print metadata if available
        if "metadata" in data:
            metadata = data["metadata"]
            if "source_files" in metadata:
                print(f"   ✓ Source files: {', '.join(metadata['source_files'])}")
    
    return transformed_benchmarks


def find_benchmarks_file(
    requirements_path: str,
    verbose: bool = True
) -> Optional[str]:
    """
    Find benchmarks JSON file relative to requirements path.
    
    This function looks for a benchmarks.json file in the following locations:
    1. {requirements_dir}/benchmarks/benchmarks.json
    2. {requirements_dir}/../benchmarks/benchmarks.json
    
    Args:
        requirements_path: Path to requirements document or directory
        verbose: Print search messages
        
    Returns:
        Path to benchmarks.json if found, None otherwise
        
    Example:
        >>> find_benchmarks_file("real_requirements/inputs/doc.pdf")
        "real_requirements/benchmarks/benchmarks.json"
    """
    req_path = Path(requirements_path)
    
    # Determine base directory
    if req_path.is_file():
        base_dir = req_path.parent
    else:
        base_dir = req_path
    
    # Search locations (in order of priority)
    search_paths = [
        base_dir / "benchmarks" / "benchmarks.json",  # Same level
        base_dir.parent / "benchmarks" / "benchmarks.json",  # One level up
    ]
    
    if verbose:
        print(f"\n🔍 Searching for benchmarks file...")
    
    for search_path in search_paths:
        if search_path.exists():
            if verbose:
                print(f"   ✓ Found: {search_path}")
            return str(search_path)
    
    if verbose:
        print(f"   ℹ No benchmarks file found in:")
        for search_path in search_paths:
            print(f"      - {search_path}")
    
    return None


def load_benchmarks_auto(
    requirements_path: str,
    verbose: bool = True
) -> Optional[List[Dict[str, Any]]]:
    """
    Automatically find and load benchmarks relative to requirements path.
    
    This is a convenience function that combines find_benchmarks_file()
    and load_benchmarks_from_json().
    
    Args:
        requirements_path: Path to requirements document or directory
        verbose: Print progress messages
        
    Returns:
        List of benchmarks if found, None otherwise
        
    Example:
        >>> benchmarks = load_benchmarks_auto("real_requirements/inputs/doc.pdf")
        >>> if benchmarks:
        ...     print(f"Loaded {len(benchmarks)} benchmarks")
    """
    benchmarks_file = find_benchmarks_file(requirements_path, verbose=verbose)
    
    if benchmarks_file is None:
        return None
    
    try:
        return load_benchmarks_from_json(benchmarks_file, verbose=verbose)
    except Exception as e:
        if verbose:
            print(f"   ⚠️  Failed to load benchmarks: {e}")
        return None
