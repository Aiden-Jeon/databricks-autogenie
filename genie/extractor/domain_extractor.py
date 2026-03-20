"""
Domain knowledge extraction from requirements documents.

This module extracts structured domain knowledge from requirements:
- Table relationships and join patterns
- Business metrics and formulas
- Common filters and WHERE clauses
- Business terminology and definitions
"""

import re
from typing import Dict, List, Set, Tuple, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TableRelationship:
    """Represents a relationship between two tables."""
    left_table: str
    right_table: str
    relationship_type: str  # "one-to-one", "one-to-many", "many-to-one", "many-to-many"
    join_column_left: Optional[str] = None
    join_column_right: Optional[str] = None
    description: Optional[str] = None

    def to_join_spec(self) -> Dict[str, Any]:
        """Convert to join specification format."""
        # Map relationship types to join types
        type_map = {
            "one-to-one": "INNER",
            "one-to-many": "LEFT",
            "many-to-one": "INNER",
            "many-to-many": "INNER"
        }

        join_type = type_map.get(self.relationship_type, "INNER")

        if self.join_column_left and self.join_column_right:
            join_condition = f"{self.left_table}.{self.join_column_left} = {self.right_table}.{self.join_column_right}"
        else:
            join_condition = f"{self.left_table}.id = {self.right_table}.{self.left_table}_id"

        return {
            "left_table": self.left_table,
            "right_table": self.right_table,
            "join_type": join_type,
            "join_condition": join_condition,
            "description": self.description or f"{self.relationship_type} relationship"
        }


@dataclass
class BusinessMetric:
    """Represents a business metric definition."""
    name: str
    formula: str
    description: Optional[str] = None
    sql_expression: Optional[str] = None
    type: str = "metric"  # "metric", "dimension", "filter"


@dataclass
class CommonFilter:
    """Represents a commonly used filter."""
    name: str
    condition: str
    description: Optional[str] = None
    examples: List[str] = field(default_factory=list)


@dataclass
class DomainKnowledge:
    """Complete extracted domain knowledge."""
    table_relationships: List[TableRelationship] = field(default_factory=list)
    business_metrics: List[BusinessMetric] = field(default_factory=list)
    common_filters: List[CommonFilter] = field(default_factory=list)
    table_descriptions: Dict[str, str] = field(default_factory=dict)
    business_terms: Dict[str, str] = field(default_factory=dict)
    sample_queries: List[Dict[str, str]] = field(default_factory=list)

    def to_structured_context(self) -> str:
        """Convert to structured context for prompt injection."""
        sections = []

        # Table Relationships
        if self.table_relationships:
            sections.append("## Extracted Table Relationships\n")
            for rel in self.table_relationships:
                sections.append(f"- **{rel.left_table}** ({rel.relationship_type}) **{rel.right_table}**")
                if rel.join_column_left and rel.join_column_right:
                    sections.append(f"  - Join: `{rel.join_column_left}` = `{rel.join_column_right}`")
                if rel.description:
                    sections.append(f"  - {rel.description}")
                sections.append("")

        # Business Metrics
        if self.business_metrics:
            sections.append("\n## Key Business Metrics\n")
            for metric in self.business_metrics:
                sections.append(f"- **{metric.name}**")
                if metric.formula:
                    sections.append(f"  - Formula: `{metric.formula}`")
                if metric.sql_expression:
                    sections.append(f"  - SQL: `{metric.sql_expression}`")
                if metric.description:
                    sections.append(f"  - {metric.description}")
                sections.append("")

        # Common Filters
        if self.common_filters:
            sections.append("\n## Standard Filters\n")
            for filter_def in self.common_filters:
                sections.append(f"- **{filter_def.name}**: `{filter_def.condition}`")
                if filter_def.description:
                    sections.append(f"  - {filter_def.description}")
                sections.append("")

        # Business Terms
        if self.business_terms:
            sections.append("\n## Business Terminology\n")
            for term, definition in self.business_terms.items():
                sections.append(f"- **{term}**: {definition}")
            sections.append("")

        return "\n".join(sections)

    def summary(self) -> str:
        """Get human-readable summary."""
        return (
            f"Domain Knowledge Extracted:\n"
            f"  - Table Relationships: {len(self.table_relationships)}\n"
            f"  - Business Metrics: {len(self.business_metrics)}\n"
            f"  - Common Filters: {len(self.common_filters)}\n"
            f"  - Business Terms: {len(self.business_terms)}\n"
            f"  - Sample Queries: {len(self.sample_queries)}"
        )


