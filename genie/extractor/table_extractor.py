"""
Rule-based table extraction from requirements documents.

This module extracts all tables explicitly mentioned in requirements using pattern matching,
providing a comprehensive list to ensure no tables are missed by LLM-only approaches.
"""

import re
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExtractedTable:
    """Represents a table extracted from requirements."""
    catalog: str
    schema: str
    table: str
    full_name: str
    description: str = ""
    sample_columns: List[str] = field(default_factory=list)
    mentioned_in_queries: int = 0
    related_questions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to config format."""
        return {
            "catalog_name": self.catalog,
            "schema_name": self.schema,
            "table_name": self.table,
            "description": self.description or f"Table {self.full_name}"
        }


class TableExtractor:
    """Extract tables from requirements using rule-based patterns."""
    
    # Pattern for fully qualified table names: catalog.schema.table
    TABLE_PATTERN_FULL = re.compile(
        r'`?([a-zA-Z_][a-zA-Z0-9_]*)\.'  # catalog
        r'([a-zA-Z_][a-zA-Z0-9_]*)\.'     # schema
        r'([a-zA-Z_][a-zA-Z0-9_]*)`?'     # table
    )
    
    # Pattern for schema.table (when catalog is implied)
    TABLE_PATTERN_PARTIAL = re.compile(
        r'`?([a-zA-Z_][a-zA-Z0-9_]*)\.'   # schema
        r'([a-zA-Z_][a-zA-Z0-9_]*)`?'     # table
        r'(?!\.[a-zA-Z_])'                # negative lookahead for third part
    )
    
    # Pattern for table sections in markdown
    TABLE_SECTION_PATTERN = re.compile(
        r'\*\*Table:\*\*\s*`([^`]+)`',
        re.IGNORECASE
    )
    
    # Pattern for column references
    COLUMN_PATTERN = re.compile(
        r'([a-zA-Z_][a-zA-Z0-9_]*\.)*([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s+',
        re.IGNORECASE
    )
    
    def __init__(self, default_catalog: str = "main", verbose: bool = False):
        """
        Initialize table extractor.
        
        Args:
            default_catalog: Default catalog to use when not specified
            verbose: Print extraction progress
        """
        self.default_catalog = default_catalog
        self.verbose = verbose
        self.tables: Dict[str, ExtractedTable] = {}
        self.current_question = None
    
    def extract_from_file(self, file_path: str) -> List[ExtractedTable]:
        """
        Extract tables from a requirements file.
        
        Args:
            file_path: Path to requirements document
            
        Returns:
            List of extracted tables with metadata
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Requirements file not found: {file_path}")
        
        content = path.read_text(encoding='utf-8')
        return self.extract_from_text(content)
    
    def extract_from_text(self, content: str) -> List[ExtractedTable]:
        """
        Extract tables from requirements text.
        
        Args:
            content: Requirements document content
            
        Returns:
            List of extracted tables with metadata
        """
        self.tables = {}
        
        # Extract from markdown table sections
        self._extract_from_table_sections(content)
        
        # Extract from SQL queries
        self._extract_from_sql_queries(content)
        
        # Extract from catalog.schema mentions in text
        self._extract_from_text_mentions(content)
        
        # Sort by mention frequency
        sorted_tables = sorted(
            self.tables.values(),
            key=lambda t: t.mentioned_in_queries,
            reverse=True
        )
        
        if self.verbose:
            print(f"\n📊 Rule-based Table Extraction Results:")
            print(f"   Total unique tables: {len(sorted_tables)}")
            for table in sorted_tables[:10]:
                print(f"   - {table.full_name} (mentioned {table.mentioned_in_queries}x)")
            if len(sorted_tables) > 10:
                print(f"   ... and {len(sorted_tables) - 10} more")
        
        return sorted_tables
    
    def _extract_from_table_sections(self, content: str):
        """Extract tables from **Table:** sections in markdown."""
        matches = self.TABLE_SECTION_PATTERN.findall(content)
        
        for table_ref in matches:
            parts = table_ref.split('.')
            
            if len(parts) == 3:
                catalog, schema, table = parts
            elif len(parts) == 2:
                schema, table = parts
                catalog = self.default_catalog
            else:
                continue
            
            # Skip invalid entries
            if not self._is_valid_table_name(catalog, schema, table):
                continue
            
            full_name = f"{catalog}.{schema}.{table}"
            
            if full_name not in self.tables:
                self.tables[full_name] = ExtractedTable(
                    catalog=catalog,
                    schema=schema,
                    table=table,
                    full_name=full_name,
                    description=f"Table from requirements: {table}",
                    mentioned_in_queries=1
                )
            else:
                self.tables[full_name].mentioned_in_queries += 1
    
    def _extract_from_sql_queries(self, content: str):
        """Extract tables from SQL queries in code blocks."""
        # Find SQL code blocks
        sql_blocks = re.findall(r'```sql\n(.*?)```', content, re.DOTALL | re.IGNORECASE)
        
        for sql in sql_blocks:
            # Extract table aliases to filter them out
            aliases = self._extract_sql_aliases(sql)
            
            # Extract FROM/JOIN clauses
            from_join_tables = self._extract_from_from_join_clauses(sql, aliases)
            
            for catalog, schema, table in from_join_tables:
                full_name = f"{catalog}.{schema}.{table}"
                self._add_or_update_table(catalog, schema, table, full_name)
    
    def _extract_from_text_mentions(self, content: str):
        """Extract tables from inline backtick mentions."""
        # Look for catalog.schema patterns in text
        pattern = re.compile(r'`([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)`')
        matches = pattern.findall(content)
        
        for match in matches:
            parts = match.split('.')
            if len(parts) == 2 and not self._is_likely_column_reference(match, content):
                schema, table = parts
                full_name = f"{self.default_catalog}.{schema}.{table}"
                self._add_or_update_table(self.default_catalog, schema, table, full_name)
    
    def _add_or_update_table(self, catalog: str, schema: str, table: str, full_name: str):
        """Add table or increment mention count."""
        # Skip invalid table names
        if not self._is_valid_table_name(catalog, schema, table):
            return
            
        if full_name not in self.tables:
            self.tables[full_name] = ExtractedTable(
                catalog=catalog,
                schema=schema,
                table=table,
                full_name=full_name,
                description=f"Table from SQL: {table}",
                mentioned_in_queries=1
            )
        else:
            self.tables[full_name].mentioned_in_queries += 1
    
    def _is_valid_table_name(self, catalog: str, schema: str, table: str) -> bool:
        """
        Validate table name components.
        
        Filters out:
        - Unknown catalogs
        - Column-like names (e.g., event_date, created_at)
        - Too short names (likely aliases)
        - Reserved SQL keywords
        """
        # Skip unknown catalogs
        if catalog.lower() == "unknown":
            return False
        
        # Skip common column names
        common_columns = {
            'event_date', 'created_at', 'updated_at', 'timestamp', 'date',
            'id', 'name', 'value', 'count', 'total', 'sum', 'avg', 'max', 'min'
        }
        if table.lower() in common_columns:
            return False
        
        # Skip if any component is too short (likely an alias)
        if len(catalog) < 2 or len(schema) < 2 or len(table) < 4:
            return False
        
        return True
    
    def _extract_sql_aliases(self, sql: str) -> Set[str]:
        """Extract table aliases from SQL (e.g., FROM table AS alias or FROM table alias)."""
        aliases = set()
        
        # Pattern: FROM/JOIN table_name AS alias or FROM/JOIN table_name alias
        alias_pattern = re.compile(
            r'(?:FROM|JOIN)\s+'
            r'(?:[a-zA-Z_][a-zA-Z0-9_]*\.)*'  # optional schema/catalog
            r'[a-zA-Z_][a-zA-Z0-9_]*\s+'
            r'(?:AS\s+)?'
            r'([a-zA-Z_][a-zA-Z0-9_]*)',
            re.IGNORECASE
        )
        
        for match in alias_pattern.finditer(sql):
            alias = match.group(1)
            # Single letter aliases are very common (e.g., t, m, c)
            if len(alias) <= 3:
                aliases.add(alias.lower())
        
        return aliases
    
    def _extract_from_from_join_clauses(self, sql: str, aliases: Set[str]) -> List[Tuple[str, str, str]]:
        """Extract tables specifically from FROM and JOIN clauses."""
        tables = []
        
        # Pattern for FROM/JOIN with fully qualified names
        from_join_pattern = re.compile(
            r'(?:FROM|JOIN)\s+'
            r'`?([a-zA-Z_][a-zA-Z0-9_]*)`?\.`?([a-zA-Z_][a-zA-Z0-9_]*)`?\.`?([a-zA-Z_][a-zA-Z0-9_]*)`?'
            r'(?:\s+(?:AS\s+)?[a-zA-Z_][a-zA-Z0-9_]*)?',  # optional alias
            re.IGNORECASE
        )
        
        for match in from_join_pattern.finditer(sql):
            catalog, schema, table = match.groups()
            
            # Filter out obvious aliases and too-short names
            if (catalog.lower() not in aliases and 
                schema.lower() not in aliases and
                len(table) > 3):  # Skip very short names (likely aliases)
                tables.append((catalog, schema, table))
        
        return tables
    
    def _is_likely_column_reference(self, text: str, context: str) -> bool:
        """
        Heuristic to determine if a reference is a column vs table.
        
        Args:
            text: The text to check (e.g., "table.column")
            context: Surrounding context
            
        Returns:
            True if likely a column reference
        """
        # Check if preceded by SELECT, WHERE, GROUP BY, ORDER BY
        col_keywords = ['SELECT', 'WHERE', 'GROUP BY', 'ORDER BY', 'HAVING', 'AND', 'OR']
        
        # Find the text in context
        idx = context.find(text)
        if idx > 50:
            before = context[idx-50:idx].upper()
            for keyword in col_keywords:
                if keyword in before:
                    return True
        
        return False


