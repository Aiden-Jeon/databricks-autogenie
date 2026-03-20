"""
Markdown Parser Module
Extracts structured information from markdown files using regex patterns.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MarkdownQuestion:
    """Question extracted from markdown"""
    id: str
    text: str
    category: str
    tables_needed: List[str] = field(default_factory=list)
    columns_needed: List[str] = field(default_factory=list)
    join_conditions: List[str] = field(default_factory=list)
    filtering_conditions: List[str] = field(default_factory=list)
    example_query: Optional[str] = None


@dataclass
class MarkdownTable:
    """Table information extracted from markdown"""
    full_name: str
    description: str
    key_columns: List[str] = field(default_factory=list)
    related_kpi: Optional[str] = None


class MarkdownParser:
    """
    Parser for extracting structured information from markdown files.
    Uses regex patterns for deterministic extraction.
    """
    
    # Regex patterns
    QUESTION_PATTERN = r"###\s+(\d+)\.\s+(.+?)(?=\n|$)"
    SQL_QUERY_PATTERN = r"```sql\n(.*?)\n```"
    TABLE_LIST_PATTERN = r"\*\*필요한 테이블:\*\*\s*(.*?)(?=\n\n|\*\*|$)"
    COLUMN_LIST_PATTERN = r"\*\*필요한 컬럼:\*\*\s*(.*?)(?=\n\n|\*\*|$)"
    JOIN_PATTERN = r"```sql\s*(.*?LEFT JOIN.*?)\s*```"
    FILTER_PATTERN = r"\*\*필터링 조건:\*\*\s*(.*?)(?=\n\n|\*\*|$)"
    TABLE_NAME_PATTERN = r"`([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)`"
    RELATED_KPI_PATTERN = r"\*\*Related KPI:\*\*\s*(.+?)(?=\n|$)"
    SAMPLE_QUERY_SECTION_PATTERN = r"\*\*Sample Query:\*\*\s*```sql\n(.*?)\n```"
    # Enhanced patterns for Phase 1
    OPTIONAL_MARKER_PATTERN = r"\(선택적\)|\(optional\)"
    REMARK_PATTERN = r"\*\*(?:Remark|비고|참고):\*\*\s*(.*?)(?=\n\n|\*\*|$)"
    COLUMN_USAGE_PATTERN = r"`([^`]+)`[^`]*?(?:for|용도:|is)\s*([^\n,]+)"
    AGGREGATION_PATTERN = r"(COALESCE|try_divide|UNION ALL|WITH\s+\w+|RANK\(\)|ROW_NUMBER\(\))"
    
    def __init__(self):
        """Initialize markdown parser"""
        pass

    def _extract_column_metadata(self, text: str) -> Dict[str, Dict]:
        """Extract column-level metadata from text"""
        columns = {}

        # Find optional markers
        for match in re.finditer(self.OPTIONAL_MARKER_PATTERN, text):
            # Extract column name before marker
            context = text[max(0, match.start()-50):match.start()]
            col_match = re.search(r"`([^`]+)`", context)
            if col_match:
                col_name = col_match.group(1)
                columns[col_name] = {"is_required": False}

        # Find usage types
        for match in re.finditer(self.COLUMN_USAGE_PATTERN, text):
            col_name = match.group(1)
            usage = match.group(2).strip()
            if col_name not in columns:
                columns[col_name] = {}
            columns[col_name]["usage_type"] = usage

        return columns

    def _extract_remarks(self, text: str) -> List[str]:
        """Extract special remarks from text"""
        remarks = []
        # Match all variations of remark markers
        for match in re.finditer(self.REMARK_PATTERN, text, re.DOTALL):
            remark = match.group(1).strip()
            # Clean up newlines within the remark
            remark = ' '.join(remark.split())
            if remark:
                remarks.append(remark)
        return remarks

    def _extract_aggregation_patterns(self, query: str) -> List[str]:
        """Extract aggregation patterns from SQL query"""
        patterns = set()
        for match in re.finditer(self.AGGREGATION_PATTERN, query, re.IGNORECASE):
            pattern = match.group(1).upper()
            if "WITH" in pattern:
                patterns.add("CTE")
            elif "UNION ALL" in pattern:
                patterns.add("UNION_ALL")
            else:
                patterns.add(pattern)
        return list(patterns)

    def _extract_filtering_rules(self, query: str) -> List[str]:
        """Extract filtering rules from WHERE clause"""
        filtering_rules = []
        # Extract WHERE clause
        where_pattern = r"WHERE\s+(.*?)(?=GROUP BY|ORDER BY|LIMIT|$)"
        where_match = re.search(where_pattern, query, re.DOTALL | re.IGNORECASE)
        if where_match:
            where_clause = where_match.group(1).strip()
            # Split by AND/OR and clean
            conditions = re.split(r'\s+AND\s+|\s+OR\s+', where_clause, flags=re.IGNORECASE)
            filtering_rules = [cond.strip() for cond in conditions if cond.strip()]
        return filtering_rules

    def _extract_join_specs_from_query(self, query: str) -> List[str]:
        """Extract explicit JOIN specifications from SQL query"""
        join_specs = []
        # Simplified pattern: match JOIN ... ON ... until next clause or end
        # Matches: [LEFT|RIGHT|INNER|FULL] [OUTER] JOIN table [AS alias] ON condition
        join_pattern = r'((?:LEFT|RIGHT|INNER|FULL)?\s*(?:OUTER\s+)?JOIN\s+\S+(?:\s+(?:AS\s+)?\S+)?\s+ON\s+[\w\s.=<>!]+?)(?=\s+(?:LEFT|RIGHT|INNER|FULL|WHERE|GROUP|ORDER|UNION|$))'
        join_matches = re.finditer(join_pattern, query, re.IGNORECASE)
        for match in join_matches:
            join_spec = ' '.join(match.group(1).split())  # Normalize whitespace
            join_specs.append(join_spec.strip())
        return join_specs
    
    def parse_file(self, md_path: str) -> Dict:
        """
        Parse a markdown file and extract structured information.
        
        Args:
            md_path: Path to markdown file
            
        Returns:
            Dictionary with extracted questions, tables, and queries
        """
        logger.info(f"Parsing markdown file: {md_path}")
        
        try:
            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading markdown file: {e}")
            raise
        
        # Determine domain from file name
        file_name = Path(md_path).name.lower()
        if 'kpi' in file_name:
            domain = 'kpi_analytics'
        elif 'content' in file_name or 'social' in file_name:
            domain = 'social_analytics'
        else:
            domain = 'unknown'
        
        # Extract information
        questions = self._extract_questions(content)
        tables = self._extract_tables(content)
        sql_queries = self._extract_sql_queries(content)
        
        logger.info(f"Extracted {len(questions)} questions, {len(tables)} tables, {len(sql_queries)} queries")
        
        return {
            "questions": questions,
            "tables": tables,
            "sql_queries": sql_queries,
            "metadata": {
                "document_title": Path(md_path).stem,
                "domain": domain,
                "source_file": md_path
            }
        }
    
    def _extract_questions(self, content: str) -> List[Dict]:
        """Extract questions from markdown content"""
        questions = []
        
        # Find all question headers
        question_matches = re.finditer(self.QUESTION_PATTERN, content, re.MULTILINE)
        
        for match in question_matches:
            question_id = match.group(1)
            question_text = match.group(2).strip()
            
            # Find the section for this question
            section_start = match.start()
            next_question = re.search(r"\n###\s+\d+\.", content[section_start + 1:])
            section_end = section_start + next_question.start() if next_question else len(content)
            section_content = content[section_start:section_end]
            
            # Extract details from section
            tables_needed = self._extract_tables_from_section(section_content)
            columns_needed = self._extract_columns_from_section(section_content)
            join_conditions = self._extract_joins_from_section(section_content)
            filtering_conditions = self._extract_filters_from_section(section_content)
            example_query = self._extract_query_from_section(section_content)
            category = self._categorize_question(question_text, section_content)
            
            question = {
                "id": f"Q{question_id}",
                "text": question_text,
                "category": category,
                "tables_needed": tables_needed,
                "columns_needed": columns_needed,
                "join_conditions": join_conditions,
                "filtering_conditions": filtering_conditions,
                "example_query": example_query
            }
            
            questions.append(question)
        
        return questions
    
    def _extract_tables_from_section(self, section: str) -> List[str]:
        """Extract table names from a question section"""
        tables = []
        
        # Look for table list section
        table_list_match = re.search(self.TABLE_LIST_PATTERN, section, re.DOTALL)
        if table_list_match:
            table_text = table_list_match.group(1)
            # Extract table names with pattern catalog.schema.table
            table_matches = re.findall(self.TABLE_NAME_PATTERN, table_text)
            tables.extend(table_matches)
        
        # Also extract from SQL queries
        query_match = re.search(self.SQL_QUERY_PATTERN, section, re.DOTALL | re.IGNORECASE)
        if query_match:
            query = query_match.group(1)
            # Extract FROM and JOIN clauses
            from_pattern = r"FROM\s+([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)"
            join_pattern = r"JOIN\s+([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)"
            
            tables.extend(re.findall(from_pattern, query, re.IGNORECASE))
            tables.extend(re.findall(join_pattern, query, re.IGNORECASE))
        
        return list(set(tables))  # Remove duplicates
    
    def _extract_columns_from_section(self, section: str) -> List[str]:
        """Extract column names from a question section"""
        columns = []
        
        # Look for column list section
        column_list_match = re.search(self.COLUMN_LIST_PATTERN, section, re.DOTALL)
        if column_list_match:
            column_text = column_list_match.group(1)
            # Extract column names (simple pattern)
            column_pattern = r"`([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)`"
            columns = re.findall(column_pattern, column_text)
        
        return columns
    
    def _extract_joins_from_section(self, section: str) -> List[str]:
        """Extract JOIN conditions from a question section"""
        joins = []
        
        # Look for join relationship section
        join_section_pattern = r"\*\*조인 관계:\*\*\s*```sql\s*(.*?)\s*```"
        join_match = re.search(join_section_pattern, section, re.DOTALL)
        
        if join_match:
            join_text = join_match.group(1)
            # Split by newlines and clean
            join_lines = [line.strip() for line in join_text.split('\n') if line.strip() and 'JOIN' in line.upper()]
            joins.extend(join_lines)
        
        return joins
    
    def _extract_filters_from_section(self, section: str) -> List[str]:
        """Extract filtering conditions from a question section"""
        filters = []
        
        # Look for filtering section
        filter_match = re.search(self.FILTER_PATTERN, section, re.DOTALL)
        if filter_match:
            filter_text = filter_match.group(1)
            # Split by newlines and clean
            filter_lines = [line.strip('- ').strip() for line in filter_text.split('\n') if line.strip().startswith('-')]
            filters.extend(filter_lines)
        
        return filters
    
    def _extract_query_from_section(self, section: str) -> Optional[str]:
        """Extract SQL query from a question section"""
        # Look for example query
        query_match = re.search(self.SQL_QUERY_PATTERN, section, re.DOTALL | re.IGNORECASE)
        if query_match:
            return query_match.group(1).strip()
        return None
    
    def _categorize_question(self, question_text: str, section_content: str) -> str:
        """Categorize a question based on its text and content"""
        text_lower = question_text.lower()
        
        # KPI-related keywords
        if any(kw in text_lower for kw in ['dau', 'arpu', 'kpi', '리텐션', 'retention', '잔존', 'paying']):
            return 'KPI'
        
        # Social analytics keywords
        if any(kw in text_lower for kw in ['디스코드', 'discord', '스팀', 'steam', '리뷰', 'review', '리액션', 'reaction']):
            return 'Social'
        
        # Sentiment keywords
        if any(kw in text_lower for kw in ['긍정', '부정', 'positive', 'negative', 'sentiment', '감성']):
            return 'Sentiment'
        
        # Trend keywords
        if any(kw in text_lower for kw in ['트렌드', 'trend', '변화', 'change', '급증', 'spike']):
            return 'Trend'
        
        # Comparison keywords
        if any(kw in text_lower for kw in ['비교', 'compare', '차이', 'difference', '전후', 'before/after']):
            return 'Comparison'
        
        # Regional keywords
        if any(kw in text_lower for kw in ['지역', 'region', '국가', 'country']):
            return 'Regional'
        
        return 'Other'
    
    def _extract_tables(self, content: str) -> List[Dict]:
        """Extract table information from markdown content with flexible pattern matching"""
        tables = []
        tables_by_name = {}  # Track unique tables by full_name

        # Pattern 1: Standard format with level 2 heading and **Table:**
        # Example: ## Daily KPI Summary\n\n**Table:** `catalog.schema.table`
        pattern1 = r"##\s+(.+?)\n\n\*\*Table:\*\*\s+`([^`]+)`"

        # Pattern 2: Level 3 heading with **Table:**
        # Example: ### Table Name\n**Table:** `catalog.schema.table`
        pattern2 = r"###\s+(.+?)\n+\*\*Table:\*\*\s+`([^`]+)`"

        # Pattern 3: Korean format with level 2/3 heading
        # Example: ## Table Name\n테이블: catalog.schema.table
        pattern3 = r"#{2,3}\s+(.+?)\n+(?:테이블|Table):\s*([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)"

        # Pattern 4: Inline table reference without heading
        # Example: **Table:** `catalog.schema.table`
        pattern4 = r"\*\*Table:\*\*\s+`([^`]+)`"

        # Pattern 5: Plain text table reference
        # Example: Table: catalog.schema.table or 테이블: catalog.schema.table
        pattern5 = r"(?:Table|테이블|table name):\s*([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)"

        # Try all patterns
        all_patterns = [
            (pattern1, True),   # Has section title
            (pattern2, True),   # Has section title
            (pattern3, True),   # Has section title
            (pattern4, False),  # No section title
            (pattern5, False),  # No section title
        ]

        for pattern, has_title in all_patterns:
            matches = re.finditer(pattern, content, re.MULTILINE)

            for match in matches:
                if has_title:
                    section_title = match.group(1).strip()
                    table_name = match.group(2).strip()
                else:
                    section_title = None
                    table_name = match.group(1).strip()

                # Skip if already found
                if table_name in tables_by_name:
                    continue

                # Find the section content
                section_start = match.start()
                next_section = re.search(r"\n#{2,3}\s+", content[section_start + 1:])
                section_end = section_start + next_section.start() if next_section else len(content)
                section_content = content[section_start:section_end]

                # Extract related KPI
                related_kpi_match = re.search(self.RELATED_KPI_PATTERN, section_content)
                related_kpi = related_kpi_match.group(1).strip() if related_kpi_match else None

                # Extract key columns from sample query
                sample_query_match = re.search(self.SAMPLE_QUERY_SECTION_PATTERN, section_content, re.DOTALL)
                key_columns = []
                if sample_query_match:
                    query = sample_query_match.group(1)
                    # Extract SELECT columns (simplified)
                    select_pattern = r"SELECT\s+(.*?)\s+FROM"
                    select_match = re.search(select_pattern, query, re.DOTALL | re.IGNORECASE)
                    if select_match:
                        select_clause = select_match.group(1)
                        # Extract column names (simplified)
                        col_pattern = r"([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)|([a-zA-Z0-9_]+)\s+as"
                        key_columns = [c[0] or c[1] for c in re.findall(col_pattern, select_clause, re.IGNORECASE)]

                table = {
                    "full_name": table_name,
                    "description": section_title or f"Table {table_name}",
                    "key_columns": key_columns,  # No limit - extract all columns
                    "related_kpi": related_kpi
                }

                tables_by_name[table_name] = table

        # Convert dict to list
        tables = list(tables_by_name.values())

        logger.info(f"Extracted {len(tables)} unique tables from markdown")
        return tables
    
    def _extract_sql_queries(self, content: str) -> List[Dict]:
        """Extract SQL queries from markdown content with enhanced metadata"""
        queries = []

        # Find all SQL queries
        query_matches = re.finditer(self.SQL_QUERY_PATTERN, content, re.DOTALL | re.IGNORECASE)

        for idx, match in enumerate(query_matches, start=1):
            query = match.group(1).strip()

            # Try to find associated question (look backwards for ###)
            section_before = content[:match.start()]
            question_match = re.findall(self.QUESTION_PATTERN, section_before, re.MULTILINE)

            if question_match:
                # Get the last question before this query
                last_question = question_match[-1]
                question_id = f"Q{last_question[0]}"
                description = f"Query for: {last_question[1]}"
            else:
                question_id = f"Q_UNKNOWN_{idx}"
                description = "SQL query without associated question"

            # Enhanced extraction
            aggregation_patterns = self._extract_aggregation_patterns(query)
            filtering_rules = self._extract_filtering_rules(query)
            join_specs = self._extract_join_specs_from_query(query)

            queries.append({
                "question_id": question_id,
                "query": query,
                "description": description,
                "aggregation_patterns": aggregation_patterns,
                "filtering_rules": filtering_rules,
                "join_specs": join_specs
            })

        return queries
    
    def parse_directory(self, directory: str) -> Dict:
        """
        Parse all markdown files in a directory.
        
        Args:
            directory: Path to directory containing markdown files
            
        Returns:
            Combined dictionary with all extracted information
        """
        logger.info(f"Parsing markdown files in directory: {directory}")
        
        md_files = list(Path(directory).glob("*.md"))
        logger.info(f"Found {len(md_files)} markdown files")
        
        all_questions = []
        all_tables = []
        all_queries = []
        
        for md_file in md_files:
            try:
                result = self.parse_file(str(md_file))
                all_questions.extend(result["questions"])
                all_tables.extend(result["tables"])
                all_queries.extend(result["sql_queries"])
            except Exception as e:
                logger.error(f"Error parsing {md_file}: {e}")
        
        # Remove duplicates
        unique_tables = self._deduplicate_tables(all_tables)
        
        return {
            "questions": all_questions,
            "tables": unique_tables,
            "sql_queries": all_queries,
            "metadata": {
                "source_directory": directory,
                "num_files_processed": len(md_files)
            }
        }
    
    def _deduplicate_tables(self, tables: List[Dict]) -> List[Dict]:
        """Remove duplicate tables based on full_name"""
        seen = set()
        unique = []
        
        for table in tables:
            if table["full_name"] not in seen:
                seen.add(table["full_name"])
                unique.append(table)
        
        return unique


def parse_markdown_file(md_path: str) -> Dict:
    """
    Convenience function to parse a single markdown file.
    
    Args:
        md_path: Path to markdown file
        
    Returns:
        Dictionary with extracted information
    """
    parser = MarkdownParser()
    return parser.parse_file(md_path)


def parse_markdown_directory(directory: str) -> Dict:
    """
    Convenience function to parse all markdown files in a directory.
    
    Args:
        directory: Path to directory
        
    Returns:
        Combined dictionary with all extracted information
    """
    parser = MarkdownParser()
    return parser.parse_directory(directory)
