"""Extract SQL query examples directly from requirements documents.

This module extracts sample queries from requirements and converts them
to SQL query examples for teaching Genie AI how to answer questions.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from genie.models import GenieSpaceExampleSQL, GenieSpaceConfig


def extract_sample_queries_as_examples(
    requirements_path: str
) -> List[GenieSpaceExampleSQL]:
    """
    Extract sample SQL queries from requirements document as SQL examples.

    This function supports two formats:

    Format 1 (original): Sections with **Sample Questions:** and **Sample Query:**
        ## Section Title
        **Table:** table_name
        **Sample Questions:**
        1. Question text 1
        2. Question text 2
        **Sample Query:**
        ```sql
        SELECT ...
        ```

    Format 2 (Korean requirements): Subsections with question in header and **예시 쿼리:** marker
        ### N. Question text here
        **필요한 테이블:**
        ...
        **예시 쿼리:**
        ```sql
        SELECT ...
        ```

    Args:
        requirements_path: Path to the requirements document

    Returns:
        List of GenieSpaceExampleSQL objects extracted from requirements.
        Only includes questions that have SQL queries.

    Example:
        >>> examples = extract_sample_queries_as_examples("data/parsed_requirements.md")
        >>> examples[0]
        GenieSpaceExampleSQL(
            question="디스코드에서 리액션이 가장 많은 메시지는 무엇인가요?",
            sql_query="WITH hot_messages AS (...",
            description=None
        )
    """
    doc_path = Path(requirements_path)

    if not doc_path.exists():
        raise FileNotFoundError(f"Requirements file not found: {doc_path}")

    with open(doc_path, 'r', encoding='utf-8') as f:
        content = f.read()

    examples = []
    lines = content.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i]

        # FORMAT 2: Look for subsection headers (### N. Question text)
        # Example: ### 3. 전체 소셜 플랫폼에서 반응이 가장 많은 주제는 무엇인가요?
        subsection_match = re.match(r'^###\s+\d+\.\s+(.+)$', line.strip())
        if subsection_match:
            question_text = subsection_match.group(1)
            sample_sql = None

            # Look for **예시 쿼리:** (Example Query in Korean) in the following lines
            j = i + 1
            while j < len(lines) and not lines[j].startswith('###'):
                # Check for example query marker (Korean: 예시 쿼리)
                if '**예시 쿼리:**' in lines[j] or '**Sample Query:**' in lines[j]:
                    # Found example query marker - extract SQL
                    sql_lines = []
                    k = j + 1

                    # Skip to the start of SQL block
                    while k < len(lines) and not lines[k].strip().startswith('```sql'):
                        k += 1

                    if k < len(lines):
                        k += 1  # Skip the ```sql line

                        # Extract SQL until we hit the closing ```
                        while k < len(lines) and not lines[k].strip().startswith('```'):
                            sql_lines.append(lines[k])
                            k += 1

                        # Build the SQL query
                        if sql_lines:
                            sample_sql = '\n'.join(sql_lines)

                    break  # Found and processed the example query

                j += 1

            # Create example if we found SQL
            if sample_sql:
                examples.append(
                    GenieSpaceExampleSQL(
                        question=question_text,
                        sql_query=sample_sql,
                        description=None
                    )
                )

            i += 1
            continue

        # FORMAT 1: Look for section headers (## Title)
        if line.startswith('## ') and not line.startswith('###'):
            section_title = line.replace('##', '').strip()

            # Extract metadata and check for Sample Questions
            sample_questions = []
            sample_sql = None

            j = i + 1
            while j < len(lines) and not lines[j].startswith('##'):
                # Extract Sample Questions
                if lines[j].startswith('**Sample Questions:**'):
                    # Extract all numbered questions following this marker
                    k = j + 1
                    while k < len(lines):
                        stripped = lines[k].strip()
                        # Check if this is a numbered question
                        question_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
                        if question_match:
                            question_text = question_match.group(2)
                            sample_questions.append(question_text)
                            k += 1
                        elif stripped == '' or stripped.startswith('**'):
                            # Empty line or next section marker - stop collecting questions
                            break
                        else:
                            k += 1

                # Extract Sample Query
                elif lines[j].startswith('**Sample Query:**'):
                    # Found a sample query - extract the SQL
                    sql_lines = []
                    k = j + 1

                    # Skip to the start of SQL block
                    while k < len(lines) and not lines[k].strip().startswith('```sql'):
                        k += 1

                    if k < len(lines):
                        k += 1  # Skip the ```sql line

                        # Extract SQL until we hit the closing ```
                        while k < len(lines) and not lines[k].strip().startswith('```'):
                            sql_lines.append(lines[k])
                            k += 1

                        # Build the SQL query
                        if sql_lines:
                            sample_sql = '\n'.join(sql_lines)

                    break  # Found and processed the sample query for this section

                j += 1

            # Create examples only if we have BOTH sample questions AND sample SQL
            if sample_questions and sample_sql:
                for question in sample_questions:
                    examples.append(
                        GenieSpaceExampleSQL(
                            question=question,
                            sql_query=sample_sql,
                            description=None
                        )
                    )

        i += 1

    return examples


def merge_examples_into_config(
    config: GenieSpaceConfig,
    examples: List[GenieSpaceExampleSQL],
    replace: bool = True
) -> GenieSpaceConfig:
    """
    Merge extracted examples into a Genie space configuration.
    
    Args:
        config: The Genie space configuration object
        examples: List of GenieSpaceExampleSQL objects to add
        replace: If True, replace existing examples. If False, append to existing.
        
    Returns:
        Updated configuration object
    """
    if replace:
        config.example_sql_queries = examples
    else:
        # Avoid duplicates based on question text
        existing_questions = {ex.question for ex in config.example_sql_queries}
        new_examples = [ex for ex in examples if ex.question not in existing_questions]
        config.example_sql_queries.extend(new_examples)
    
    return config


def merge_examples_into_config_dict(
    config: Dict[str, Any],
    examples: List[GenieSpaceExampleSQL],
    replace: bool = True
) -> Dict[str, Any]:
    """
    Merge extracted examples into a Genie space configuration dictionary.
    
    This is a helper function for working with dict-based configs instead of Pydantic models.
    
    Args:
        config: The Genie space configuration dictionary
        examples: List of GenieSpaceExampleSQL objects to add
        replace: If True, replace existing examples. If False, append to existing.
        
    Returns:
        Updated configuration dictionary
    """
    # Convert examples to dicts
    example_dicts = [ex.model_dump() for ex in examples]
    
    if "genie_space_config" in config:
        # Handle wrapped config format
        if replace:
            config["genie_space_config"]["example_sql_queries"] = example_dicts
        else:
            existing = config["genie_space_config"].get("example_sql_queries", [])
            # Avoid duplicates
            existing_questions = {ex["question"] for ex in existing}
            new_examples = [ex for ex in example_dicts if ex["question"] not in existing_questions]
            config["genie_space_config"]["example_sql_queries"] = existing + new_examples
    else:
        # Handle direct config format
        if replace:
            config["example_sql_queries"] = example_dicts
        else:
            existing = config.get("example_sql_queries", [])
            existing_questions = {ex["question"] for ex in existing}
            new_examples = [ex for ex in example_dicts if ex["question"] not in existing_questions]
            config["example_sql_queries"] = existing + new_examples
    
    return config


def validate_examples(examples: List[GenieSpaceExampleSQL]) -> List[str]:
    """
    Validate extracted SQL examples and return list of issues.
    
    Args:
        examples: List of GenieSpaceExampleSQL objects
        
    Returns:
        List of validation issue messages (empty if all valid)
    """
    issues = []
    
    for i, example in enumerate(examples, 1):
        # Check question
        if not example.question or len(example.question.strip()) < 5:
            issues.append(f"Example {i}: Question too short or empty")
        
        # Check SQL query
        if not example.sql_query or len(example.sql_query.strip()) < 10:
            issues.append(f"Example {i}: SQL query too short or empty")
        
        # Check for SQL keywords
        sql_upper = example.sql_query.upper()
        if not any(keyword in sql_upper for keyword in ['SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE']):
            issues.append(f"Example {i}: SQL query doesn't contain expected keywords")
    
    return issues


if __name__ == "__main__":
    """Example usage and testing."""
    import json
    
    print("="*80)
    print("SQL EXAMPLE EXTRACTION - COMPREHENSIVE TEST")
    print("="*80)
    
    # Extract sample query examples
    print("\n1. Extracting sample SQL queries as examples...")
    examples = extract_sample_queries_as_examples("data/parsed.md")
    print(f"   ✓ Extracted {len(examples)} SQL examples")
    
    # Show examples
    if examples:
        print(f"\n   Sample examples:")
        for i, ex in enumerate(examples[:3], 1):
            print(f"   {i}. {ex.question}")
            sql_preview = ex.sql_query[:100].replace('\n', ' ')
            print(f"      SQL: {sql_preview}...")
    
    # Validate
    print("\n2. Validating SQL examples...")
    issues = validate_examples(examples)
    
    if issues:
        print(f"   ⚠️  {len(issues)} validation issues:")
        for issue in issues[:5]:
            print(f"       - {issue}")
    else:
        print(f"   ✓ All {len(examples)} examples are valid!")
    
    # Save to file
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert to dict format for JSON
    example_dicts = [ex.model_dump() for ex in examples]
    
    with open(output_dir / "extracted_examples.json", 'w', encoding='utf-8') as f:
        json.dump(example_dicts, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved SQL examples to: output/extracted_examples.json")
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"SQL Examples Extracted: {len(examples)}")
    print(f"Validation Issues:      {len(issues)}")
    print("="*80)