class DomainKnowledgeExtractor:
    """
    Extracts domain knowledge from requirements documents.

    Patterns recognized:
    - Table relationships (from ERD, relationship descriptions)
    - Business metrics (KPIs, formulas, calculations)
    - Common filters (status filters, date ranges, exclusions)
    - Business terminology (domain-specific definitions)
    """

    # Patterns for table relationships
    RELATIONSHIP_PATTERNS = [
        # "customers (1) -> orders (N)"
        r'(\w+)\s*\(1\)\s*[-→>]+\s*(\w+)\s*\(N\)',
        # "orders N:1 customers"
        r'(\w+)\s+N:1\s+(\w+)',
        # "each customer has many orders"
        r'each\s+(\w+)\s+has\s+many\s+(\w+)',
        # "transactions belong to customers"
        r'(\w+)\s+belong\s+to\s+(\w+)',
        # "join customers on customer_id"
        r'join\s+(\w+)\s+on\s+(\w+)',
    ]

    # Patterns for business metrics
    METRIC_PATTERNS = [
        # "ARPU = revenue / customers"
        r'(\w+)\s*=\s*([^=\n]+)',
        # "Revenue: SUM(amount)"
        r'(\w+):\s*(SUM|COUNT|AVG|MAX|MIN)\s*\([^)]+\)',
        # "Calculate total_revenue as SUM(amount)"
        r'calculate\s+(\w+)\s+as\s+([^.\n]+)',
    ]

    # Patterns for common filters
    FILTER_PATTERNS = [
        # "status != 'cancelled'"
        r"(status|state)\s*[!=<>]+\s*'[^']+'",
        # "event_date >= DATE_SUB(CURRENT_DATE(), 30)"
        r'(\w+_date|\w+_time)\s*[>=<]+\s*[^,\n]+',
        # "is_active = true"
        r'(is_\w+|has_\w+)\s*=\s*(true|false|1|0)',
        # "type IN ('A', 'B', 'C')"
        r"(\w+)\s+IN\s*\([^)]+\)",
    ]

    def __init__(self):
        """Initialize the domain knowledge extractor."""
        pass

    def extract_from_file(self, file_path: str) -> DomainKnowledge:
        """
        Extract domain knowledge from a requirements file.

        Args:
            file_path: Path to requirements document

        Returns:
            DomainKnowledge with extracted information
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Requirements file not found: {file_path}")

        content = path.read_text(encoding='utf-8')
        return self.extract_from_text(content)

    def extract_from_text(self, content: str) -> DomainKnowledge:
        """
        Extract domain knowledge from text content.

        Args:
            content: Requirements document text

        Returns:
            DomainKnowledge with extracted information
        """
        knowledge = DomainKnowledge()

        # Extract table relationships
        knowledge.table_relationships = self._extract_table_relationships(content)

        # Extract business metrics
        knowledge.business_metrics = self._extract_business_metrics(content)

        # Extract common filters
        knowledge.common_filters = self._extract_common_filters(content)

        # Extract table descriptions
        knowledge.table_descriptions = self._extract_table_descriptions(content)

        # Extract business terms
        knowledge.business_terms = self._extract_business_terms(content)

        # Extract sample queries
        knowledge.sample_queries = self._extract_sample_queries(content)

        return knowledge

    def _extract_table_relationships(self, content: str) -> List[TableRelationship]:
        """Extract table relationships from content."""
        relationships = []
        seen = set()

        # Look for explicit relationship patterns
        for pattern in self.RELATIONSHIP_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) >= 2:
                    left_table = match.group(1).lower()
                    right_table = match.group(2).lower()

                    # Avoid duplicates
                    key = f"{left_table}-{right_table}"
                    if key in seen:
                        continue
                    seen.add(key)

                    # Infer relationship type from pattern
                    if "(1)" in match.group(0) and "(N)" in match.group(0):
                        rel_type = "one-to-many"
                    elif "N:1" in match.group(0):
                        rel_type = "many-to-one"
                    elif "belong to" in match.group(0).lower():
                        rel_type = "many-to-one"
                    elif "has many" in match.group(0).lower():
                        rel_type = "one-to-many"
                    else:
                        rel_type = "many-to-one"  # default

                    relationships.append(TableRelationship(
                        left_table=left_table,
                        right_table=right_table,
                        relationship_type=rel_type,
                        description=match.group(0)
                    ))

        # Look for join patterns in SQL examples
        join_pattern = r'JOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)?\s+ON\s+([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)'
        join_matches = re.finditer(join_pattern, content, re.IGNORECASE)

        for match in join_matches:
            right_table = match.group(1).lower()
            left_alias = match.group(3).split('.')[0].lower()
            right_alias = match.group(4).split('.')[0].lower()
            left_col = match.group(3).split('.')[1].lower()
            right_col = match.group(4).split('.')[1].lower()

            # Try to find the left table name
            from_pattern = rf'FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:AS\s+)?{left_alias}\b'
            from_match = re.search(from_pattern, content, re.IGNORECASE)
            if from_match:
                left_table = from_match.group(1).lower()

                key = f"{left_table}-{right_table}"
                if key not in seen:
                    seen.add(key)
                    relationships.append(TableRelationship(
                        left_table=left_table,
                        right_table=right_table,
                        relationship_type="many-to-one",
                        join_column_left=left_col,
                        join_column_right=right_col,
                        description=f"Extracted from SQL JOIN"
                    ))

        return relationships

    def _extract_business_metrics(self, content: str) -> List[BusinessMetric]:
        """Extract business metric definitions from content."""
        metrics = []
        seen = set()

        # Look for explicit metric definitions
        for pattern in self.METRIC_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                name = match.group(1).strip()
                formula = match.group(2).strip() if len(match.groups()) > 1 else ""

                # Avoid duplicates
                if name.lower() in seen:
                    continue
                seen.add(name.lower())

                # Determine metric type
                if any(agg in formula.upper() for agg in ['SUM', 'COUNT', 'AVG', 'MAX', 'MIN']):
                    metric_type = "metric"
                else:
                    metric_type = "dimension"

                metrics.append(BusinessMetric(
                    name=name,
                    formula=formula,
                    type=metric_type
                ))

        # Look for KPI sections
        kpi_pattern = r'##\s*(?:KPI|Metrics|Key\s+Metrics)[^\n]*\n((?:[-*]\s+.+\n?)+)'
        kpi_matches = re.finditer(kpi_pattern, content, re.IGNORECASE)

        for match in kpi_matches:
            items_text = match.group(1)
            items = re.findall(r'[-*]\s+([^:\n]+)(?::\s*([^\n]+))?', items_text)

            for name, description in items:
                name = name.strip()
                if name.lower() not in seen:
                    seen.add(name.lower())
                    metrics.append(BusinessMetric(
                        name=name,
                        formula="",
                        description=description.strip() if description else None,
                        type="metric"
                    ))

        return metrics

    def _extract_common_filters(self, content: str) -> List[CommonFilter]:
        """Extract common filter patterns from content."""
        filters = []
        seen = set()

        for pattern in self.FILTER_PATTERNS:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                filter_text = match.group(0).strip()

                # Avoid duplicates
                if filter_text.lower() in seen:
                    continue
                seen.add(filter_text.lower())

                # Extract filter name
                if '=' in filter_text or '!=' in filter_text or '<' in filter_text or '>' in filter_text:
                    name = filter_text.split('=')[0].strip().split('<')[0].strip().split('>')[0].strip()
                elif ' IN ' in filter_text.upper():
                    name = filter_text.split(' IN ')[0].strip()
                else:
                    name = "filter"

                filters.append(CommonFilter(
                    name=name,
                    condition=filter_text,
                    description=f"Common filter: {filter_text}"
                ))

        return filters

    def _extract_table_descriptions(self, content: str) -> Dict[str, str]:
        """Extract table descriptions from content."""
        descriptions = {}

        # Look for table sections with descriptions
        # Pattern: ## table_name or ### table_name followed by description
        table_pattern = r'###+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\n([^\n#]+)'
        matches = re.finditer(table_pattern, content, re.IGNORECASE)

        for match in matches:
            table_name = match.group(1).strip().lower()
            description = match.group(2).strip()
            descriptions[table_name] = description

        return descriptions

    def _extract_business_terms(self, content: str) -> Dict[str, str]:
        """Extract business terminology definitions."""
        terms = {}

        # Look for glossary or terminology sections
        glossary_pattern = r'##\s*(?:Glossary|Terminology|Definitions)[^\n]*\n((?:[-*]\s+.+\n?)+)'
        glossary_matches = re.finditer(glossary_pattern, content, re.IGNORECASE)

        for match in glossary_matches:
            items_text = match.group(1)
            # Pattern: - Term: Definition or * Term: Definition
            items = re.findall(r'[-*]\s+([^:\n]+):\s*([^\n]+)', items_text)

            for term, definition in items:
                terms[term.strip()] = definition.strip()

        # Look for inline definitions (Term: definition)
        inline_pattern = r'\*\*([A-Z][A-Za-z\s]+)\*\*:\s*([^.\n]+)'
        inline_matches = re.finditer(inline_pattern, content)

        for match in inline_matches:
            term = match.group(1).strip()
            definition = match.group(2).strip()
            if term not in terms:
                terms[term] = definition

        return terms

    def _extract_sample_queries(self, content: str) -> List[Dict[str, str]]:
        """Extract sample SQL queries from content."""
        queries = []

        # Look for SQL code blocks
        sql_pattern = r'```sql\s*\n(.*?)\n```'
        matches = re.finditer(sql_pattern, content, re.DOTALL | re.IGNORECASE)

        for match in matches:
            sql = match.group(1).strip()

            # Try to find associated question
            # Look backwards for a question or comment before the SQL block
            start_pos = match.start()
            preceding_text = content[max(0, start_pos - 200):start_pos]
            question_match = re.search(r'([^\n]+\?)\s*$', preceding_text)

            question = question_match.group(1).strip() if question_match else None

            queries.append({
                "question": question,
                "sql": sql
            })

        return queries


def extract_domain_knowledge(requirements_path: str, verbose: bool = False) -> DomainKnowledge:
    """
    Convenience function to extract domain knowledge from requirements file.

    Args:
        requirements_path: Path to requirements document
        verbose: Print extraction progress

    Returns:
        DomainKnowledge with extracted information
    """
    extractor = DomainKnowledgeExtractor()

    if verbose:
        print(f"📚 Extracting domain knowledge from {requirements_path}...")

    knowledge = extractor.extract_from_file(requirements_path)

    if verbose:
        print(knowledge.summary())

    return knowledge
