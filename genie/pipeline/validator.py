"""Configuration validation module."""

import os
import json
from pathlib import Path
from typing import Optional

from genie.validation import TableValidator
from genie.validation.table_validator import ValidationReport


def remove_self_joins(config_path: str) -> int:
    """
    Remove self-join specifications from config (where left_table == right_table).
    Modifies the config file in place.

    Args:
        config_path: Path to config JSON file

    Returns:
        Number of self-joins removed
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Get the genie config
    if "genie_space_config" in config:
        genie_config = config["genie_space_config"]
    else:
        genie_config = config

    # Get join specifications
    join_specs = genie_config.get("join_specifications", [])
    if not join_specs:
        return 0

    # Filter out self-joins
    original_count = len(join_specs)
    filtered_joins = [
        j for j in join_specs
        if j.get("left_table") != j.get("right_table")
    ]
    removed_count = original_count - len(filtered_joins)

    if removed_count > 0:
        # Update config
        genie_config["join_specifications"] = filtered_joins

        # Save back
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    return removed_count


def validate_config(
    config_path: str = "output/genie_space_config.json",
    databricks_host: Optional[str] = None,
    databricks_token: Optional[str] = None,
    fallback_token: Optional[str] = None,
    verbose: bool = True
) -> ValidationReport:
    """
    Validate tables in Genie space configuration.

    This function:
    1. Removes self-joins (where left_table == right_table)
    2. Checks that all tables exist in Unity Catalog

    Args:
        config_path: Path to Genie space configuration file
        databricks_host: Databricks workspace URL (overrides env var)
        databricks_token: Databricks personal access token (overrides env var)
        verbose: Print progress messages

    Returns:
        ValidationReport: Validation results with details

    Raises:
        ValueError: If credentials are missing or config file not found
        Exception: If validation fails
    """
    # Get credentials
    host = databricks_host or os.getenv("DATABRICKS_HOST")
    token = databricks_token or os.getenv("DATABRICKS_TOKEN")

    if not host:
        raise ValueError(
            "DATABRICKS_HOST must be set. "
            "Either set environment variable or pass as argument."
        )

    if not token:
        raise ValueError(
            "DATABRICKS_TOKEN must be set. "
            "Either set environment variable or pass as argument."
        )

    # Check config file exists
    config_path_obj = Path(config_path)
    if not config_path_obj.exists():
        raise ValueError(f"Configuration file not found: {config_path}")

    if verbose:
        print(f"✓ Validating configuration...")
        print(f"   Config: {config_path}")

    # Step 1: Remove self-joins silently
    removed_self_joins = remove_self_joins(config_path)
    if verbose and removed_self_joins > 0:
        print(f"   Removed {removed_self_joins} self-join(s)")

    # Step 2: Validate table existence only (simplified)
    # Initialize validator with optional fallback token for when user token lacks scopes
    validator = TableValidator(
        databricks_host=host,
        databricks_token=token,
        fallback_token=fallback_token
    )

    # Run validation (tables only, no columns)
    report = validator.validate_tables_only(config_path)

    if verbose:
        # Print summary
        total_tables = len(report.tables_checked)
        valid_tables = len(report.tables_valid)

        print(f"   Tables: {valid_tables}/{total_tables} exist in Unity Catalog")

        if report.has_errors():
            print(f"   ❌ {len([i for i in report.issues if i.severity == 'error'])} errors found")

        if not report.has_errors():
            print(f"   ✓ Validation passed!")

    return report
