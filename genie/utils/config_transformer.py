"""
Transform our Genie space configuration to Databricks serialized_space format.

CRITICAL REQUIREMENTS
=====================
1. **Version**: Must be 1 (not 2)
2. **IDs**: 32 lowercase hexadecimal characters (no dashes) - generate with uuid.uuid4().hex
3. **Sorting**: All arrays with IDs MUST be sorted by ID
   - sample_questions, text_instructions, example_question_sqls, join_specs
   - sql_functions, sql_snippets.filters, sql_snippets.expressions, sql_snippets.measures
   - benchmarks.questions
4. **Tables/Columns**: Must be sorted
   - data_sources.tables[] - sorted by identifier
   - column_configs[] - sorted by column_name

Join Specification Format
=========================
Join specs define relationships between tables in the Genie space.

Input format (in your config JSON):
{
    "joins": [
        {
            "left_table": "catalog.schema.fact_table",
            "left_alias": "fact_table",
            "right_table": "catalog.schema.dim_table",
            "right_alias": "dim_table",
            "join_condition": "fact_table.dim_id = dim_table.dim_id",
            "relationship_type": "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE",
            "comment": "Links fact records to dimension"
        }
    ]
}

Valid relationship types:
- FROM_RELATIONSHIP_TYPE_ONE_TO_ONE: Each record in left matches exactly one in right
- FROM_RELATIONSHIP_TYPE_MANY_TO_ONE: Many records in left can match one in right (most common for fact→dim)
- FROM_RELATIONSHIP_TYPE_ONE_TO_MANY: One record in left matches many in right
- FROM_RELATIONSHIP_TYPE_MANY_TO_MANY: Many-to-many relationship

SQL Snippets
============
Reusable SQL components that Genie can use:
- filters: WHERE conditions (e.g., "table.price > 100")
- expressions: Row-level calculations (e.g., "CONCAT(first_name, ' ', last_name)")
- measures: Aggregations (e.g., "SUM(revenue)", "AVG(price)")

Column Config Flags
===================
- exclude: Set to True to hide column from Genie (default: False)
- get_example_values: Set to True for dates, IDs, key fields (default: False)
- build_value_dictionary: Set to True for categorical fields (default: False)
"""

import json
import uuid
from typing import Dict, Any, List


def _generate_id() -> str:
    """Generate a Genie-compatible ID (32-character lowercase hex UUID without hyphens)"""
    return uuid.uuid4().hex  # Returns 32-character hex string


def _to_string_array(text: str) -> List[str]:
    """
    Convert a string to an array of strings for Databricks format.
    Splits by lines and preserves newlines.
    
    Important: Each line should end with \n except potentially the last line.
    """
    if not text:
        return []
    
    # Split by newlines and preserve them
    lines = text.split('\n')
    result = []
    for i, line in enumerate(lines):
        # Add newline to each line (Databricks format expects this)
        if i < len(lines) - 1 or line:  # Add \n to all but empty last line
            result.append(line + '\n')
    return result