def extract_tables_from_requirements(
    requirements_path: str,
    default_catalog: str = "main",
    verbose: bool = False
) -> List[ExtractedTable]:
    """
    Extract all tables from requirements document using rule-based patterns.
    
    This function provides a comprehensive list of tables mentioned in:
    - **Table:** sections
    - SQL queries (FROM/JOIN clauses)
    - Inline catalog.schema.table references
    
    Args:
        requirements_path: Path to requirements document
        default_catalog: Default catalog when not specified
        verbose: Print extraction progress
        
    Returns:
        List of ExtractedTable objects sorted by mention frequency
        
    Example:
        ```python
        tables = extract_tables_from_requirements("requirements.md")
        print(f"Found {len(tables)} tables")
        for table in tables[:5]:
            print(f"  {table.full_name} (mentioned {table.mentioned_in_queries}x)")
        ```
    """
    extractor = TableExtractor(default_catalog=default_catalog, verbose=verbose)
    return extractor.extract_from_file(requirements_path)


def merge_llm_and_rule_based_tables(
    llm_tables: List[Dict],
    rule_based_tables: List[ExtractedTable],
    max_tables: int = 25,
    prioritize_llm: bool = True
) -> List[Dict]:
    """
    Merge LLM-selected tables with rule-based extracted tables.
    
    Strategy:
    1. Start with LLM-selected tables (they have descriptions and prioritization)
    2. Add high-frequency rule-based tables that LLM missed
    3. Respect max_tables limit (default 25 for Genie)
    
    Args:
        llm_tables: Tables selected by LLM
        rule_based_tables: Tables extracted by rules
        max_tables: Maximum tables to include (Genie limit is 25)
        prioritize_llm: If True, prefer LLM tables; if False, prefer high-frequency rule tables
        
    Returns:
        Merged list of table definitions
    """
    # Create lookup for LLM tables
    llm_table_names = {
        f"{t['catalog_name']}.{t['schema_name']}.{t['table_name']}"
        for t in llm_tables
    }
    
    # Start with LLM tables
    merged_tables = list(llm_tables)
    
    # Add missing tables from rule-based extraction
    for rb_table in rule_based_tables:
        if rb_table.full_name not in llm_table_names:
            if len(merged_tables) >= max_tables:
                break
            
            merged_tables.append(rb_table.to_dict())
            llm_table_names.add(rb_table.full_name)
    
    return merged_tables


if __name__ == "__main__":
    # Test extraction
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python table_extractor.py <requirements_file>")
        sys.exit(1)
    
    tables = extract_tables_from_requirements(sys.argv[1], verbose=True)
    
    print(f"\n✓ Extracted {len(tables)} tables")
    print("\nTop 10 tables by mention frequency:")
    for i, table in enumerate(tables[:10], 1):
        print(f"{i:2d}. {table.full_name:60s} ({table.mentioned_in_queries:2d}x)")
