"""Utilities for updating Genie space configuration files."""

import json
from typing import Dict


def update_config_catalog_schema_table(
    config_path: str,
    old_catalog: str,
    old_schema: str,
    old_table: str,
    new_catalog: str,
    new_schema: str,
    new_table: str
) -> Dict:
    """
    Update catalog, schema, and table name in configuration file.

    Args:
        config_path: Path to the configuration JSON file
        old_catalog: Old catalog name
        old_schema: Old schema name
        old_table: Old table name
        new_catalog: New catalog name
        new_schema: New schema name
        new_table: New table name

    Returns:
        Dictionary with counts of updated items
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Get the genie_space_config
    if "genie_space_config" in config:
        genie_config = config["genie_space_config"]
    else:
        genie_config = config

    # Build old and new full table identifiers
    old_full_table = f"{old_catalog}.{old_schema}.{old_table}"
    new_full_table = f"{new_catalog}.{new_schema}.{new_table}"

    # Update tables
    updated_count = 0
    for table_def in genie_config.get("tables", []):
        if (table_def.get("catalog_name") == old_catalog and
            table_def.get("schema_name") == old_schema and
            table_def.get("table_name") == old_table):
            table_def["catalog_name"] = new_catalog
            table_def["schema_name"] = new_schema
            table_def["table_name"] = new_table
            updated_count += 1

    # Update SQL snippets - replace full table references
    sql_expr_count = 0
    sql_snippets = genie_config.get("sql_snippets", {})

    # Update filters
    for filt in sql_snippets.get("filters", []):
        if "sql" in filt and old_full_table in filt["sql"]:
            filt["sql"] = filt["sql"].replace(old_full_table, new_full_table)
            sql_expr_count += 1

    # Update expressions
    for expr in sql_snippets.get("expressions", []):
        if "sql" in expr and old_full_table in expr["sql"]:
            expr["sql"] = expr["sql"].replace(old_full_table, new_full_table)
            sql_expr_count += 1

    # Update measures
    for measure in sql_snippets.get("measures", []):
        if "sql" in measure and old_full_table in measure["sql"]:
            measure["sql"] = measure["sql"].replace(old_full_table, new_full_table)
            sql_expr_count += 1

    # Update example queries - replace full table references
    example_query_count = 0
    for query in genie_config.get("example_sql_queries", []):
        if "sql_query" in query and old_full_table in query["sql_query"]:
            query["sql_query"] = query["sql_query"].replace(old_full_table, new_full_table)
            example_query_count += 1

    # Update benchmark questions
    benchmark_count = 0
    for benchmark in genie_config.get("benchmark_questions", []):
        updated_this_benchmark = False

        # Update expected_sql field (may be null for FAQ items)
        if "expected_sql" in benchmark and benchmark["expected_sql"] and old_full_table in benchmark["expected_sql"]:
            benchmark["expected_sql"] = benchmark["expected_sql"].replace(old_full_table, new_full_table)
            updated_this_benchmark = True

        # Update table field (contains backtick-quoted table names)
        if "table" in benchmark and benchmark["table"]:
            old_table_ref = f"`{old_full_table}`"
            new_table_ref = f"`{new_full_table}`"
            if old_table_ref in benchmark["table"]:
                benchmark["table"] = benchmark["table"].replace(old_table_ref, new_table_ref)
                updated_this_benchmark = True

        if updated_this_benchmark:
            benchmark_count += 1

    # Update instructions - replace full table references
    instruction_count = 0
    for instruction in genie_config.get("instructions", []):
        if "content" in instruction and old_full_table in instruction["content"]:
            instruction["content"] = instruction["content"].replace(old_full_table, new_full_table)
            instruction_count += 1

    # Update joins if they reference this table
    join_count = 0
    for join in genie_config.get("joins", []):
        updated_this_join = False

        if join.get("left_table") == old_full_table:
            join["left_table"] = new_full_table
            join["left_alias"] = new_table
            updated_this_join = True

        if join.get("right_table") == old_full_table:
            join["right_table"] = new_full_table
            join["right_alias"] = new_table
            updated_this_join = True

        # Update join condition
        if "join_condition" in join and old_full_table in join["join_condition"]:
            join["join_condition"] = join["join_condition"].replace(old_full_table, new_full_table)
            updated_this_join = True

        # Also replace old table alias references in join condition
        if "join_condition" in join:
            old_alias_pattern = f"{old_table}."
            new_alias_pattern = f"{new_table}."
            if old_alias_pattern in join["join_condition"]:
                join["join_condition"] = join["join_condition"].replace(old_alias_pattern, new_alias_pattern)
                updated_this_join = True

        if updated_this_join:
            join_count += 1

    # Update join_specifications if they exist (alternative format)
    join_spec_count = 0
    for join_spec in genie_config.get("join_specifications", []):
        updated_this_spec = False

        if join_spec.get("left_table") == old_full_table:
            join_spec["left_table"] = new_full_table
            updated_this_spec = True

        if join_spec.get("right_table") == old_full_table:
            join_spec["right_table"] = new_full_table
            updated_this_spec = True

        # Update join condition
        if "join_condition" in join_spec and old_full_table in join_spec["join_condition"]:
            join_spec["join_condition"] = join_spec["join_condition"].replace(old_full_table, new_full_table)
            updated_this_spec = True

        # Also replace table aliases in join condition
        if "join_condition" in join_spec:
            old_alias_pattern = f"{old_table}."
            new_alias_pattern = f"{new_table}."
            if old_alias_pattern in join_spec["join_condition"]:
                join_spec["join_condition"] = join_spec["join_condition"].replace(old_alias_pattern, new_alias_pattern)
                updated_this_spec = True

        if updated_this_spec:
            join_spec_count += 1

    # Save back to file
    if "genie_space_config" in config:
        config["genie_space_config"] = genie_config
    else:
        config = genie_config

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return {
        'tables': updated_count,
        'sql_expressions': sql_expr_count,
        'example_queries': example_query_count,
        'benchmark_questions': benchmark_count,
        'instructions': instruction_count,
        'joins': join_count,
        'join_specifications': join_spec_count
    }


def update_config_catalog_schema(config_path: str, old_catalog: str, old_schema: str, new_catalog: str, new_schema: str) -> Dict:
    """
    Update catalog and schema in configuration file (legacy function, kept for backwards compatibility).
    This function updates ALL tables with matching catalog.schema.

    For individual table updates, use update_config_catalog_schema_table instead.
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Get the genie_space_config
    if "genie_space_config" in config:
        genie_config = config["genie_space_config"]
    else:
        genie_config = config

    # Update tables
    updated_count = 0
    for table_def in genie_config.get("tables", []):
        if table_def.get("catalog_name") == old_catalog and table_def.get("schema_name") == old_schema:
            table_def["catalog_name"] = new_catalog
            table_def["schema_name"] = new_schema
            updated_count += 1

    # Update SQL snippets
    sql_expr_count = 0
    old_prefix = f"{old_catalog}.{old_schema}."
    new_prefix = f"{new_catalog}.{new_schema}."

    sql_snippets = genie_config.get("sql_snippets", {})

    # Update filters
    for filt in sql_snippets.get("filters", []):
        if "sql" in filt and old_prefix in filt["sql"]:
            filt["sql"] = filt["sql"].replace(old_prefix, new_prefix)
            sql_expr_count += 1

    # Update expressions
    for expr in sql_snippets.get("expressions", []):
        if "sql" in expr and old_prefix in expr["sql"]:
            expr["sql"] = expr["sql"].replace(old_prefix, new_prefix)
            sql_expr_count += 1

    # Update measures
    for measure in sql_snippets.get("measures", []):
        if "sql" in measure and old_prefix in measure["sql"]:
            measure["sql"] = measure["sql"].replace(old_prefix, new_prefix)
            sql_expr_count += 1

    # Update example queries
    example_query_count = 0
    for query in genie_config.get("example_sql_queries", []):
        old_prefix = f"{old_catalog}.{old_schema}."
        new_prefix = f"{new_catalog}.{new_schema}."
        if "sql_query" in query and old_prefix in query["sql_query"]:
            query["sql_query"] = query["sql_query"].replace(old_prefix, new_prefix)
            example_query_count += 1

    # Update benchmark questions
    benchmark_count = 0
    for benchmark in genie_config.get("benchmark_questions", []):
        old_prefix = f"{old_catalog}.{old_schema}."
        new_prefix = f"{new_catalog}.{new_schema}."
        updated_this_benchmark = False

        # Update expected_sql field (may be null for FAQ items)
        if "expected_sql" in benchmark and benchmark["expected_sql"] and old_prefix in benchmark["expected_sql"]:
            benchmark["expected_sql"] = benchmark["expected_sql"].replace(old_prefix, new_prefix)
            updated_this_benchmark = True

        # Update table field (contains backtick-quoted table names)
        if "table" in benchmark and benchmark["table"]:
            old_table_ref = f"`{old_catalog}.{old_schema}."
            new_table_ref = f"`{new_catalog}.{new_schema}."
            if old_table_ref in benchmark["table"]:
                benchmark["table"] = benchmark["table"].replace(old_table_ref, new_table_ref)
                updated_this_benchmark = True

        if updated_this_benchmark:
            benchmark_count += 1

    # Update instructions
    instruction_count = 0
    for instruction in genie_config.get("instructions", []):
        old_prefix = f"{old_catalog}.{old_schema}."
        new_prefix = f"{new_catalog}.{new_schema}."
        if "content" in instruction and old_prefix in instruction["content"]:
            instruction["content"] = instruction["content"].replace(old_prefix, new_prefix)
            instruction_count += 1

    # Update joins
    join_count = 0
    for join in genie_config.get("joins", []):
        updated_this_join = False
        old_prefix = f"{old_catalog}.{old_schema}."
        new_prefix = f"{new_catalog}.{new_schema}."

        if "left_table" in join and old_prefix in join["left_table"]:
            join["left_table"] = join["left_table"].replace(old_prefix, new_prefix)
            updated_this_join = True

        if "right_table" in join and old_prefix in join["right_table"]:
            join["right_table"] = join["right_table"].replace(old_prefix, new_prefix)
            updated_this_join = True

        if "join_condition" in join and old_prefix in join["join_condition"]:
            join["join_condition"] = join["join_condition"].replace(old_prefix, new_prefix)
            updated_this_join = True

        if updated_this_join:
            join_count += 1

    # Update join_specifications
    join_spec_count = 0
    for join_spec in genie_config.get("join_specifications", []):
        updated_this_spec = False
        old_prefix = f"{old_catalog}.{old_schema}."
        new_prefix = f"{new_catalog}.{new_schema}."

        if "left_table" in join_spec and old_prefix in join_spec["left_table"]:
            join_spec["left_table"] = join_spec["left_table"].replace(old_prefix, new_prefix)
            updated_this_spec = True

        if "right_table" in join_spec and old_prefix in join_spec["right_table"]:
            join_spec["right_table"] = join_spec["right_table"].replace(old_prefix, new_prefix)
            updated_this_spec = True

        if "join_condition" in join_spec and old_prefix in join_spec["join_condition"]:
            join_spec["join_condition"] = join_spec["join_condition"].replace(old_prefix, new_prefix)
            updated_this_spec = True

        if updated_this_spec:
            join_spec_count += 1

    # Save back to file
    if "genie_space_config" in config:
        config["genie_space_config"] = genie_config
    else:
        config = genie_config

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return {
        'tables': updated_count,
        'sql_expressions': sql_expr_count,
        'example_queries': example_query_count,
        'benchmark_questions': benchmark_count,
        'instructions': instruction_count,
        'joins': join_count,
        'join_specifications': join_spec_count
    }


