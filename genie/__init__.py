"""Source package for Genie space configuration generation."""

# Models (at root)
from .models import (
    GenieSpaceConfig,
    GenieSpaceTable,
    GenieSpaceInstruction,
    GenieSpaceExampleSQL,
    GenieSpaceSQLExpression,
    GenieSpaceBenchmark,
    LLMResponse,
)

# LLM clients
from .llm import DatabricksLLMClient, DatabricksFoundationModelClient

# Prompt builder
from .prompt import PromptBuilder

# API clients
from .api import GenieSpaceClient, create_genie_space_from_file

# Utils
from .utils import (
    transform_to_serialized_space,
    create_join_spec,
    ParseCacheManager,
    update_config_catalog_schema_table,
    update_config_catalog_schema,
    remove_table_from_config,
)

# Benchmark utilities
from .benchmark import (
    extract_benchmarks_from_requirements,
    load_benchmarks_from_json,
    load_benchmarks_auto,
)

# Validation utilities
from .validation import (
    TableValidator,
    ValidationReport,
    ValidationIssue,
    SQLValidator,
    InstructionQualityScorer,
)

# Extractor utilities
from .extractor import (
    extract_domain_knowledge,
    extract_sample_queries_as_examples,
    extract_tables_from_requirements,
)

__all__ = [
    # Models
    "GenieSpaceConfig",
    "GenieSpaceTable",
    "GenieSpaceInstruction",
    "GenieSpaceExampleSQL",
    "GenieSpaceSQLExpression",
    "GenieSpaceBenchmark",
    "LLMResponse",
    # LLM
    "DatabricksLLMClient",
    "DatabricksFoundationModelClient",
    # Prompt
    "PromptBuilder",
    # API
    "GenieSpaceClient",
    "create_genie_space_from_file",
    # Utils
    "transform_to_serialized_space",
    "create_join_spec",
    "ParseCacheManager",
    "update_config_catalog_schema_table",
    "update_config_catalog_schema",
    "remove_table_from_config",
    # Benchmark
    "extract_benchmarks_from_requirements",
    "load_benchmarks_from_json",
    "load_benchmarks_auto",
    # Validation
    "TableValidator",
    "ValidationReport",
    "ValidationIssue",
    "SQLValidator",
    "InstructionQualityScorer",
    # Extractor
    "extract_domain_knowledge",
    "extract_sample_queries_as_examples",
    "extract_tables_from_requirements",
]
