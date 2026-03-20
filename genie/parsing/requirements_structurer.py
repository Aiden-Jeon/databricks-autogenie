"""
Requirements Structurer Module
Transforms extracted data from PDFs and markdown into unified intermediate structure.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class QuestionCategory(str, Enum):
    """Question categories"""
    KPI = "KPI"
    SOCIAL = "Social"
    SENTIMENT = "Sentiment"
    TREND = "Trend"
    COMPARISON = "Comparison"
    REGIONAL = "Regional"
    OTHER = "Other"


class Domain(str, Enum):
    """Document domains"""
    SOCIAL_ANALYTICS = "social_analytics"
    KPI_ANALYTICS = "kpi_analytics"
    COMBINED = "combined"
    UNKNOWN = "unknown"


@dataclass
class ColumnInfo:
    """Column information"""
    name: str
    description: Optional[str] = None
    data_type: Optional[str] = None
    # Enhanced fields for Phase 1
    is_required: bool = True  # False if marked "선택적" or "optional"
    usage_type: Optional[str] = None  # "filtering" | "display" | "aggregation" | "join_key"
    transformation_rule: Optional[str] = None  # e.g., "FROM_UNIXTIME(timestamp_created)"


@dataclass
class TableInfo:
    """Table information"""
    catalog: str
    schema: str
    table: str
    description: str
    columns: List[ColumnInfo] = field(default_factory=list)
    related_kpi: Optional[str] = None
    sample_query: Optional[str] = None
    # Enhanced field for Phase 1
    table_remarks: List[str] = field(default_factory=list)  # Special notes
    
    @property
    def full_name(self) -> str:
        """Get full table name"""
        return f"{self.catalog}.{self.schema}.{self.table}"
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TableInfo':
        """Create from dictionary"""
        full_name = data.get("full_name", "")
        parts = full_name.split(".")

        if len(parts) == 3:
            catalog, schema, table = parts
        elif len(parts) == 2:
            catalog = "unknown"
            schema, table = parts
        else:
            catalog = schema = "unknown"
            table = full_name

        # Convert columns if present
        columns = []
        if "key_columns" in data:
            # Check if it's a list of strings or dicts
            key_columns = data["key_columns"]
            if key_columns and isinstance(key_columns[0], dict):
                # Enhanced format with metadata
                columns = [
                    ColumnInfo(
                        name=col.get("name", ""),
                        description=col.get("description"),
                        data_type=col.get("data_type"),
                        is_required=col.get("is_required", True),
                        usage_type=col.get("usage_type"),
                        transformation_rule=col.get("transformation_rule")
                    )
                    for col in key_columns
                ]
            else:
                # Legacy format (list of strings)
                columns = [ColumnInfo(name=col) for col in key_columns]

        return cls(
            catalog=catalog,
            schema=schema,
            table=table,
            description=data.get("description", ""),
            columns=columns,
            related_kpi=data.get("related_kpi"),
            sample_query=data.get("sample_query"),
            table_remarks=data.get("table_remarks", [])
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "full_name": self.full_name,
            "catalog": self.catalog,
            "schema": self.schema,
            "table": self.table,
            "description": self.description,
            "columns": [col.name for col in self.columns],
            "related_kpi": self.related_kpi,
            "sample_query": self.sample_query
        }


@dataclass
class QueryResultExample:
    """Sample query result for validation"""
    query_id: str
    sample_rows: List[Dict[str, str]] = field(default_factory=list)  # List of row dicts
    column_names: List[str] = field(default_factory=list)
    notes: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> 'QueryResultExample':
        return cls(
            query_id=data.get("query_id", ""),
            sample_rows=data.get("sample_rows", []),
            column_names=data.get("column_names", []),
            notes=data.get("notes")
        )

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FormulaDefinition:
    """Reusable metric formula definition"""
    name: str  # e.g., "ARPU", "DAU", "Retention Rate"
    formula: str  # SQL expression
    description: str
    required_columns: List[str] = field(default_factory=list)
    required_tables: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    example_usage: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> 'FormulaDefinition':
        return cls(
            name=data.get("name", ""),
            formula=data.get("formula", ""),
            description=data.get("description", ""),
            required_columns=data.get("required_columns", []),
            required_tables=data.get("required_tables", []),
            notes=data.get("notes"),
            example_usage=data.get("example_usage")
        )

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PlatformNote:
    """Platform-specific logic and restrictions"""
    platform: str  # "PUBG", "Steam", "Discord", "All"
    note_type: str  # "restriction", "transformation", "limitation", "requirement"
    description: str
    affected_tables: List[str] = field(default_factory=list)
    affected_queries: List[str] = field(default_factory=list)
    example_code: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict) -> 'PlatformNote':
        return cls(
            platform=data.get("platform", "All"),
            note_type=data.get("note_type", "requirement"),
            description=data.get("description", ""),
            affected_tables=data.get("affected_tables", []),
            affected_queries=data.get("affected_queries", []),
            example_code=data.get("example_code")
        )

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SQLQuery:
    """SQL query information"""
    question_id: str
    query: str
    description: str
    tables_used: List[str] = field(default_factory=list)
    # Enhanced fields for Phase 1
    aggregation_patterns: List[str] = field(default_factory=list)  # ["COALESCE", "CTE", "UNION_ALL", "window_function"]
    filtering_rules: List[str] = field(default_factory=list)  # Extracted WHERE conditions
    join_specs: List[str] = field(default_factory=list)  # Explicit JOIN syntax with conditions
    # Phase 2 fields
    intent: Optional[str] = None  # "monitoring", "analysis", "reporting", "alert"
    complexity: Optional[str] = None  # "low", "medium", "high"
    optimization_notes: List[str] = field(default_factory=list)
    result_example: Optional['QueryResultExample'] = None

    @classmethod
    def from_dict(cls, data: Dict) -> 'SQLQuery':
        """Create from dictionary"""
        result_example = None
        if "result_example" in data and data["result_example"]:
            result_example = QueryResultExample.from_dict(data["result_example"])

        return cls(
            question_id=data.get("question_id", ""),
            query=data.get("query", ""),
            description=data.get("description", ""),
            tables_used=data.get("tables_used", []),
            aggregation_patterns=data.get("aggregation_patterns", []),
            filtering_rules=data.get("filtering_rules", []),
            join_specs=data.get("join_specs", []),
            intent=data.get("intent"),
            complexity=data.get("complexity"),
            optimization_notes=data.get("optimization_notes", []),
            result_example=result_example
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class JoinSpec:
    """Explicit join relationship"""
    left_table: str
    right_table: str
    join_type: str  # "INNER" | "LEFT" | "RIGHT" | "FULL"
    join_condition: str  # e.g., "m.message_id = r.message_id"
    is_optional: bool = False  # True if marked "선택적"

    @classmethod
    def from_dict(cls, data: Dict) -> 'JoinSpec':
        return cls(
            left_table=data.get("left_table", ""),
            right_table=data.get("right_table", ""),
            join_type=data.get("join_type", "LEFT"),
            join_condition=data.get("join_condition", ""),
            is_optional=data.get("is_optional", False)
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class Question:
    """Question/requirement information"""
    id: str
    text: str
    category: str
    tables_needed: List[str] = field(default_factory=list)
    columns_needed: List[str] = field(default_factory=list)
    join_conditions: List[str] = field(default_factory=list)
    filtering_conditions: List[str] = field(default_factory=list)
    example_query: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Question':
        """Create from dictionary"""
        return cls(
            id=data.get("id", ""),
            text=data.get("text", ""),
            category=data.get("category", "Other"),
            tables_needed=data.get("tables_needed", []),
            columns_needed=data.get("columns_needed", []),
            join_conditions=data.get("join_conditions", []),
            filtering_conditions=data.get("filtering_conditions", []),
            example_query=data.get("example_query")
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class RequirementSection:
    """Section of requirements"""
    title: str
    questions: List[Question] = field(default_factory=list)
    tables: List[TableInfo] = field(default_factory=list)
    sample_queries: List[SQLQuery] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "title": self.title,
            "questions": [q.to_dict() for q in self.questions],
            "tables": [t.to_dict() for t in self.tables],
            "sample_queries": [q.to_dict() for q in self.sample_queries]
        }


@dataclass
class RequirementsDocument:
    """Complete requirements document"""
    metadata: Dict
    sections: List[RequirementSection] = field(default_factory=list)
    all_questions: List[Question] = field(default_factory=list)
    all_tables: List[TableInfo] = field(default_factory=list)
    all_queries: List[SQLQuery] = field(default_factory=list)
    # Phase 2 fields
    all_formulas: List[FormulaDefinition] = field(default_factory=list)
    platform_notes: List[PlatformNote] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "metadata": self.metadata,
            "sections": [s.to_dict() for s in self.sections],
            "all_questions": [q.to_dict() for q in self.all_questions],
            "all_tables": [t.to_dict() for t in self.all_tables],
            "all_queries": [q.to_dict() for q in self.all_queries]
        }


class RequirementsStructurer:
    """
    Transforms extracted data from PDFs and markdown into unified structure.
    """
    
    def __init__(self):
        """Initialize structurer"""
        pass
    
    def structure_data(self, pdf_data: Dict, md_data: Dict) -> RequirementsDocument:
        """
        Combine PDF and markdown data into unified structure.
        
        Args:
            pdf_data: Data extracted from PDF files
            md_data: Data extracted from markdown files
            
        Returns:
            RequirementsDocument with combined data
        """
        logger.info("Structuring requirements data")
        
        # Combine questions
        all_questions = self._combine_questions(
            pdf_data.get("questions", []),
            md_data.get("questions", [])
        )
        
        # Combine tables
        all_tables = self._combine_tables(
            pdf_data.get("tables", []),
            md_data.get("tables", [])
        )
        
        # Combine queries
        all_queries = self._combine_queries(
            pdf_data.get("sql_queries", []),
            md_data.get("sql_queries", [])
        )
        
        # Create sections by category
        sections = self._create_sections(all_questions, all_tables, all_queries)
        
        # Combine metadata
        metadata = self._combine_metadata(
            pdf_data.get("metadata", {}),
            md_data.get("metadata", {})
        )
        
        logger.info(f"Structured: {len(all_questions)} questions, {len(all_tables)} tables, "
                   f"{len(all_queries)} queries, {len(sections)} sections")
        
        return RequirementsDocument(
            metadata=metadata,
            sections=sections,
            all_questions=all_questions,
            all_tables=all_tables,
            all_queries=all_queries
        )
    
    def _combine_questions(self, pdf_questions: List[Dict], md_questions: List[Dict]) -> List[Question]:
        """Combine and deduplicate questions from PDF and markdown"""
        questions = []
        seen_texts = set()
        
        # Add markdown questions first (more reliable)
        for q_dict in md_questions:
            q = Question.from_dict(q_dict)
            if q.text not in seen_texts:
                questions.append(q)
                seen_texts.add(q.text)
        
        # Add PDF questions if not duplicates
        for q_dict in pdf_questions:
            q = Question.from_dict(q_dict)
            if q.text not in seen_texts:
                questions.append(q)
                seen_texts.add(q.text)
        
        # Sort by ID
        questions.sort(key=lambda x: self._extract_question_number(x.id))
        
        return questions
    
    def _combine_tables(self, pdf_tables: List[Dict], md_tables: List[Dict]) -> List[TableInfo]:
        """Combine and deduplicate tables from PDF and markdown with smart merging"""
        tables_dict = {}

        # Add markdown tables first
        for t_dict in md_tables:
            t = TableInfo.from_dict(t_dict)
            tables_dict[t.full_name] = t

        # Add PDF tables, merging with existing
        for t_dict in pdf_tables:
            t = TableInfo.from_dict(t_dict)
            if t.full_name in tables_dict:
                # Smart merge: combine information instead of replacing
                existing = tables_dict[t.full_name]

                # Merge descriptions (combine both if different)
                if t.description and t.description != existing.description:
                    if existing.description:
                        # Combine descriptions with separator
                        existing.description = f"{existing.description}; {t.description}"
                    else:
                        existing.description = t.description

                # Merge related KPI
                if not existing.related_kpi and t.related_kpi:
                    existing.related_kpi = t.related_kpi

                # Merge columns (deduplicate by column name)
                if t.columns:
                    existing_col_names = {col.name for col in existing.columns}
                    for col in t.columns:
                        if col.name not in existing_col_names:
                            existing.columns.append(col)
                            existing_col_names.add(col.name)

                # Merge table remarks
                if t.table_remarks:
                    if not existing.table_remarks:
                        existing.table_remarks = t.table_remarks[:]
                    else:
                        # Combine unique remarks
                        existing_remarks = set(existing.table_remarks)
                        for remark in t.table_remarks:
                            if remark not in existing_remarks:
                                existing.table_remarks.append(remark)
            else:
                tables_dict[t.full_name] = t

        logger.info(f"Combined tables: {len(md_tables)} markdown + {len(pdf_tables)} PDF -> {len(tables_dict)} unique")
        return list(tables_dict.values())
    
    def _combine_queries(self, pdf_queries: List[Dict], md_queries: List[Dict]) -> List[SQLQuery]:
        """Combine and deduplicate queries from PDF and markdown"""
        queries = []
        seen_queries = set()
        
        # Add markdown queries first (more reliable)
        for q_dict in md_queries:
            q = SQLQuery.from_dict(q_dict)
            # Use query text as dedup key
            query_key = q.query.strip()[:100]  # First 100 chars
            if query_key not in seen_queries:
                queries.append(q)
                seen_queries.add(query_key)
        
        # Add PDF queries if not duplicates
        for q_dict in pdf_queries:
            q = SQLQuery.from_dict(q_dict)
            query_key = q.query.strip()[:100]
            if query_key not in seen_queries:
                queries.append(q)
                seen_queries.add(query_key)
        
        return queries
    
    def _create_sections(self, questions: List[Question], tables: List[TableInfo], 
                        queries: List[SQLQuery]) -> List[RequirementSection]:
        """Organize questions into sections by category"""
        sections_dict = {}
        
        # Group questions by category
        for question in questions:
            category = question.category
            if category not in sections_dict:
                sections_dict[category] = RequirementSection(title=category)
            
            sections_dict[category].questions.append(question)
        
        # Add relevant tables and queries to each section
        for section in sections_dict.values():
            # Collect tables used by questions in this section
            tables_needed = set()
            for q in section.questions:
                tables_needed.update(q.tables_needed)
            
            # Add matching tables
            for table in tables:
                if table.full_name in tables_needed:
                    section.tables.append(table)
            
            # Add matching queries
            question_ids = {q.id for q in section.questions}
            for query in queries:
                if query.question_id in question_ids:
                    section.sample_queries.append(query)
        
        return list(sections_dict.values())
    
    def _combine_metadata(self, pdf_metadata: Dict, md_metadata: Dict) -> Dict:
        """Combine metadata from PDF and markdown sources"""
        metadata = {
            "title": "Combined Requirements",
            "source_files": [],
            "domains": set(),
            "num_questions": 0,
            "num_tables": 0,
            "num_queries": 0
        }
        
        # Add source files
        if "source_file" in pdf_metadata:
            metadata["source_files"].append(pdf_metadata["source_file"])
        if "source_file" in md_metadata:
            metadata["source_files"].append(md_metadata["source_file"])
        if "source_directory" in md_metadata:
            metadata["source_files"].append(md_metadata["source_directory"])
        
        # Add domains
        if "domain" in pdf_metadata:
            metadata["domains"].add(pdf_metadata["domain"])
        if "domain" in md_metadata:
            metadata["domains"].add(md_metadata["domain"])
        
        # Convert domains set to list
        metadata["domains"] = list(metadata["domains"])
        
        # Determine primary domain
        if "kpi_analytics" in metadata["domains"] and "social_analytics" in metadata["domains"]:
            metadata["primary_domain"] = "combined"
        elif metadata["domains"]:
            metadata["primary_domain"] = metadata["domains"][0]
        else:
            metadata["primary_domain"] = "unknown"
        
        return metadata
    
    def _extract_question_number(self, question_id: str) -> int:
        """Extract numeric part from question ID for sorting"""
        import re
        match = re.search(r'\d+', question_id)
        return int(match.group()) if match else 9999
    
    def update_metadata(self, doc: RequirementsDocument) -> RequirementsDocument:
        """Update metadata with counts"""
        doc.metadata["num_questions"] = len(doc.all_questions)
        doc.metadata["num_tables"] = len(doc.all_tables)
        doc.metadata["num_queries"] = len(doc.all_queries)
        doc.metadata["num_sections"] = len(doc.sections)
        
        return doc


def structure_requirements(pdf_data: Dict, md_data: Dict) -> RequirementsDocument:
    """
    Convenience function to structure requirements.
    
    Args:
        pdf_data: Data extracted from PDF files
        md_data: Data extracted from markdown files
        
    Returns:
        RequirementsDocument with structured data
    """
    structurer = RequirementsStructurer()
    doc = structurer.structure_data(pdf_data, md_data)
    return structurer.update_metadata(doc)