def remove_table_from_config(config_path: str, catalog: str, schema: str, table: str) -> Dict:
    """
    Remove a table and all its references from the configuration.

    Args:
        config_path: Path to the configuration JSON file
        catalog: Catalog name
        schema: Schema name
        table: Table name

    Returns:
        Dictionary with counts of removed items
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Get the genie_space_config
    if "genie_space_config" in config:
        genie_config = config["genie_space_config"]
    else:
        genie_config = config

    full_table = f"{catalog}.{schema}.{table}"

    # Remove from tables array
    tables_before = len(genie_config.get("tables", []))
    genie_config["tables"] = [
        t for t in genie_config.get("tables", [])
        if not (t.get("catalog_name") == catalog and
                t.get("schema_name") == schema and
                t.get("table_name") == table)
    ]
    tables_removed = tables_before - len(genie_config.get("tables", []))

    # Remove SQL expressions that reference this table
    sql_snippets = genie_config.get("sql_snippets", {})

    filters_before = len(sql_snippets.get("filters", []))
    sql_snippets["filters"] = [
        f for f in sql_snippets.get("filters", [])
        if full_table not in f.get("sql", "")
    ]
    filters_removed = filters_before - len(sql_snippets.get("filters", []))

    expressions_before = len(sql_snippets.get("expressions", []))
    sql_snippets["expressions"] = [
        e for e in sql_snippets.get("expressions", [])
        if full_table not in e.get("sql", "")
    ]
    expressions_removed = expressions_before - len(sql_snippets.get("expressions", []))

    measures_before = len(sql_snippets.get("measures", []))
    sql_snippets["measures"] = [
        m for m in sql_snippets.get("measures", [])
        if full_table not in m.get("sql", "")
    ]
    measures_removed = measures_before - len(sql_snippets.get("measures", []))

    # Remove example queries that reference this table
    queries_before = len(genie_config.get("example_sql_queries", []))
    genie_config["example_sql_queries"] = [
        q for q in genie_config.get("example_sql_queries", [])
        if full_table not in q.get("sql_query", "")
    ]
    queries_removed = queries_before - len(genie_config.get("example_sql_queries", []))

    # Remove benchmark questions that reference this table
    benchmarks_before = len(genie_config.get("benchmark_questions", []))
    genie_config["benchmark_questions"] = [
        b for b in genie_config.get("benchmark_questions", [])
        if full_table not in b.get("expected_sql", "") and
           f"`{full_table}`" not in b.get("table", "")
    ]
    benchmarks_removed = benchmarks_before - len(genie_config.get("benchmark_questions", []))

    # Remove instructions that reference this table
    instructions_before = len(genie_config.get("instructions", []))
    genie_config["instructions"] = [
        i for i in genie_config.get("instructions", [])
        if full_table not in i.get("content", "")
    ]
    instructions_removed = instructions_before - len(genie_config.get("instructions", []))

    # Remove joins that reference this table
    joins_before = len(genie_config.get("joins", []))
    genie_config["joins"] = [
        j for j in genie_config.get("joins", [])
        if j.get("left_table") != full_table and j.get("right_table") != full_table
    ]
    joins_removed = joins_before - len(genie_config.get("joins", []))

    # Remove join_specifications that reference this table
    join_specs_before = len(genie_config.get("join_specifications", []))
    genie_config["join_specifications"] = [
        js for js in genie_config.get("join_specifications", [])
        if js.get("left_table") != full_table and js.get("right_table") != full_table
    ]
    join_specs_removed = join_specs_before - len(genie_config.get("join_specifications", []))

    # Save back to file
    if "genie_space_config" in config:
        config["genie_space_config"] = genie_config
    else:
        config = genie_config

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return {
        'tables': tables_removed,
        'sql_filters': filters_removed,
        'sql_expressions': expressions_removed,
        'sql_measures': measures_removed,
        'example_queries': queries_removed,
        'benchmark_questions': benchmarks_removed,
        'instructions': instructions_removed,
        'joins': joins_removed,
        'join_specifications': join_specs_removed
    }
