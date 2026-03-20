"""
Client for managing Databricks Genie Spaces via API.

API Reference: https://docs.databricks.com/api/workspace/genie

Key Requirements:
- All IDs must be 32-character lowercase hex (uuid.uuid4().hex)
- All ID-based arrays must be sorted by ID
- Tables sorted by identifier, columns sorted by column_name
- Text fields (description, question, sql, content) must be arrays of strings
- Join SQL should NOT include backticks
- Each SQL line should end with \n
"""

import os
import json
from typing import Optional, Dict, Any
import requests
from genie.utils.config_transformer import transform_to_serialized_space


class GenieSpaceClient:
    """Client for creating and managing Databricks Genie Spaces."""
    
    def __init__(
        self,
        databricks_host: Optional[str] = None,
        databricks_token: Optional[str] = None
    ):
        """
        Initialize the Genie Space client.

        Args:
            databricks_host: Databricks workspace URL (defaults to DATABRICKS_HOST env var)
            databricks_token: Databricks personal access token (defaults to DATABRICKS_TOKEN env var)
        """
        self.databricks_host = databricks_host or os.getenv("DATABRICKS_HOST")
        self.databricks_token = databricks_token or os.getenv("DATABRICKS_TOKEN")

        if not self.databricks_host:
            raise ValueError("databricks_host must be provided or DATABRICKS_HOST env var must be set")
        if not self.databricks_token:
            raise ValueError("databricks_token must be provided or DATABRICKS_TOKEN env var must be set")

        # Clean up host URL
        self.databricks_host = self.databricks_host.rstrip('/')
        if not self.databricks_host.startswith('http'):
            self.databricks_host = f"https://{self.databricks_host}"

        # Genie Spaces API endpoint
        self.api_base = f"{self.databricks_host}/api/2.0/genie/spaces"

        # Cache for organization ID
        self._org_id = None
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {self.databricks_token}",
            "Content-Type": "application/json"
        }

    def get_organization_id(self) -> Optional[str]:
        """
        Get the organization ID for the current workspace.

        Returns:
            Organization ID or None if it cannot be retrieved
        """
        if self._org_id:
            return self._org_id

        try:
            # Try to get org ID from the current user's workspace info
            response = requests.get(
                f"{self.databricks_host}/api/2.0/preview/scim/v2/Me",
                headers=self._get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # Extract org ID from the response
            if "groups" in data:
                for group in data.get("groups", []):
                    if "value" in group and group["value"].startswith("org_"):
                        # Parse org ID from group name like "org_7474647945795688"
                        org_id = group["value"].replace("org_", "")
                        self._org_id = org_id
                        return org_id

            # Alternative: try to get from workspace API
            response = requests.get(
                f"{self.databricks_host}/api/2.0/workspace-conf",
                headers=self._get_headers(),
                params={"keys": "enableOrganizationId"},
                timeout=30
            )
            if response.ok:
                data = response.json()
                # Try to extract org ID if available
                pass

        except Exception:
            pass

        return None
    
    def get_available_warehouse(self) -> Optional[str]:
        """
        Get the first available SQL warehouse.
        
        Returns:
            Warehouse ID of the first available warehouse, or None if no warehouses found
            
        API Reference:
            https://docs.databricks.com/api/workspace/warehouses/list
        """
        try:
            response = requests.get(
                f"{self.databricks_host}/api/2.0/sql/warehouses",
                headers=self._get_headers(),
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            
            warehouses = data.get("warehouses", [])
            if not warehouses:
                return None
            
            # Prefer warehouses that are running, otherwise take the first one
            for warehouse in warehouses:
                if warehouse.get("state") == "RUNNING":
                    return warehouse.get("id")
            
            # If no running warehouse, return the first one
            return warehouses[0].get("id")
            
        except Exception:
            return None
    
    def create_space(
        self,
        config: Dict[str, Any],
        parent_path: Optional[str] = None,
        timeout: int = 300,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        Create a new Genie space.
        
        Args:
            config: Genie space configuration (should match GenieSpaceConfig schema)
            parent_path: Parent folder path where the space will be registered (optional)
            timeout: Request timeout in seconds
            verbose: Print informational messages (e.g., auto-selected warehouse)
            
        Returns:
            Response from the API containing space_id and other metadata
            
        Raises:
            requests.HTTPError: If the API request fails
            
        API Reference:
            https://docs.databricks.com/api/workspace/genie/createspace
        """
        # Extract just the genie_space_config if the full LLMResponse format is provided
        if "genie_space_config" in config:
            config = config["genie_space_config"]
        
        # Make a copy to avoid modifying the original
        config_copy = config.copy()
        
        # Extract required fields for the API
        warehouse_id = config_copy.get("warehouse_id")
        
        # Auto-fetch warehouse if not provided or placeholder
        if not warehouse_id or warehouse_id == "REPLACE_WITH_YOUR_SQL_WAREHOUSE_ID":
            if verbose:
                print("   No warehouse_id specified, fetching available warehouse...")
            
            warehouse_id = self.get_available_warehouse()
            
            if not warehouse_id:
                raise ValueError(
                    "No SQL warehouse found in your workspace. "
                    "Please create a SQL warehouse first or provide a warehouse_id in the configuration."
                )
            
            if verbose:
                print(f"   Auto-selected warehouse: {warehouse_id}")
        
        # Extract optional fields
        title = config_copy.get("space_name")
        description = config_copy.get("description")
        
        # Transform our config to Databricks serialized_space format
        serialized_space = transform_to_serialized_space(config_copy)
        
        # Debug: Save serialized space and full payload for debugging
        if verbose:
            try:
                debug_path = "output/debug_serialized_space.json"
                import os
                os.makedirs(os.path.dirname(debug_path), exist_ok=True)
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(serialized_space)
                print(f"   Debug: Saved serialized space to {debug_path}")

                # Also save the full API payload
                payload_debug_path = "output/debug_api_payload.json"
                with open(payload_debug_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        "warehouse_id": warehouse_id,
                        "title": title,
                        "description": description,
                        "parent_path": parent_path,
                        "serialized_space_length": len(serialized_space)
                    }, f, indent=2)
                print(f"   Debug: Saved API payload metadata to {payload_debug_path}")
            except Exception as e:
                print(f"   Warning: Failed to save debug files: {e}")
        
        # Build the API request payload according to Databricks API spec
        payload = {
            "warehouse_id": warehouse_id,
            "serialized_space": serialized_space,
        }
        
        if title:
            payload["title"] = title
        if description:
            payload["description"] = description
        if parent_path:
            payload["parent_path"] = parent_path
        
        response = requests.post(
            self.api_base,
            headers=self._get_headers(),
            json=payload,
            timeout=timeout
        )
        
        # Handle errors with more detailed information
        if not response.ok:
            error_msg = f"{response.status_code} {response.reason} for url: {response.url}"
            try:
                error_details = response.json()
                if "message" in error_details:
                    error_msg += f"\nAPI Error: {error_details['message']}"
                if "error_code" in error_details:
                    error_msg += f"\nError Code: {error_details['error_code']}"
                if "details" in error_details:
                    error_msg += f"\nDetails: {error_details['details']}"
            except:
                # If we can't parse JSON, include the raw text
                if response.text:
                    error_msg += f"\nResponse: {response.text[:500]}"
            
            raise requests.HTTPError(error_msg, response=response)
        
        return response.json()
    
    def get_space(
        self,
        space_id: str,
        include_serialized_space: bool = False
    ) -> Dict[str, Any]:
        """
        Get details of an existing Genie space.
        
        Args:
            space_id: The ID of the space to retrieve
            include_serialized_space: Whether to include the serialized space export in the response.
                                     Requires at least CAN EDIT permission on the space.
            
        Returns:
            Space details
            
        API Reference:
            https://docs.databricks.com/api/workspace/genie/getspace
        """
        params = {}
        if include_serialized_space:
            params["include_serialized_space"] = "true"
        
        response = requests.get(
            f"{self.api_base}/{space_id}",
            headers=self._get_headers(),
            params=params,
            timeout=60
        )
        
        response.raise_for_status()
        return response.json()
    
    def list_spaces(
        self,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List all Genie spaces in the workspace.
        
        Args:
            page_size: Maximum number of spaces to return per page (optional)
            page_token: Pagination token for getting the next page of results (optional)
        
        Returns:
            Dictionary containing:
            - spaces: List of space objects
            - next_page_token: Token for the next page (if available)
            
        API Reference:
            https://docs.databricks.com/api/workspace/genie/listspaces
        """
        params = {}
        if page_size is not None:
            params["page_size"] = page_size
        if page_token:
            params["page_token"] = page_token
        
        response = requests.get(
            self.api_base,
            headers=self._get_headers(),
            params=params,
            timeout=60
        )
        
        response.raise_for_status()
        return response.json()
    
    def update_space(
        self,
        space_id: str,
        config: Optional[Dict[str, Any]] = None,
        warehouse_id: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Update an existing Genie space.
        
        Note: All parameters are optional. Only provided fields will be updated.
        
        Args:
            space_id: The ID of the space to update
            config: Updated space configuration (optional). If provided, will update serialized_space.
            warehouse_id: Optional warehouse override
            title: Optional title override
            description: Optional description override
            timeout: Request timeout in seconds
            
        Returns:
            Response from the API
            
        API Reference:
            https://docs.databricks.com/api/workspace/genie/updatespace
        """
        # Build the API request payload
        payload = {}
        
        # Handle config-based update
        if config is not None:
            # Extract just the genie_space_config if the full LLMResponse format is provided
            if "genie_space_config" in config:
                config = config["genie_space_config"]
            
            # Make a copy to avoid modifying the original
            config_copy = config.copy()
            
            # Transform our config to Databricks serialized_space format
            serialized_space = transform_to_serialized_space(config_copy)
            payload["serialized_space"] = serialized_space
            
            # Extract fields from config if not provided as separate parameters
            if warehouse_id is None:
                warehouse_id = config_copy.get("warehouse_id")
            if title is None:
                title = config_copy.get("space_name")
            if description is None:
                description = config_copy.get("description")
        
        # Add optional fields if provided
        if warehouse_id and warehouse_id != "REPLACE_WITH_YOUR_SQL_WAREHOUSE_ID":
            payload["warehouse_id"] = warehouse_id
        if title:
            payload["title"] = title
        if description is not None:  # Allow empty string to clear description
            payload["description"] = description
        
        if not payload:
            raise ValueError("At least one field must be provided to update the space")
        
        response = requests.patch(
            f"{self.api_base}/{space_id}",
            headers=self._get_headers(),
            json=payload,
            timeout=timeout
        )
        
        response.raise_for_status()
        return response.json()
    
    def trash_space(self, space_id: str) -> None:
        """
        Move a Genie space to the trash.
        
        Note: This does not permanently delete the space, but moves it to trash
        where it can potentially be recovered.
        
        Args:
            space_id: The ID of the space to move to trash
            
        Returns:
            None
            
        API Reference:
            https://docs.databricks.com/api/workspace/genie/trashspace
        """
        response = requests.delete(
            f"{self.api_base}/{space_id}",
            headers=self._get_headers(),
            timeout=60
        )
        
        response.raise_for_status()
    
    def delete_space(self, space_id: str) -> None:
        """
        Move a Genie space to the trash.
        
        DEPRECATED: Use trash_space() instead. This method name is kept for
        backward compatibility but calls trash_space() internally.
        
        Note: This does not permanently delete the space, but moves it to trash
        where it can potentially be recovered.
        
        Args:
            space_id: The ID of the space to move to trash
        """
        return self.trash_space(space_id)
    
    def get_space_url(self, space_id: str) -> str:
        """
        Get the URL for accessing a Genie space.

        Args:
            space_id: The ID of the space

        Returns:
            Full URL to access the space in the Databricks UI
        """
        # Use /genie/rooms/ (correct UI endpoint) instead of /genie/spaces/
        base_url = f"{self.databricks_host}/genie/rooms/{space_id}"

        # Try to append organization ID if available
        org_id = self.get_organization_id()
        if org_id:
            base_url += f"?o={org_id}"

        return base_url
    
    def export_space_config(
        self,
        space_id: str,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Export a Genie space configuration (serialized_space).
        
        This retrieves the complete space configuration including all tables,
        instructions, joins, SQL snippets, and benchmarks.
        
        Args:
            space_id: The ID of the space to export
            output_path: Optional path to save the exported config as JSON
            
        Returns:
            Dictionary containing the parsed serialized_space configuration
            
        Note:
            Requires at least CAN EDIT permission on the space.
        """
        # Get space with serialized_space included
        space_data = self.get_space(space_id, include_serialized_space=True)
        
        # Parse the serialized_space JSON string
        serialized_space_str = space_data.get("serialized_space", "{}")
        config = json.loads(serialized_space_str)
        
        # Save to file if path provided
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"✓ Exported space configuration to: {output_path}")
        
        return config


def create_genie_space_from_file(
    config_path: str,
    databricks_host: Optional[str] = None,
    databricks_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a Genie space from a configuration file.
    
    Args:
        config_path: Path to the JSON configuration file
        databricks_host: Databricks workspace URL
        databricks_token: Databricks personal access token
        
    Returns:
        Dictionary containing:
        - space_id: The ID of the created space
        - space_url: URL to access the space
        - response: Full API response
    """
    # Load configuration
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Initialize client
    client = GenieSpaceClient(
        databricks_host=databricks_host,
        databricks_token=databricks_token
    )
    
    # Create space
    print(f"Creating Genie space from: {config_path}")
    response = client.create_space(config)
    
    # Extract space ID (API may return different field names)
    space_id = response.get("space_id") or response.get("id")
    
    if not space_id:
        raise ValueError(f"Could not extract space_id from API response: {response}")
    
    # Get space URL
    space_url = client.get_space_url(space_id)
    
    result = {
        "space_id": space_id,
        "space_url": space_url,
        "response": response
    }
    
    print(f"✓ Genie space created successfully!")
    print(f"  Space ID: {space_id}")
    print(f"  Space URL: {space_url}")
    
    return result
