"""Genie space deployment module."""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from genie.api.genie_space_client import GenieSpaceClient


def deploy_space(
    config_path: str = "output/genie_space_config.json",
    databricks_host: Optional[str] = None,
    databricks_token: Optional[str] = None,
    parent_path: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Deploy Genie space from configuration.
    
    This function creates a Genie space in your Databricks workspace using
    the provided configuration file.
    
    Args:
        config_path: Path to Genie space configuration file
        databricks_host: Databricks workspace URL (overrides env var)
        databricks_token: Databricks personal access token (overrides env var)
        parent_path: Optional parent workspace path for the space
        verbose: Print progress messages
        
    Returns:
        dict: Result containing space_id and space_url
        
    Raises:
        ValueError: If credentials are missing or config file not found
        Exception: If deployment fails
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
        print(f"🚀 Deploying Genie space...")
        print(f"   Config: {config_path}")
    
    # Load configuration
    with open(config_path_obj, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    
    # Initialize client
    client = GenieSpaceClient(
        databricks_host=host,
        databricks_token=token
    )
    
    # Create space
    if verbose:
        print(f"   Creating space via API...")
    
    response = client.create_space(
        config=config_data,
        parent_path=parent_path,
        verbose=verbose
    )
    
    space_id = response.get("space_id")
    space_url = client.get_space_url(space_id)
    
    result = {
        "space_id": space_id,
        "space_url": space_url,
        "response": response
    }
    
    if verbose:
        print(f"   ✓ Space created successfully!")
        print(f"   Space ID: {space_id}")
        print(f"   Space URL: {space_url}")
    
    return result