def create_join_spec(
    left_table: str,
    right_table: str,
    left_column: str,
    right_column: str,
    relationship_type: str = "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE",
    left_alias: str = None,
    right_alias: str = None,
    comment: str = None
) -> Dict[str, Any]:
    """
    Helper function to create a join specification.
    
    Args:
        left_table: Full table identifier (catalog.schema.table)
        right_table: Full table identifier (catalog.schema.table)
        left_column: Column name in the left table (no backticks needed)
        right_column: Column name in the right table (no backticks needed)
        relationship_type: Relationship type (default: MANY_TO_ONE)
        left_alias: Optional alias for left table (defaults to table name)
        right_alias: Optional alias for right table (defaults to table name)
        comment: Optional comment describing the join relationship
    
    Returns:
        Join specification dictionary ready for use in config
    
    Example:
        >>> create_join_spec(
        ...     "users.schema.fact_sales",
        ...     "users.schema.dim_product",
        ...     "product_id",
        ...     "product_id",
        ...     "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE",
        ...     comment="Links sales to product information"
        ... )
    """
    # Extract table names for default aliases
    if left_alias is None:
        left_alias = left_table.split('.')[-1]
    if right_alias is None:
        right_alias = right_table.split('.')[-1]
    
    # Validate relationship type
    valid_types = [
        "FROM_RELATIONSHIP_TYPE_ONE_TO_ONE",
        "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE",
        "FROM_RELATIONSHIP_TYPE_ONE_TO_MANY",
        "FROM_RELATIONSHIP_TYPE_MANY_TO_MANY"
    ]
    if relationship_type not in valid_types:
        raise ValueError(
            f"Invalid relationship type: {relationship_type}. "
            f"Valid types are: {', '.join(valid_types)}"
        )
    
    # Build join condition WITHOUT backticks (Databricks format)
    join_condition = f"{left_alias}.{left_column} = {right_alias}.{right_column}"
    
    result = {
        "left_table": left_table,
        "left_alias": left_alias,
        "right_table": right_table,
        "right_alias": right_alias,
        "join_condition": join_condition,
        "relationship_type": relationship_type
    }
    
    if comment:
        result["comment"] = comment
    
    return result


