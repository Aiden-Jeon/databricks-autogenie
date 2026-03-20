"""Pydantic models for Genie space creation."""

from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class GenieSpaceTable(BaseModel):
    """Represents a table to include in the Genie space."""
    
    catalog_name: str = Field(..., description="Catalog name in Unity Catalog")
    schema_name: str = Field(..., description="Schema name in Unity Catalog")
    table_name: str = Field(..., description="Table name in Unity Catalog")
    description: Optional[str] = Field(None, description="Custom description for the table")


class GenieSpaceInstruction(BaseModel):
    """Represents a plain text instruction for the Genie space."""
    
    content: str = Field(..., description="The instruction text")
    priority: Optional[int] = Field(None, description="Priority of the instruction (higher = more important)")


class GenieSpaceExampleSQL(BaseModel):
    """Represents an example SQL query for the Genie space."""
    
    question: str = Field(..., description="Natural language question that this SQL answers")
    sql_query: str = Field(..., description="The SQL query that answers the question")
    description: Optional[str] = Field(None, description="Additional description or context")


class GenieSpaceSQLFilter(BaseModel):
    """Represents a SQL filter (WHERE condition)."""
    
    sql: str = Field(..., description="SQL filter expression (e.g., 'table.price > 100')")
    display_name: str = Field(..., description="User-friendly name for the filter")
    synonyms: Optional[List[str]] = Field(None, description="Alternative names for the filter")


class GenieSpaceSQLExpression(BaseModel):
    """Represents a SQL expression (dimension/calculated field)."""
    
    alias: str = Field(..., description="Internal alias for the expression")
    sql: str = Field(..., description="SQL expression (e.g., 'YEAR(orders.order_date)')")
    display_name: str = Field(..., description="User-friendly name for the expression")
    synonyms: Optional[List[str]] = Field(None, description="Alternative names for the expression")
    instruction: Optional[str] = Field(None, description="Guidance on when and how to use this expression")


class GenieSpaceSQLMeasure(BaseModel):
    """Represents a SQL measure (aggregation)."""
    
    alias: str = Field(..., description="Internal alias for the measure")
    sql: str = Field(..., description="SQL aggregation expression (e.g., 'SUM(orders.order_amount)')")
    display_name: str = Field(..., description="User-friendly name for the measure")
    synonyms: Optional[List[str]] = Field(None, description="Alternative names for the measure")
    instruction: Optional[str] = Field(None, description="Guidance on when and how to use this measure")


class GenieSpaceSQLSnippets(BaseModel):
    """Container for all SQL snippets (filters, expressions, measures)."""
    
    filters: List[GenieSpaceSQLFilter] = Field(default_factory=list, description="SQL filters (WHERE conditions)")
    expressions: List[GenieSpaceSQLExpression] = Field(default_factory=list, description="SQL expressions (dimensions/calculated fields)")
    measures: List[GenieSpaceSQLMeasure] = Field(default_factory=list, description="SQL measures (aggregations)")


class GenieSpaceBenchmark(BaseModel):
    """Represents a benchmark question for testing the Genie space."""

    question: str = Field(..., description="The benchmark question")
    expected_sql: Optional[str] = Field(None, description="Expected SQL query pattern")
    expected_accuracy: Optional[str] = Field(None, description="Expected accuracy level")


class GenieSpaceJoinSpec(BaseModel):
    """Represents an explicit join specification between two tables."""

    left_table: str = Field(..., description="Left table in fully qualified format: catalog.schema.table")
    right_table: str = Field(..., description="Right table in fully qualified format: catalog.schema.table")
    join_type: str = Field(..., description="Join type: INNER, LEFT, RIGHT, or FULL")
    join_condition: str = Field(..., description="Join condition (e.g., 'left_table.id = right_table.foreign_id')")
    description: Optional[str] = Field(None, description="Explanation of the relationship between tables")
    instruction: Optional[str] = Field(None, description="Guidance on when and how to use this join")


class GenieSpaceConfig(BaseModel):
    """Complete configuration for creating a Genie space."""
    
    space_name: str = Field(..., description="Name of the Genie space")
    description: str = Field(..., description="Description of what this space is for")
    purpose: str = Field(..., description="Specific purpose and target audience")
    
    # Data configuration
    tables: List[GenieSpaceTable] = Field(default_factory=list, description="Tables to include in the space")
    join_specifications: List[GenieSpaceJoinSpec] = Field(default_factory=list, description="Explicit join relationships between tables")

    # Instructions and examples
    instructions: List[GenieSpaceInstruction] = Field(default_factory=list, description="Plain text instructions")
    example_sql_queries: List[GenieSpaceExampleSQL] = Field(default_factory=list, description="Example SQL queries")
    sql_snippets: Optional[GenieSpaceSQLSnippets] = Field(None, description="SQL snippets (filters, expressions, measures)")

    # Testing
    benchmark_questions: List[GenieSpaceBenchmark] = Field(default_factory=list, description="Benchmark questions for testing")
    
    # Metadata
    warehouse_id: Optional[str] = Field(None, description="SQL warehouse ID to use")
    enable_data_sampling: bool = Field(True, description="Whether to enable data sampling")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "space_name": "Fashion Retail Analytics",
                "description": "Natural language querying for fashion retail data",
                "purpose": "Enable business users to analyze sales, customer behavior, and product performance",
                "tables": [
                    {
                        "catalog_name": "jongseob_demo",
                        "schema_name": "fashion_recommendations",
                        "table_name": "transactions"
                    }
                ],
                "instructions": [
                    {
                        "content": "When users ask about sales without specifying a time range, default to the last 7 days.",
                        "priority": 1
                    }
                ],
                "example_sql_queries": [
                    {
                        "question": "What were the top selling products last week?",
                        "sql_query": "SELECT product_name, COUNT(*) as sales FROM transactions WHERE transaction_date >= CURRENT_DATE - 7 GROUP BY product_name ORDER BY sales DESC LIMIT 10"
                    }
                ],
                "benchmark_questions": [
                    {
                        "question": "What were the top 10 selling products last week?"
                    }
                ]
            }
        }
    )


class BenchmarkSQL(BaseModel):
    """Single benchmark SQL result from LLM."""

    question: str = Field(..., description="The benchmark question")
    sql: str = Field(..., description="Complete SQL query answering the question")
    reasoning: Optional[str] = Field(None, description="Explanation of query logic")


class BenchmarkSQLResponse(BaseModel):
    """Response from LLM for benchmark SQL generation."""

    benchmark_sqls: List[BenchmarkSQL] = Field(..., description="List of benchmark SQL queries")
    reasoning: Optional[str] = Field(None, description="Overall reasoning for SQL generation approach")


class LLMResponse(BaseModel):
    """Response from the LLM containing the generated Genie space configuration."""

    genie_space_config: GenieSpaceConfig = Field(..., description="The generated Genie space configuration")
    reasoning: Optional[str] = Field(None, description="LLM's reasoning for the configuration choices")
    confidence_score: Optional[float] = Field(None, description="Confidence score (0-1) for the configuration")
