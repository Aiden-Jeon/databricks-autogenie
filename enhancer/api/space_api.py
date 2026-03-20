"""
Genie Space API Client

Wrapper for Databricks Genie Space API to export and update
space configurations.
"""

import requests
import json
import logging
from typing import Dict, Optional, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpaceUpdater:
    """Client for managing Genie Space configurations via API."""

    def __init__(self, host: str, token: str):
        """
        Initialize Space Updater client.

        Args:
            host: Databricks workspace host (e.g., "company.cloud.databricks.com")
            token: Personal access token
        """
        self.host = host.replace("https://", "").replace("http://", "")
        self.base_url = f"https://{self.host}/api/2.0/genie/spaces"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def export_space(self, space_id: str) -> Dict:
        """
        Export a Genie Space configuration.

        Args:
            space_id: Genie Space ID

        Returns:
            {
                "space_id": str,
                "title": str,
                "description": str,
                "warehouse_id": str,
                "serialized_space": str (JSON string)
            }
        """
        url = f"{self.base_url}/{space_id}"
        params = {"include_serialized_space": "true"}

        logger.info(f"Exporting space: {space_id}")

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            result = response.json()

            # Parse serialized_space from JSON string to dict
            if "serialized_space" in result:
                result["serialized_space_parsed"] = json.loads(result["serialized_space"])

            logger.info(f"Space exported successfully")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to export space: {e}")
            raise

    def _migrate_column_config_v1_to_v2(self, column_config: Dict) -> Dict:
        """
        Migrate column_config from v1 to v2 field names.

        v1 fields -> v2 fields:
        - get_example_values -> enable_format_assistance
        - build_value_dictionary -> enable_entity_matching

        Args:
            column_config: Column configuration dict

        Returns:
            Migrated column configuration
        """
        # Migrate get_example_values -> enable_format_assistance
        if "get_example_values" in column_config:
            column_config["enable_format_assistance"] = column_config.pop("get_example_values")

        # Migrate build_value_dictionary -> enable_entity_matching
        if "build_value_dictionary" in column_config:
            column_config["enable_entity_matching"] = column_config.pop("build_value_dictionary")

        return column_config

    def _prepare_config_for_api(self, config: Dict) -> Dict:
        """
        Prepare configuration for Genie API by sorting and migrating fields.

        The Genie API requires:
        - column_configs sorted by column_name
        - join_specs sorted by id
        - example_question_sqls sorted by id
        - sample_questions sorted by id
        - v2 field names for column_configs

        Args:
            config: Space configuration dictionary

        Returns:
            Configuration with sorted and migrated fields
        """
        # Sort data_sources fields
        if "data_sources" in config:
            data_sources = config["data_sources"]

            # Sort tables by identifier (REQUIRED by API)
            if "tables" in data_sources and data_sources["tables"]:
                # First migrate and sort column_configs within each table
                for table in data_sources["tables"]:
                    if "column_configs" in table and table["column_configs"]:
                        # Migrate v1 -> v2 fields
                        table["column_configs"] = [
                            self._migrate_column_config_v1_to_v2(col)
                            for col in table["column_configs"]
                        ]
                        # Sort by column_name
                        table["column_configs"] = sorted(
                            table["column_configs"],
                            key=lambda x: x.get("column_name", "").lower()
                        )
                # Then sort tables by identifier
                data_sources["tables"] = sorted(
                    data_sources["tables"],
                    key=lambda x: x.get("identifier", "").lower()
                )

            # Sort metric_views by identifier (if exists)
            if "metric_views" in data_sources and data_sources["metric_views"]:
                for mv in data_sources["metric_views"]:
                    if "column_configs" in mv and mv["column_configs"]:
                        # Migrate v1 -> v2 fields
                        mv["column_configs"] = [
                            self._migrate_column_config_v1_to_v2(col)
                            for col in mv["column_configs"]
                        ]
                        # Sort by column_name
                        mv["column_configs"] = sorted(
                            mv["column_configs"],
                            key=lambda x: x.get("column_name", "").lower()
                        )
                # Sort metric_views by identifier
                data_sources["metric_views"] = sorted(
                    data_sources["metric_views"],
                    key=lambda x: x.get("identifier", "").lower()
                )

        # Sort instructions fields
        if "instructions" in config:
            instructions = config["instructions"]

            # Sort join_specs by id
            if "join_specs" in instructions and instructions["join_specs"]:
                instructions["join_specs"] = sorted(
                    instructions["join_specs"],
                    key=lambda x: x.get("id", "")
                )

            # Sort example_question_sqls by id
            if "example_question_sqls" in instructions and instructions["example_question_sqls"]:
                instructions["example_question_sqls"] = sorted(
                    instructions["example_question_sqls"],
                    key=lambda x: x.get("id", "")
                )

        # Sort sample_questions in config
        if "config" in config:
            cfg = config["config"]
            if "sample_questions" in cfg and cfg["sample_questions"]:
                cfg["sample_questions"] = sorted(
                    cfg["sample_questions"],
                    key=lambda x: x.get("id", "")
                )

        return config

    def update_space(
        self,
        space_id: str,
        serialized_space: str,
        title: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict:
        """
        Update an existing Genie Space with new configuration.

        Args:
            space_id: Genie Space ID
            serialized_space: JSON string of space configuration
            title: Optional new title
            description: Optional new description

        Returns:
            Updated space information
        """
        url = f"{self.base_url}/{space_id}"

        # Parse, sort required fields, and re-serialize
        config = json.loads(serialized_space)
        config = self._prepare_config_for_api(config)
        serialized_space = json.dumps(config)
        logger.info("Config prepared for API (sorted column_configs, join_specs, etc.)")

        payload = {
            "serialized_space": serialized_space
        }
        if title:
            payload["title"] = title
        if description:
            payload["description"] = description

        logger.info(f"Updating space: {space_id}")

        try:
            response = requests.patch(url, headers=self.headers, json=payload)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Space updated successfully")
            return result
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update space: {e}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response: {e.response.text}")
            raise

    def validate_config(self, config: Dict) -> Dict:
        """
        Validate a Genie Space configuration.

        Args:
            config: GenieSpaceExport dictionary

        Returns:
            {
                "is_valid": bool,
                "errors": List[str],
                "warnings": List[str]
            }
        """
        errors = []
        warnings = []

        # Check version
        if "version" not in config:
            errors.append("Missing required field: version")
        elif config["version"] != 1:
            errors.append(f"Invalid version: {config['version']}, expected 1")

        # Validate data_sources
        if "data_sources" in config:
            data_sources = config["data_sources"]

            # Check for tables
            if "tables" in data_sources:
                tables = data_sources["tables"]
                for table in tables:
                    # Validate identifier format (catalog.schema.table)
                    identifier = table.get("identifier", "")
                    if not self._is_valid_table_identifier(identifier):
                        errors.append(f"Invalid table identifier: {identifier}")

                    # Check column_configs
                    if "column_configs" in table:
                        for col in table["column_configs"]:
                            if "column_name" not in col:
                                errors.append(f"Column config missing column_name in {identifier}")

            # Check for metric_views
            if "metric_views" in data_sources:
                metric_views = data_sources["metric_views"]
                for mv in metric_views:
                    identifier = mv.get("identifier", "")
                    if not self._is_valid_table_identifier(identifier):
                        errors.append(f"Invalid metric view identifier: {identifier}")

        # Validate instructions
        if "instructions" in config:
            instructions = config["instructions"]

            # Check text_instructions (max 1)
            if "text_instructions" in instructions:
                if len(instructions["text_instructions"]) > 1:
                    errors.append("Maximum 1 text instruction allowed")

            # Validate join_specs
            if "join_specs" in instructions:
                for join in instructions["join_specs"]:
                    if "id" not in join:
                        errors.append("Join spec missing id")
                    if "left" not in join or "right" not in join:
                        errors.append("Join spec missing left or right")
                    if "sql" not in join:
                        errors.append("Join spec missing sql")
                    else:
                        # Check for relationship type marker
                        sql_lines = join["sql"]
                        has_marker = any("--rt=FROM_RELATIONSHIP_TYPE_" in line for line in sql_lines)
                        if not has_marker:
                            warnings.append(f"Join {join.get('id')} missing relationship type marker")

        # Validate UUIDs
        uuid_fields = [
            ("config.sample_questions", config.get("config", {}).get("sample_questions", [])),
            ("instructions.text_instructions", config.get("instructions", {}).get("text_instructions", [])),
            ("instructions.example_question_sqls", config.get("instructions", {}).get("example_question_sqls", [])),
            ("instructions.join_specs", config.get("instructions", {}).get("join_specs", [])),
        ]

        for field_name, items in uuid_fields:
            for item in items:
                if "id" in item:
                    if not self._is_valid_uuid(item["id"]):
                        errors.append(f"Invalid UUID in {field_name}: {item['id']}")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    def _is_valid_table_identifier(self, identifier: str) -> bool:
        """
        Check if identifier follows catalog.schema.table format.

        Args:
            identifier: Table identifier string

        Returns:
            True if valid, False otherwise
        """
        parts = identifier.split(".")
        return len(parts) == 3 and all(part.strip() for part in parts)

    def _is_valid_uuid(self, uuid_str: str) -> bool:
        """
        Check if string is a valid UUID (32 lowercase hex chars).

        Args:
            uuid_str: UUID string

        Returns:
            True if valid, False otherwise
        """
        import re
        pattern = r'^[0-9a-f]{32}$'
        return bool(re.match(pattern, uuid_str))

    def create_metric_view(
        self,
        warehouse_id: str,
        metric_view_name: str,
        catalog: str,
        schema: str,
        yaml_definition: Dict,
        source_table: str = None
    ) -> Dict:
        """
        Create a metric view in Unity Catalog using SQL.

        Args:
            warehouse_id: SQL warehouse ID for execution
            metric_view_name: Name of the metric view
            catalog: Catalog name
            schema: Schema name
            yaml_definition: Dict with 'dimensions' and 'measures' keys
            source_table: Optional source table (catalog.schema.table)

        Returns:
            {
                "success": bool,
                "metric_view_fqn": str,
                "sql_executed": str,
                "error": str or None
            }
        """
        import yaml

        fqn = f"{catalog}.{schema}.{metric_view_name}"
        logger.info(f"Creating metric view: {fqn}")

        try:
            # Build YAML definition
            yaml_dict = {}

            # Add source table if provided
            if source_table:
                yaml_dict["tables"] = [{"name": source_table}]

            # Add dimensions
            if "dimensions" in yaml_definition and yaml_definition["dimensions"]:
                yaml_dict["dimensions"] = yaml_definition["dimensions"]

            # Add measures
            if "measures" in yaml_definition and yaml_definition["measures"]:
                yaml_dict["measures"] = yaml_definition["measures"]

            # Convert to YAML string
            yaml_str = yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False)

            # Build CREATE METRIC VIEW SQL
            sql = f"""CREATE OR REPLACE METRIC VIEW {fqn}
AS '{yaml_str}'
"""

            logger.debug(f"Metric view SQL:\n{sql}")

            # Execute via SQL Statements API
            from .sql_executor import SQLExecutor
            executor = SQLExecutor(
                host=self.host,
                token=self.token,
                warehouse_id=warehouse_id
            )

            result = executor.execute(sql, timeout=60)

            if result["status"] == "SUCCEEDED":
                logger.info(f"✅ Metric view created successfully: {fqn}")
                return {
                    "success": True,
                    "metric_view_fqn": fqn,
                    "sql_executed": sql,
                    "error": None
                }
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(f"❌ Failed to create metric view: {error_msg}")
                return {
                    "success": False,
                    "metric_view_fqn": fqn,
                    "sql_executed": sql,
                    "error": error_msg
                }

        except Exception as e:
            logger.error(f"Error creating metric view: {e}", exc_info=True)
            return {
                "success": False,
                "metric_view_fqn": fqn,
                "sql_executed": sql if 'sql' in locals() else None,
                "error": str(e)
            }

    def add_metric_view_metadata(
        self,
        space_id: str,
        metric_view_fqn: str,
        table_description: str = None,
        column_descriptions: Dict[str, str] = None,
        synonyms: Dict[str, List[str]] = None
    ) -> Dict:
        """
        Add metadata (descriptions, synonyms) for a metric view to Genie Space.

        This adds the metric view as a table in the space configuration
        so Genie can discover and query it.

        Args:
            space_id: Genie Space ID
            metric_view_fqn: Fully qualified metric view name (catalog.schema.name)
            table_description: Description of the metric view
            column_descriptions: Dict mapping column names to descriptions
            synonyms: Dict mapping column names to lists of synonyms

        Returns:
            {
                "success": bool,
                "space_id": str,
                "error": str or None
            }
        """
        try:
            # Export current space
            space_data = self.export_space(space_id)
            config = space_data.get("serialized_space_parsed", {})

            # Find or create table entry for metric view
            tables = config.setdefault("data_sources", {}).setdefault("tables", [])

            # Check if metric view already exists in config
            metric_view_table = None
            for table in tables:
                if table["identifier"] == metric_view_fqn:
                    metric_view_table = table
                    break

            # Create new table entry if not exists
            if not metric_view_table:
                metric_view_table = {
                    "identifier": metric_view_fqn,
                    "column_configs": []
                }
                tables.append(metric_view_table)
                logger.info(f"Added metric view {metric_view_fqn} to space config")

            # Add table description
            if table_description:
                if isinstance(table_description, str):
                    metric_view_table["description"] = [table_description]
                else:
                    metric_view_table["description"] = table_description

            # Add column descriptions and synonyms
            if column_descriptions or synonyms:
                column_configs = metric_view_table.setdefault("column_configs", [])

                # Get all column names that need config
                all_columns = set()
                if column_descriptions:
                    all_columns.update(column_descriptions.keys())
                if synonyms:
                    all_columns.update(synonyms.keys())

                for column_name in all_columns:
                    # Find or create column config
                    column_config = None
                    for col in column_configs:
                        if col["column_name"] == column_name:
                            column_config = col
                            break

                    if not column_config:
                        column_config = {"column_name": column_name}
                        column_configs.append(column_config)

                    # Add description
                    if column_descriptions and column_name in column_descriptions:
                        desc = column_descriptions[column_name]
                        if isinstance(desc, str):
                            column_config["description"] = [desc]
                        else:
                            column_config["description"] = desc

                    # Add synonyms
                    if synonyms and column_name in synonyms:
                        column_config["synonyms"] = synonyms[column_name]

            # Update space
            self.update_space(space_id, json.dumps(config))

            logger.info(f"✅ Metric view metadata added to space {space_id}")
            return {
                "success": True,
                "space_id": space_id,
                "error": None
            }

        except Exception as e:
            logger.error(f"Error adding metric view metadata: {e}", exc_info=True)
            return {
                "success": False,
                "space_id": space_id,
                "error": str(e)
            }


# Example usage
if __name__ == "__main__":
    import os

    # Configuration
    HOST = os.getenv("DATABRICKS_HOST", "your-workspace.cloud.databricks.com")
    TOKEN = os.getenv("DATABRICKS_TOKEN", "your-token")
    SPACE_ID = os.getenv("GENIE_SPACE_ID", "your-space-id")

    # Create client
    updater = SpaceUpdater(HOST, TOKEN)

    # Export current space
    print("Exporting space...")
    space_data = updater.export_space(SPACE_ID)

    print(f"\nSpace ID: {space_data['space_id']}")
    print(f"Title: {space_data['title']}")
    print(f"Description: {space_data.get('description', 'N/A')}")

    # Validate current config
    if "serialized_space_parsed" in space_data:
        print("\nValidating configuration...")
        validation = updater.validate_config(space_data["serialized_space_parsed"])

        print(f"Valid: {validation['is_valid']}")
        if validation['errors']:
            print(f"Errors: {validation['errors']}")
        if validation['warnings']:
            print(f"Warnings: {validation['warnings']}")
    else:
        print("\nNo serialized space data available")