def _convert_join_specifications_to_joins(join_specifications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert simplified join_specifications format from LLM to internal joins format.

    LLM format (simple):
    {
        "left_table": "catalog.schema.table1",
        "right_table": "catalog.schema.table2",
        "join_type": "INNER|LEFT|RIGHT|FULL",
        "join_condition": "table1.col = table2.col",
        "description": "...",
        "instruction": "..."
    }

    Internal format (for serialization):
    {
        "left_table": "catalog.schema.table1",
        "left_alias": "table1",
        "right_table": "catalog.schema.table2",
        "right_alias": "table2",
        "join_condition": "table1.col = table2.col",
        "relationship_type": "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE",
        "comment": "...",
        "instruction": "..."
    }
    """
    # Map join types to relationship types
    # INNER/LEFT typically indicate many-to-one (fact to dimension)
    # This is a reasonable default; can be overridden in config
    join_type_to_relationship = {
        "INNER": "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE",
        "LEFT": "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE",
        "RIGHT": "FROM_RELATIONSHIP_TYPE_ONE_TO_MANY",
        "FULL": "FROM_RELATIONSHIP_TYPE_MANY_TO_MANY",
    }

    joins = []
    for spec in join_specifications:
        left_table = spec.get("left_table", "")
        right_table = spec.get("right_table", "")
        join_type = spec.get("join_type", "INNER").upper()
        join_condition = spec.get("join_condition", "")
        description = spec.get("description", "")
        instruction = spec.get("instruction", "")

        # Extract table names for aliases
        left_alias = left_table.split('.')[-1] if left_table else ""
        right_alias = right_table.split('.')[-1] if right_table else ""

        # Map join type to relationship type
        relationship_type = join_type_to_relationship.get(join_type, "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE")

        join = {
            "left_table": left_table,
            "left_alias": left_alias,
            "right_table": right_table,
            "right_alias": right_alias,
            "join_condition": join_condition,
            "relationship_type": relationship_type,
        }

        if description:
            join["comment"] = description

        if instruction:
            join["instruction"] = instruction

        joins.append(join)

    return joins


def _validate_and_fix_join_table_references(
    joins: List[Dict[str, Any]],
    tables: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Validate that join table references match actual tables in the space.
    Automatically corrects catalog/schema mismatches by matching on table name.
    Skips joins that reference tables not included in the space.

    Args:
        joins: List of join specifications (internal format)
        tables: List of table definitions from config

    Returns:
        Corrected list of join specifications (excluding joins with missing tables)
    """
    # Build lookup: table_name -> full_identifier
    table_map = {}
    for table in tables:
        catalog = table.get("catalog_name", "")
        schema = table.get("schema_name", "")
        table_name = table.get("table_name", "")
        full_identifier = f"{catalog}.{schema}.{table_name}"
        table_map[table_name] = full_identifier

    corrected_joins = []
    for join in joins:
        # Check if both tables exist in the space
        left_table = join.get("left_table", "")
        left_table_name = left_table.split(".")[-1]
        right_table = join.get("right_table", "")
        right_table_name = right_table.split(".")[-1]

        # Skip joins that reference tables not in the space
        if left_table_name not in table_map:
            print(f"Warning: Skipping join - left table '{left_table}' not in space")
            continue
        if right_table_name not in table_map:
            print(f"Warning: Skipping join - right table '{right_table}' not in space")
            continue

        corrected_join = join.copy()

        # Fix left_table reference
        correct_left = table_map[left_table_name]
        if left_table != correct_left:
            print(f"Warning: Correcting join left_table: {left_table} -> {correct_left}")
            corrected_join["left_table"] = correct_left
            corrected_join["left_alias"] = left_table_name

        # Fix right_table reference
        correct_right = table_map[right_table_name]
        if right_table != correct_right:
            print(f"Warning: Correcting join right_table: {right_table} -> {correct_right}")
            corrected_join["right_table"] = correct_right
            corrected_join["right_alias"] = right_table_name

        # Fix join_condition to use correct table references
        join_condition = corrected_join.get("join_condition", "")
        if join_condition:
            # Update join condition to replace old catalog.schema.table references
            # with the correct ones
            if left_table != correct_left:
                join_condition = join_condition.replace(left_table, correct_left)
            if right_table != correct_right:
                join_condition = join_condition.replace(right_table, correct_right)
            corrected_join["join_condition"] = join_condition

        corrected_joins.append(corrected_join)

    return corrected_joins


def _filter_invalid_self_joins(joins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter out invalid self-joins that would cause API errors.

    An invalid self-join is detected when:
    1. left_table == right_table (self-join)
    2. The join condition has identical left and right sides (e.g., table.col = table.col)

    Args:
        joins: List of join specifications

    Returns:
        Filtered list of joins with invalid self-joins removed
    """
    valid_joins = []

    for join in joins:
        left_table = join.get("left_table", "")
        right_table = join.get("right_table", "")
        join_condition = join.get("join_condition", "")

        # Check if this is a self-join
        if left_table == right_table:
            # Parse the join condition to check if it's invalid
            # Invalid: table.col = table.col (same column on both sides)
            # Valid: table.col1 = table.col2 (different columns for self-comparison)

            if "=" in join_condition:
                # Split by = and normalize whitespace
                parts = [p.strip() for p in join_condition.split("=")]

                if len(parts) == 2:
                    left_expr = parts[0]
                    right_expr = parts[1]

                    # Check if both sides are identical
                    if left_expr == right_expr:
                        print(f"Warning: Filtering invalid self-join on '{left_table}' with condition '{join_condition}'")
                        print(f"  Reason: Join condition has identical left and right sides (tautology)")
                        continue

                    # Additional check: If both sides reference the same column name
                    # e.g., "topic_url = topic_url" or "table.topic_url = table.topic_url"
                    left_col = left_expr.split(".")[-1]
                    right_col = right_expr.split(".")[-1]

                    if left_col == right_col:
                        print(f"Warning: Filtering suspicious self-join on '{left_table}' with condition '{join_condition}'")
                        print(f"  Reason: Self-join on the same column '{left_col}' (likely not meaningful)")
                        continue
            else:
                # No = in condition - this is suspicious for any join
                print(f"Warning: Filtering self-join on '{left_table}' with invalid condition '{join_condition}'")
                print(f"  Reason: Join condition must contain '='")
                continue

        # If we got here, the join is valid
        valid_joins.append(join)

    if len(valid_joins) < len(joins):
        filtered_count = len(joins) - len(valid_joins)
        print(f"Filtered {filtered_count} invalid self-join(s) from configuration")

    return valid_joins


def transform_to_serialized_space(config: Dict[str, Any]) -> str:
    """
    Transform our configuration format to Databricks serialized_space format.

    Based on actual Genie room structure analysis:
    - Instructions are nested under an "instructions" object with three arrays:
      - text_instructions: general instructions
      - join_specs: join specifications between tables
      - example_question_sqls: example questions with SQL queries
    - All text fields (content, question, sql) are arrays of strings
    - Benchmarks are a separate top-level section

    Handles two formats for joins:
    1. "join_specifications" (simple format from LLM) - converted automatically
    2. "joins" (internal format) - used directly

    Args:
        config: Our Genie space configuration

    Returns:
        JSON string in serialized_space format
    """
    # Validate: Remove empty "joins" field if present
    # This field conflicts with "join_specifications"
    if "joins" in config and config.get("joins") == []:
        import warnings
        warnings.warn(
            "Config contains empty 'joins' field - removing it. "
            "This field conflicts with 'join_specifications'."
        )
        config = config.copy()
        del config["joins"]

    # Validate and fix: Replace forward slashes in metadata fields
    # Forward slashes in space_name cause INTERNAL_ERROR
    metadata_fields = ['space_name', 'description', 'purpose']
    for field in metadata_fields:
        if field in config and isinstance(config[field], str):
            if '/' in config[field]:
                import warnings
                warnings.warn(
                    f"Config contains forward slash (/) in '{field}' field. "
                    f"Replacing with ' and ' to avoid API errors."
                )
                config = config.copy() if config is not config else config
                config[field] = config[field].replace('/', ' and ')

    # Extract tables from our config
    tables = config.get("tables", [])
    
    # Transform tables to Databricks format
    serialized_tables = []
    for table in tables:
        catalog = table.get("catalog_name", "")
        schema = table.get("schema_name", "")
        table_name = table.get("table_name", "")
        
        # Create table identifier in format: catalog.schema.table
        identifier = f"{catalog}.{schema}.{table_name}"
        
        serialized_table = {
            "identifier": identifier,
        }
        
        # Add description if present (must be an array)
        if "description" in table:
            desc = table["description"]
            if isinstance(desc, str):
                serialized_table["description"] = [desc]
            elif isinstance(desc, list):
                serialized_table["description"] = desc
        
        # Add column_configs if present
        if "column_configs" in table:
            column_configs = table["column_configs"]
            # Process each column config to ensure proper format
            processed_configs = []
            for col_config in column_configs:
                col = col_config.copy()
                
                # Ensure description is an array if present
                if "description" in col and isinstance(col["description"], str):
                    col["description"] = [col["description"]]
                
                # Ensure synonyms is an array if present
                if "synonyms" in col and isinstance(col["synonyms"], str):
                    col["synonyms"] = [col["synonyms"]]
                
                # Ensure exclude, get_example_values, build_value_dictionary are set
                # (these are important flags that Databricks uses)
                if "exclude" not in col:
                    col["exclude"] = False
                if "get_example_values" not in col:
                    col["get_example_values"] = False
                if "build_value_dictionary" not in col:
                    col["build_value_dictionary"] = False
                
                processed_configs.append(col)
            
            # Sort column configs by column_name (required by Databricks API)
            processed_configs.sort(key=lambda x: x.get("column_name", ""))
            serialized_table["column_configs"] = processed_configs
        
        serialized_tables.append(serialized_table)
    
    # Sort tables by identifier (required by Databricks API)
    serialized_tables.sort(key=lambda x: x["identifier"])
    
    # Build the serialized_space structure
    # IMPORTANT: Use version 1 (not 2) as per Databricks API reference
    serialized_space = {
        "version": 1,
        "data_sources": {
            "tables": serialized_tables
        }
    }
    
    # =========================================================================
    # CONFIG SECTION (sample questions for UI)
    # =========================================================================
    sample_questions = config.get("sample_questions", [])
    if sample_questions:
        sample_q_list = []
        for sq in sample_questions:
            question_text = sq.get("question", "")
            if question_text:
                sample_q_item = {
                    "id": _generate_id(),
                    "question": [question_text] if isinstance(question_text, str) else question_text
                }
                sample_q_list.append(sample_q_item)
        
        if sample_q_list:
            # Sort by ID (required by Databricks API)
            sample_q_list.sort(key=lambda x: x["id"])
            serialized_space["config"] = {
                "sample_questions": sample_q_list
            }
    
    # =========================================================================
    # INSTRUCTIONS SECTION (nested structure)
    # =========================================================================
    instructions_section = {}
    
    # 1. Text Instructions
    # NOTE: Databricks API requires exactly ONE text_instruction item
    # Combine all instructions into a single content array
    text_instructions = config.get("instructions", [])
    if text_instructions:
        combined_content = []
        for instruction in text_instructions:
            content = instruction.get("content", "")
            if content:
                # Add the instruction content
                combined_content.extend(_to_string_array(content))
                # Add separator between instructions
                combined_content.append("\n")
        
        if combined_content:
            serialized_instruction = {
                "id": _generate_id(),
                "content": combined_content
            }
            instructions_section["text_instructions"] = [serialized_instruction]
    
    # 2. Join Specifications
    # Format based on actual Genie space structure:
    # {
    #   "id": "unique_id",
    #   "left": {"identifier": "catalog.schema.table", "alias": "table_alias"},
    #   "right": {"identifier": "catalog.schema.table", "alias": "table_alias"},
    #   "sql": [
    #     "left_alias.column = right_alias.column\n",
    #     "--rt=FROM_RELATIONSHIP_TYPE_XXX--"
    #   ],
    #   "comment": ["Description of the join relationship"],
    #   "instruction": ["When to use this join"]
    # }
    # Valid relationship types:
    # - FROM_RELATIONSHIP_TYPE_ONE_TO_ONE
    # - FROM_RELATIONSHIP_TYPE_MANY_TO_ONE
    # - FROM_RELATIONSHIP_TYPE_ONE_TO_MANY
    # - FROM_RELATIONSHIP_TYPE_MANY_TO_MANY

    # Handle both join_specifications (new LLM format) and joins (internal format)
    joins = config.get("joins", [])
    join_specifications = config.get("join_specifications", [])

    # Convert join_specifications to joins format if present
    if join_specifications and not joins:
        joins = _convert_join_specifications_to_joins(join_specifications)

    # VALIDATE AND FIX JOIN TABLE REFERENCES
    if joins and tables:
        joins = _validate_and_fix_join_table_references(joins, tables)

    # FILTER OUT INVALID SELF-JOINS
    if joins:
        joins = _filter_invalid_self_joins(joins)

    if joins:
        join_specs = []
        for join in joins:
            join_spec = {
                "id": _generate_id(),
                "left": {
                    "identifier": join.get("left_table", ""),
                    "alias": join.get("left_alias", "")
                },
                "right": {
                    "identifier": join.get("right_table", ""),
                    "alias": join.get("right_alias", "")
                },
                "sql": []
            }
            
            # Add join condition as array of strings
            # IMPORTANT: No backticks, add \n to each line
            join_condition = join.get("join_condition", "")
            if join_condition:
                # Remove backticks if present and add newline
                join_condition = join_condition.replace("`", "")
                if not join_condition.endswith("\n"):
                    join_condition += "\n"
                join_spec["sql"].append(join_condition)
            
            # Add relationship type if present
            # Format: "--rt=FROM_RELATIONSHIP_TYPE_XXX--"
            relationship_type = join.get("relationship_type", "")
            if relationship_type:
                # Validate relationship type
                valid_types = [
                    "FROM_RELATIONSHIP_TYPE_ONE_TO_ONE",
                    "FROM_RELATIONSHIP_TYPE_MANY_TO_ONE",
                    "FROM_RELATIONSHIP_TYPE_ONE_TO_MANY",
                    "FROM_RELATIONSHIP_TYPE_MANY_TO_MANY"
                ]
                if relationship_type not in valid_types:
                    raise ValueError(
                        f"Invalid relationship type: {relationship_type}. "
                        f"Valid types are: {', '.join(valid_types)}"
                    )
                join_spec["sql"].append(f"--rt={relationship_type}--")
            
            # Add comment if present (must be an array)
            if "comment" in join:
                comment = join["comment"]
                if isinstance(comment, str):
                    join_spec["comment"] = [comment]
                elif isinstance(comment, list):
                    join_spec["comment"] = comment
            
            # Add instruction if present (must be an array)
            if "instruction" in join:
                instruction = join["instruction"]
                if isinstance(instruction, str):
                    join_spec["instruction"] = [instruction]
                elif isinstance(instruction, list):
                    join_spec["instruction"] = instruction
            
            join_specs.append(join_spec)
        
        if join_specs:
            # Sort by ID (required by Databricks API)
            join_specs.sort(key=lambda x: x["id"])
            instructions_section["join_specs"] = join_specs
    
    # 3. Example Question SQL Queries
    example_queries = config.get("example_sql_queries", [])
    if example_queries:
        example_question_sqls = []
        for example in example_queries:
            question = example.get("question", "")
            sql_query = example.get("sql_query", "")
            
            if question and sql_query:
                example_sql = {
                    "id": _generate_id(),
                    "question": _to_string_array(question) if isinstance(question, str) else question,
                    "sql": _to_string_array(sql_query) if isinstance(sql_query, str) else sql_query
                }
                
                # Add parameters if present
                if "parameters" in example and example["parameters"]:
                    example_sql["parameters"] = example["parameters"]
                
                # Add usage_guidance if present
                if "usage_guidance" in example:
                    guidance = example["usage_guidance"]
                    if isinstance(guidance, str):
                        example_sql["usage_guidance"] = [guidance]
                    elif isinstance(guidance, list):
                        example_sql["usage_guidance"] = guidance
                
                example_question_sqls.append(example_sql)
        
        if example_question_sqls:
            # Sort by ID (required by Databricks API)
            example_question_sqls.sort(key=lambda x: x["id"])
            instructions_section["example_question_sqls"] = example_question_sqls
    
    # 4. SQL Functions (references to SQL UDFs)
    sql_functions = config.get("sql_functions", [])
    if sql_functions:
        function_list = []
        for func in sql_functions:
            func_item = {
                "id": _generate_id()
            }
            # Copy all fields from the function spec
            for key in ["function_name", "description", "parameters", "return_type", "usage_guidance"]:
                if key in func:
                    value = func[key]
                    # Ensure text fields are arrays
                    if key in ["description", "usage_guidance"] and isinstance(value, str):
                        func_item[key] = [value]
                    else:
                        func_item[key] = value
            
            function_list.append(func_item)
        
        if function_list:
            # Sort by ID (required by Databricks API)
            function_list.sort(key=lambda x: x["id"])
            instructions_section["sql_functions"] = function_list
    
    # 5. SQL Snippets (filters, expressions, measures)
    sql_snippets = config.get("sql_snippets", {})
    if sql_snippets:
        snippets_section = {}
        
        # 5a. Filters (WHERE conditions)
        filters = sql_snippets.get("filters", [])
        if filters:
            filter_list = []
            for filt in filters:
                filter_item = {
                    "id": _generate_id(),
                    "sql": [filt["sql"]] if isinstance(filt.get("sql"), str) else filt.get("sql", []),
                    "display_name": filt.get("display_name", ""),
                }
                if "synonyms" in filt:
                    filter_item["synonyms"] = filt["synonyms"] if isinstance(filt["synonyms"], list) else [filt["synonyms"]]
                
                filter_list.append(filter_item)
            
            # Sort by ID (required by Databricks API)
            filter_list.sort(key=lambda x: x["id"])
            snippets_section["filters"] = filter_list
        
        # 5b. Expressions (row-level calculations)
        expressions = sql_snippets.get("expressions", [])
        if expressions:
            expr_list = []
            for expr in expressions:
                expr_item = {
                    "id": _generate_id(),
                    "alias": expr.get("alias", ""),
                    "sql": [expr["sql"]] if isinstance(expr.get("sql"), str) else expr.get("sql", []),
                    "display_name": expr.get("display_name", ""),
                }
                if "synonyms" in expr:
                    expr_item["synonyms"] = expr["synonyms"] if isinstance(expr["synonyms"], list) else [expr["synonyms"]]
                
                # Add instruction if present (must be an array)
                if "instruction" in expr:
                    instruction = expr["instruction"]
                    if isinstance(instruction, str):
                        expr_item["instruction"] = [instruction]
                    elif isinstance(instruction, list):
                        expr_item["instruction"] = instruction
                
                expr_list.append(expr_item)
            
            # Sort by ID (required by Databricks API)
            expr_list.sort(key=lambda x: x["id"])
            snippets_section["expressions"] = expr_list
        
        # 5c. Measures (aggregation expressions)
        measures = sql_snippets.get("measures", [])
        if measures:
            measure_list = []
            for measure in measures:
                measure_item = {
                    "id": _generate_id(),
                    "alias": measure.get("alias", ""),
                    "sql": [measure["sql"]] if isinstance(measure.get("sql"), str) else measure.get("sql", []),
                    "display_name": measure.get("display_name", ""),
                }
                if "synonyms" in measure:
                    measure_item["synonyms"] = measure["synonyms"] if isinstance(measure["synonyms"], list) else [measure["synonyms"]]
                
                # Add instruction if present (must be an array)
                if "instruction" in measure:
                    instruction = measure["instruction"]
                    if isinstance(instruction, str):
                        measure_item["instruction"] = [instruction]
                    elif isinstance(instruction, list):
                        measure_item["instruction"] = instruction
                
                measure_list.append(measure_item)
            
            # Sort by ID (required by Databricks API)
            measure_list.sort(key=lambda x: x["id"])
            snippets_section["measures"] = measure_list
        
        if snippets_section:
            instructions_section["sql_snippets"] = snippets_section
    
    # Add instructions section if it has any content
    if instructions_section:
        serialized_space["instructions"] = instructions_section
    
    # =========================================================================
    # BENCHMARKS SECTION (top-level, not nested in instructions)
    # =========================================================================
    # IMPORTANT: Databricks API requires each benchmark to have at least one answer,
    # and only supports "SQL" format. We skip benchmarks without SQL (e.g., FAQ questions).
    benchmarks = config.get("benchmark_questions", [])
    if benchmarks:
        benchmark_questions = []
        for benchmark in benchmarks:
            question = benchmark.get("question", "")
            expected_sql = benchmark.get("expected_sql", "")
            
            # Only include benchmarks that have SQL (API requirement)
            if question and expected_sql:
                benchmark_q = {
                    "id": _generate_id(),
                    "question": _to_string_array(question),
                    "answer": [{
                        "format": "SQL",
                        "content": _to_string_array(expected_sql)
                    }]
                }
                benchmark_questions.append(benchmark_q)
        
        if benchmark_questions:
            # Sort by ID (required by Databricks API)
            benchmark_questions.sort(key=lambda x: x["id"])
            serialized_space["benchmarks"] = {
                "questions": benchmark_questions
            }
    
    # Convert to JSON string
    return json.dumps(serialized_space, ensure_ascii=False)


def load_and_transform_config(config_path: str) -> tuple[Dict[str, Any], str]:
    """
    Load configuration file and transform it.
    
    Args:
        config_path: Path to the configuration JSON file
        
    Returns:
        Tuple of (original_config, serialized_space_string)
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        full_config = json.load(f)
    
    # Extract the genie_space_config if present
    if "genie_space_config" in full_config:
        config = full_config["genie_space_config"]
    else:
        config = full_config
    
    # Transform to serialized format
    serialized_space = transform_to_serialized_space(config)
    
    return config, serialized_space
