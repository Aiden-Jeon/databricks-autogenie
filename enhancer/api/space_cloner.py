"""
Space Cloner for Three-Space Architecture

Manages cloning, deletion, and configuration copying between Genie Spaces
for safe enhancement without modifying production.

Three-Space Architecture:
- Production: Original space, never modified
- Dev-Best: Holds best-performing configuration (for rollback)
- Dev-Working: Where changes are tested
"""

import requests
import json
import logging
from typing import Dict, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SpaceCloner:
    """Manages Genie Space cloning and configuration for three-space architecture."""

    def __init__(self, host: str, token: str):
        """
        Initialize Space Cloner.

        Args:
            host: Databricks workspace host
            token: Personal access token
        """
        self.host = host.replace("https://", "").replace("http://", "")
        self.base_url = f"https://{self.host}/api/2.0/genie/spaces"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # Track created dev spaces for cleanup
        self.dev_working_id: Optional[str] = None
        self.dev_best_id: Optional[str] = None
        self.production_id: Optional[str] = None

    def setup_three_spaces(
        self,
        production_space_id: str,
        working_suffix: str = "_dev_working",
        best_suffix: str = "_dev_best"
    ) -> Dict:
        """
        Set up three-space architecture by cloning production.

        Args:
            production_space_id: ID of the production Genie Space
            working_suffix: Suffix for working dev space name
            best_suffix: Suffix for best dev space name

        Returns:
            {
                "success": bool,
                "production_id": str,
                "dev_working_id": str,
                "dev_best_id": str,
                "production_name": str,
                "initial_config": Dict,
                "error": str or None
            }
        """
        logger.info("=" * 80)
        logger.info("Setting up Three-Space Architecture")
        logger.info("=" * 80)

        self.production_id = production_space_id

        try:
            # 1. Export production space
            logger.info(f"[1/5] Exporting production space: {production_space_id}")
            production_data = self._export_space(production_space_id)
            production_name = production_data.get("title", "Genie Space")
            production_config = production_data.get("serialized_space_parsed", {})
            warehouse_id = production_data.get("warehouse_id")

            logger.info(f"      Production name: {production_name}")

            # 2. Check for and delete existing dev spaces
            logger.info(f"[2/5] Checking for existing dev spaces...")
            working_name = f"{production_name}{working_suffix}"
            best_name = f"{production_name}{best_suffix}"

            existing_spaces = self._list_spaces()
            for space in existing_spaces:
                if space.get("title") == working_name:
                    logger.info(f"      Deleting existing: {working_name}")
                    self._delete_space(space["space_id"])
                elif space.get("title") == best_name:
                    logger.info(f"      Deleting existing: {best_name}")
                    self._delete_space(space["space_id"])

            # 3. Create dev-working space
            logger.info(f"[3/5] Creating dev-working space: {working_name}")
            working_result = self._create_space(
                title=working_name,
                description=f"[DEV-WORKING] Enhancement testing space for {production_name}",
                warehouse_id=warehouse_id,
                serialized_space=json.dumps(production_config)
            )
            self.dev_working_id = working_result["space_id"]
            logger.info(f"      Created: {self.dev_working_id}")

            # 4. Create dev-best space
            logger.info(f"[4/5] Creating dev-best space: {best_name}")
            best_result = self._create_space(
                title=best_name,
                description=f"[DEV-BEST] Best-performing configuration for {production_name}",
                warehouse_id=warehouse_id,
                serialized_space=json.dumps(production_config)
            )
            self.dev_best_id = best_result["space_id"]
            logger.info(f"      Created: {self.dev_best_id}")

            # 5. Verify all spaces
            logger.info(f"[5/5] Verifying setup...")
            logger.info(f"      Production: {self.production_id}")
            logger.info(f"      Dev-Working: {self.dev_working_id}")
            logger.info(f"      Dev-Best: {self.dev_best_id}")

            logger.info("=" * 80)
            logger.info("✅ Three-Space Architecture Ready")
            logger.info("=" * 80)

            return {
                "success": True,
                "production_id": self.production_id,
                "dev_working_id": self.dev_working_id,
                "dev_best_id": self.dev_best_id,
                "production_name": production_name,
                "initial_config": production_config,
                "error": None
            }

        except Exception as e:
            logger.error(f"❌ Failed to set up three-space architecture: {e}")
            # Cleanup any partially created spaces
            self._cleanup_on_error()
            return {
                "success": False,
                "production_id": self.production_id,
                "dev_working_id": None,
                "dev_best_id": None,
                "production_name": None,
                "initial_config": None,
                "error": str(e)
            }

    def copy_config(self, source_space_id: str, target_space_id: str) -> Dict:
        """
        Copy configuration from source space to target space.

        Used for:
        - Updating dev-best when score improves (working → best)
        - Rolling back dev-working when score drops (best → working)

        Args:
            source_space_id: Space to copy from
            target_space_id: Space to copy to

        Returns:
            {"success": bool, "error": str or None}
        """
        try:
            # Export source config
            source_data = self._export_space(source_space_id)
            source_config = source_data.get("serialized_space_parsed", {})

            # Update target with source config
            self._update_space(target_space_id, json.dumps(source_config))

            logger.info(f"✅ Copied config: {source_space_id} → {target_space_id}")
            return {"success": True, "error": None}

        except Exception as e:
            logger.error(f"❌ Failed to copy config: {e}")
            return {"success": False, "error": str(e)}

    def update_dev_best(self) -> Dict:
        """Copy dev-working config to dev-best (when score improves)."""
        if not self.dev_working_id or not self.dev_best_id:
            return {"success": False, "error": "Dev spaces not initialized"}
        return self.copy_config(self.dev_working_id, self.dev_best_id)

    def rollback_dev_working(self) -> Dict:
        """Rollback dev-working from dev-best (when score drops)."""
        if not self.dev_working_id or not self.dev_best_id:
            return {"success": False, "error": "Dev spaces not initialized"}
        return self.copy_config(self.dev_best_id, self.dev_working_id)

    def promote_to_production(self) -> Dict:
        """
        Apply dev-best configuration to production space.

        Returns:
            {"success": bool, "error": str or None}
        """
        if not self.production_id or not self.dev_best_id:
            return {"success": False, "error": "Spaces not initialized"}

        logger.info("=" * 80)
        logger.info("Promoting dev-best to production")
        logger.info("=" * 80)

        try:
            # Export dev-best config
            best_data = self._export_space(self.dev_best_id)
            best_config = best_data.get("serialized_space_parsed", {})

            # Update production
            self._update_space(self.production_id, json.dumps(best_config))

            logger.info("✅ Production updated with best configuration")
            return {"success": True, "error": None}

        except Exception as e:
            logger.error(f"❌ Failed to promote to production: {e}")
            return {"success": False, "error": str(e)}

    def cleanup_dev_spaces(self) -> Dict:
        """
        Delete both dev spaces after enhancement completes.

        Returns:
            {"success": bool, "deleted": List[str], "error": str or None}
        """
        logger.info("Cleaning up dev spaces...")
        deleted = []
        errors = []

        if self.dev_working_id:
            try:
                self._delete_space(self.dev_working_id)
                deleted.append(self.dev_working_id)
                logger.info(f"  Deleted dev-working: {self.dev_working_id}")
            except Exception as e:
                errors.append(f"dev-working: {e}")

        if self.dev_best_id:
            try:
                self._delete_space(self.dev_best_id)
                deleted.append(self.dev_best_id)
                logger.info(f"  Deleted dev-best: {self.dev_best_id}")
            except Exception as e:
                errors.append(f"dev-best: {e}")

        self.dev_working_id = None
        self.dev_best_id = None

        if errors:
            return {"success": False, "deleted": deleted, "error": "; ".join(errors)}
        return {"success": True, "deleted": deleted, "error": None}

    def get_dev_working_config(self) -> Dict:
        """Get current configuration of dev-working space."""
        if not self.dev_working_id:
            raise ValueError("Dev-working space not initialized")
        data = self._export_space(self.dev_working_id)
        return data.get("serialized_space_parsed", {})

    # =========================================================================
    # Public API Methods (for BatchApplier compatibility)
    # =========================================================================

    def export_space(self, space_id: str) -> Dict:
        """
        Public wrapper for exporting a Genie Space configuration.

        Used by BatchApplier.
        """
        return self._export_space(space_id)

    def update_space(self, space_id: str, serialized_space: str) -> Dict:
        """
        Public wrapper for updating a Genie Space.

        Used by BatchApplier.
        """
        return self._update_space(space_id, serialized_space)

    def update_dev_working_config(self, config: Dict) -> Dict:
        """Update dev-working space with new configuration."""
        if not self.dev_working_id:
            return {"success": False, "error": "Dev-working space not initialized"}
        try:
            self._update_space(self.dev_working_id, json.dumps(config))
            return {"success": True, "error": None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Private API Methods
    # =========================================================================

    def _export_space(self, space_id: str) -> Dict:
        """Export a Genie Space configuration."""
        url = f"{self.base_url}/{space_id}"
        params = {"include_serialized_space": "true"}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        result = response.json()

        if "serialized_space" in result:
            result["serialized_space_parsed"] = json.loads(result["serialized_space"])

        return result

    def _create_space(
        self,
        title: str,
        description: str,
        warehouse_id: str,
        serialized_space: str
    ) -> Dict:
        """Create a new Genie Space."""
        url = self.base_url

        payload = {
            "title": title,
            "description": description,
            "warehouse_id": warehouse_id,
            "serialized_space": serialized_space
        }

        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def _update_space(self, space_id: str, serialized_space: str) -> Dict:
        """Update an existing Genie Space."""
        url = f"{self.base_url}/{space_id}"

        # Sort config for API requirements
        config = json.loads(serialized_space)
        config = self._prepare_config_for_api(config)
        serialized_space = json.dumps(config)

        payload = {"serialized_space": serialized_space}

        response = requests.patch(url, headers=self.headers, json=payload)
        if not response.ok:
            logger.error(f"API Error {response.status_code}: {response.text}")
        response.raise_for_status()
        return response.json()

    def _delete_space(self, space_id: str) -> Dict:
        """Delete a Genie Space."""
        url = f"{self.base_url}/{space_id}"
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()
        return {"success": True}

    def _list_spaces(self) -> list:
        """List all Genie Spaces."""
        response = requests.get(self.base_url, headers=self.headers)
        response.raise_for_status()
        result = response.json()
        return result.get("spaces", [])

    def _prepare_config_for_api(self, config: Dict) -> Dict:
        """Prepare configuration for Genie API (sorting, migration)."""
        # Sort data_sources fields
        if "data_sources" in config:
            data_sources = config["data_sources"]

            # Sort tables by identifier (REQUIRED by API)
            if "tables" in data_sources and data_sources["tables"]:
                for table in data_sources["tables"]:
                    if "column_configs" in table and table["column_configs"]:
                        # Migrate v1 -> v2 fields
                        for col in table["column_configs"]:
                            if "get_example_values" in col:
                                col["enable_format_assistance"] = col.pop("get_example_values")
                            if "build_value_dictionary" in col:
                                col["enable_entity_matching"] = col.pop("build_value_dictionary")
                        # Sort by column_name
                        table["column_configs"] = sorted(
                            table["column_configs"],
                            key=lambda x: x.get("column_name", "").lower()
                        )
                # Sort tables by identifier
                data_sources["tables"] = sorted(
                    data_sources["tables"],
                    key=lambda x: x.get("identifier", "").lower()
                )

            # Sort metric_views by identifier
            if "metric_views" in data_sources and data_sources["metric_views"]:
                data_sources["metric_views"] = sorted(
                    data_sources["metric_views"],
                    key=lambda x: x.get("identifier", "").lower()
                )

        # Sort instructions fields
        if "instructions" in config:
            instructions = config["instructions"]

            if "join_specs" in instructions and instructions["join_specs"]:
                instructions["join_specs"] = sorted(
                    instructions["join_specs"],
                    key=lambda x: x.get("id", "")
                )

            if "example_question_sqls" in instructions and instructions["example_question_sqls"]:
                # Fix type_hints: API only accepts STRING, INTEGER, DATE
                type_hint_mapping = {
                    "LONG": "INTEGER",
                    "DOUBLE": "INTEGER",
                    "TIMESTAMP": "DATE",
                    "BOOLEAN": "STRING",
                }
                valid_type_hints = {"STRING", "INTEGER", "DATE"}

                for example in instructions["example_question_sqls"]:
                    if "parameters" in example:
                        for param in example["parameters"]:
                            if "type_hint" in param:
                                hint = param["type_hint"].upper()
                                # Map to valid type
                                hint = type_hint_mapping.get(hint, hint)
                                if hint in valid_type_hints:
                                    param["type_hint"] = hint
                                else:
                                    # Mark for removal (can't delete during iteration)
                                    param["type_hint"] = None
                        # Remove None type_hints
                        for param in example["parameters"]:
                            if param.get("type_hint") is None:
                                param.pop("type_hint", None)

                instructions["example_question_sqls"] = sorted(
                    instructions["example_question_sqls"],
                    key=lambda x: x.get("id", "")
                )

            # Sort sql_snippets (filters, expressions, measures) by id
            if "sql_snippets" in instructions and instructions["sql_snippets"]:
                snippets = instructions["sql_snippets"]
                for snippet_type in ["filters", "expressions", "measures"]:
                    if snippet_type in snippets and snippets[snippet_type]:
                        snippets[snippet_type] = sorted(
                            snippets[snippet_type],
                            key=lambda x: x.get("id", "")
                        )

        # Sort sample_questions
        if "config" in config:
            cfg = config["config"]
            if "sample_questions" in cfg and cfg["sample_questions"]:
                cfg["sample_questions"] = sorted(
                    cfg["sample_questions"],
                    key=lambda x: x.get("id", "")
                )

        return config

    def _cleanup_on_error(self):
        """Clean up any partially created spaces on error."""
        if self.dev_working_id:
            try:
                self._delete_space(self.dev_working_id)
                logger.info(f"  Cleaned up partial dev-working: {self.dev_working_id}")
            except Exception:
                pass
            self.dev_working_id = None

        if self.dev_best_id:
            try:
                self._delete_space(self.dev_best_id)
                logger.info(f"  Cleaned up partial dev-best: {self.dev_best_id}")
            except Exception:
                pass
            self.dev_best_id = None


# Example usage
if __name__ == "__main__":
    import os

    HOST = os.getenv("DATABRICKS_HOST")
    TOKEN = os.getenv("DATABRICKS_TOKEN")
    SPACE_ID = os.getenv("GENIE_SPACE_ID")

    if HOST and TOKEN and SPACE_ID:
        cloner = SpaceCloner(HOST, TOKEN)

        # Set up three-space architecture
        result = cloner.setup_three_spaces(SPACE_ID)

        if result["success"]:
            print(f"\nProduction: {result['production_id']}")
            print(f"Dev-Working: {result['dev_working_id']}")
            print(f"Dev-Best: {result['dev_best_id']}")

            # Test copy operations
            print("\nTesting copy operations...")
            cloner.update_dev_best()
            cloner.rollback_dev_working()

            # Cleanup
            print("\nCleaning up...")
            cloner.cleanup_dev_spaces()
        else:
            print(f"Setup failed: {result['error']}")
    else:
        print("Set DATABRICKS_HOST, DATABRICKS_TOKEN, and GENIE_SPACE_ID")
