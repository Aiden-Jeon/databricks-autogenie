"""
Markdown Generator Module
Generates final markdown documentation following demo_requirements.md structure.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

from genie.parsing.requirements_structurer import RequirementsDocument, Question, TableInfo, SQLQuery

logger = logging.getLogger(__name__)


class MarkdownGenerator:
    """
    Generates markdown documentation from RequirementsDocument.
    Follows the structure of demo_requirements.md.
    """
    
    def __init__(self):
        """Initialize markdown generator"""
        pass
    
    def generate(self, doc: RequirementsDocument, output_path: str) -> str:
        """
        Generate markdown documentation.
        
        Args:
            doc: RequirementsDocument to convert
            output_path: Path where output will be saved
            
        Returns:
            Generated markdown content as string
        """
        logger.info(f"Generating markdown documentation")
        
        sections = []
        
        # 1. Title and Overview
        sections.append(self._generate_header(doc))
        sections.append(self._generate_overview(doc))
        
        # 2. FAQ Questions List
        sections.append(self._generate_faq_section(doc))
        
        # 3. Table Sections with Sample Queries
        sections.append(self._generate_table_sections(doc))

        # 3a. Enhanced: Column Details (Phase 1)
        column_details = self._generate_column_details_section(doc)
        if column_details.strip():
            sections.append(column_details)

        # 3b. Enhanced: Join Specifications (Phase 1)
        join_specs = self._generate_join_specs_section(doc)
        if join_specs.strip():
            sections.append(join_specs)

        # 3c. Enhanced: Aggregation Patterns (Phase 1)
        agg_patterns = self._generate_aggregation_patterns_section(doc)
        if agg_patterns.strip():
            sections.append(agg_patterns)

        # 3d. Phase 2: Formula Library
        formula_lib = self._generate_formula_library_section(doc)
        if formula_lib.strip():
            sections.append(formula_lib)

        # 3e. Phase 2: Platform-Specific Logic
        platform_notes = self._generate_platform_notes_section(doc)
        if platform_notes.strip():
            sections.append(platform_notes)

        # 3f. Phase 2: Query Analysis
        query_analysis = self._generate_query_analysis_section(doc)
        if query_analysis.strip():
            sections.append(query_analysis)

        # 3g. Phase 2: Result Examples
        result_examples = self._generate_result_examples_section(doc)
        if result_examples.strip():
            sections.append(result_examples)

        # 4. Table Relationships (ERD)
        sections.append(self._generate_erd_section(doc))

        # 5. Common Filters & Dimensions
        sections.append(self._generate_filters_section(doc))

        # 6. Table Mapping for Business Questions
        sections.append(self._generate_table_mapping(doc))

        # 7. Meta Tables
        sections.append(self._generate_meta_tables_section(doc))
        
        # Combine all sections
        markdown = "\n\n---\n\n".join(sections)
        
        logger.info(f"Generated {len(markdown)} characters of markdown")
        
        return markdown
    
    def _generate_header(self, doc: RequirementsDocument) -> str:
        """Generate document header"""
        title = doc.metadata.get("title", "Requirements Documentation")
        domain = doc.metadata.get("primary_domain", "Analytics")
        
        # Make title more readable
        if domain == "combined":
            title = "Social & KPI Analytics - Genie Demo Documentation"
        elif domain == "social_analytics":
            title = "Social Analytics - Genie Demo Documentation"
        elif domain == "kpi_analytics":
            title = "KPI Analytics - Genie Demo Documentation"
        else:
            title = f"{domain.replace('_', ' ').title()} - Genie Demo Documentation"
        
        return f"# {title}"
    
    def _generate_overview(self, doc: RequirementsDocument) -> str:
        """Generate overview section"""
        date = datetime.now().strftime("%m/%d/%Y")
        num_questions = doc.metadata.get("num_questions", len(doc.all_questions))
        
        # Extract catalog.schema from tables
        catalog_schemas = set()
        for table in doc.all_tables:
            catalog_schemas.add(f"{table.catalog}.{table.schema}")
        catalog_schema_str = ", ".join([f"`{cs}`" for cs in sorted(catalog_schemas)])
        
        summary = doc.metadata.get("summary", f"Requirements document with {num_questions} business questions")
        
        overview = f"""## 개요

| **목적** | AI Agent Demo using Databricks Genie |
| --- | --- |
| **작성자** | Generated from Requirements Conversion Pipeline |
| **작성일자** | {date} |
| **Catalog.Schema** | {catalog_schema_str if catalog_schema_str else '`catalog.schema`'} |

**Summary:** {summary}"""
        
        return overview
    
    def _generate_faq_section(self, doc: RequirementsDocument) -> str:
        """Generate FAQ questions section"""
        num_questions = len(doc.all_questions)
        
        # Group questions by category
        questions_by_category = defaultdict(list)
        for q in doc.all_questions:
            questions_by_category[q.category].append(q)
        
        # Build FAQ section
        lines = [
            "## 📊 질문 목록 (FAQ)",
            "",
            f"총 {num_questions}개 질문:",
            ""
        ]
        
        # Category order preference
        category_order = ["KPI", "Social", "Sentiment", "Trend", "Comparison", "Regional", "Other"]
        
        for category in category_order:
            if category not in questions_by_category:
                continue
            
            questions = questions_by_category[category]
            
            # Category emoji mapping
            emoji_map = {
                "KPI": "📈",
                "Social": "💬",
                "Sentiment": "😊😢",
                "Trend": "📊",
                "Comparison": "🔄",
                "Regional": "🌍",
                "Other": "❓"
            }
            
            emoji = emoji_map.get(category, "")
            lines.append(f"### {emoji} {category} Analysis")
            lines.append("")
            
            # Sort questions by extracting numeric part from ID, then assign sequential numbers
            sorted_questions = sorted(questions, key=lambda x: self._extract_question_number(x.id))
            for idx, q in enumerate(sorted_questions, start=1):
                lines.append(f"{idx}. {q.text}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _extract_question_number(self, question_id: str) -> int:
        """Extract numeric part from question ID for sorting"""
        import re
        match = re.search(r'\d+', question_id)
        return int(match.group()) if match else 9999
    
    def _generate_table_sections(self, doc: RequirementsDocument) -> str:
        """Generate table sections with sample queries"""
        sections = []
        
        for table in doc.all_tables:
            section = self._generate_single_table_section(table, doc)
            if section:
                sections.append(section)
        
        return "\n\n---\n\n".join(sections)
    
    def _generate_single_table_section(self, table: TableInfo, doc: RequirementsDocument) -> str:
        """Generate section for a single table"""
        # Find sample query for this table
        sample_query = table.sample_query
        if not sample_query:
            # Try to find from all_queries
            for query in doc.all_queries:
                if table.full_name in query.query:
                    sample_query = query.query
                    break
        
        # Find sample questions that use this table
        sample_questions = []
        for q in doc.all_questions:
            # Check if this table is in the question's tables_needed list
            # Match by full name or by partial name (table name only)
            for needed_table in q.tables_needed:
                if (table.full_name == needed_table or 
                    table.full_name in needed_table or 
                    needed_table in table.full_name or
                    table.table == needed_table.split('.')[-1]):
                    sample_questions.append(q.text)
                    break  # Only add each question once
        
        # Build section
        lines = [
            f"## {table.description or table.table}",
            "",
            f"**Table:** `{table.full_name}`",
            ""
        ]
        
        if table.related_kpi:
            lines.append(f"**Related KPI:** {table.related_kpi}")
            lines.append("")
        
        # Add sample questions if sample query exists
        if sample_query and sample_questions:
            lines.append("**Sample Questions:**")
            for idx, question in enumerate(sample_questions[:5], start=1):  # Limit to 5 questions
                lines.append(f"{idx}. {question}")
            lines.append("")
        
        if sample_query:
            lines.append("**Sample Query:**")
            lines.append("```sql")
            lines.append(sample_query.strip())
            lines.append("```")
        
        return "\n".join(lines)
    
    def _generate_erd_section(self, doc: RequirementsDocument) -> str:
        """Generate ERD/table relationships section"""
        lines = [
            "## 🗂️ 테이블 정보 (ERD)",
            "",
            "### Core Tables",
            ""
        ]
        
        # List all tables
        lines.append("#### 주요 테이블")
        for table in doc.all_tables:
            lines.append(f"- `{table.full_name}`: {table.description or 'Table'}")
        
        lines.append("")
        lines.append("#### 주요 조인 관계")
        
        # Extract join relationships from questions
        join_relationships = set()
        for q in doc.all_questions:
            for join in q.join_conditions:
                join_relationships.add(join)
        
        if join_relationships:
            lines.append("```")
            for join in sorted(join_relationships)[:10]:  # Limit to 10
                lines.append(join)
            lines.append("```")
        else:
            lines.append("```")
            lines.append("# Join relationships will be extracted from queries")
            lines.append("```")
        
        lines.append("")
        lines.append("#### 주요 컬럼")
        
        # List key columns from tables
        for table in doc.all_tables[:5]:  # First 5 tables
            if table.columns:
                col_names = ", ".join([col.name for col in table.columns[:5]])
                lines.append(f"- **{table.table}**: {col_names}")
        
        return "\n".join(lines)
    
    def _generate_filters_section(self, doc: RequirementsDocument) -> str:
        """Generate common filters and dimensions section"""
        lines = [
            "## 📊 Common Filters & Dimensions",
            "",
            "### Filters",
            "```sql"
        ]
        
        # Extract common filters from questions
        date_filters = set()
        other_filters = set()
        
        for q in doc.all_questions:
            for filter_cond in q.filtering_conditions:
                if 'date' in filter_cond.lower() or 'event_date' in filter_cond.lower():
                    date_filters.add(filter_cond)
                else:
                    other_filters.add(filter_cond)
        
        # Add date filters
        if date_filters:
            lines.append("-- 날짜 필터")
            for f in sorted(date_filters)[:3]:
                lines.append(f)
            lines.append("")
        else:
            lines.append("-- 날짜 필터")
            lines.append("WHERE event_date >= '2024-01-01'")
            lines.append("WHERE event_date >= CURRENT_DATE - 30")
            lines.append("")
        
        # Add other common filters
        if other_filters:
            lines.append("-- 기타 필터")
            for f in sorted(other_filters)[:3]:
                lines.append(f)
        
        lines.append("```")
        lines.append("")
        lines.append("### Key Dimensions")
        
        # Extract dimensions from table columns
        dimensions = set()
        for table in doc.all_tables:
            for col in table.columns:
                col_name = col.name.split(".")[-1] if "." in col.name else col.name
                if any(dim_word in col_name.lower() for dim_word in ['date', 'type', 'category', 'status', 'channel']):
                    dimensions.add(f"**{col_name}**")
        
        if dimensions:
            for dim in sorted(dimensions)[:10]:
                lines.append(f"- {dim}")
        else:
            lines.append("- **event_date**: Date dimension")
            lines.append("- **category**: Category dimension")
        
        return "\n".join(lines)
    
    def _generate_table_mapping(self, doc: RequirementsDocument) -> str:
        """Generate table mapping for business questions"""
        lines = [
            "## 📋 Table Mapping for Business Questions",
            "",
            "### 질문별 테이블 매핑",
            "",
            "| Question | Primary Table | Key Metrics |",
            "|----------|--------------|-------------|"
        ]
        
        # Map questions to tables
        for q in doc.all_questions[:15]:  # First 15 questions
            primary_table = q.tables_needed[0] if q.tables_needed else "N/A"
            # Shorten table name
            if "." in primary_table:
                primary_table = primary_table.split(".")[-1]
            
            # Extract metrics from query if available
            metrics = []
            if q.example_query:
                # Simple extraction of aggregate functions
                for metric_word in ['SUM', 'COUNT', 'AVG', 'MAX', 'MIN']:
                    if metric_word in q.example_query.upper():
                        metrics.append(metric_word)
            
            metrics_str = ", ".join(set(metrics[:3])) if metrics else "Various"
            
            # Truncate question if too long
            question_text = q.text[:50] + "..." if len(q.text) > 50 else q.text
            
            lines.append(f"| {question_text} | {primary_table} | {metrics_str} |")
        
        return "\n".join(lines)
    
    def _generate_meta_tables_section(self, doc: RequirementsDocument) -> str:
        """Generate meta tables section"""
        lines = [
            "## 🗃️ Meta Tables",
            ""
        ]
        
        # Look for tables with 'meta' or 'dim' in name
        meta_tables = [t for t in doc.all_tables if 'meta' in t.table.lower() or 'dim' in t.table.lower()]
        
        if meta_tables:
            for table in meta_tables:
                lines.append(f"### {table.description or table.table}")
                lines.append(f"**Table:** `{table.full_name}`")
                lines.append("")
                
                if table.columns:
                    lines.append("**Key Columns:**")
                    for col in table.columns[:10]:
                        lines.append(f"- `{col.name}`")
                    lines.append("")
        else:
            lines.append("### Metadata Tables")
            lines.append("")
            lines.append("Metadata tables provide reference data for dimensions and lookups.")
        
        return "\n".join(lines)

    def _generate_column_details_section(self, doc: RequirementsDocument) -> str:
        """Generate detailed column metadata section"""
        content = ["## 📋 Column Details\n"]

        has_content = False
        for table in doc.all_tables:
            # Only show tables with enhanced column info
            if not table.columns:
                continue

            # Check if any column has enhanced metadata
            has_enhanced = any(
                col.usage_type or col.transformation_rule or not col.is_required
                for col in table.columns
            )

            if not has_enhanced:
                continue

            has_content = True
            content.append(f"### {table.full_name}\n")
            content.append("| Column | Type | Required | Usage | Notes |\n")
            content.append("|--------|------|----------|-------|-------|\n")

            for col in table.columns:
                req = "✓" if col.is_required else "○"
                usage = col.usage_type or "-"
                notes = col.transformation_rule or "-"
                data_type = col.data_type or "-"
                content.append(f"| `{col.name}` | {data_type} | {req} | {usage} | {notes} |\n")

            if table.table_remarks:
                content.append("\n**Remarks:**\n")
                for remark in table.table_remarks:
                    content.append(f"- {remark}\n")

            content.append("\n")

        if not has_content:
            return ""

        return "".join(content)

    def _generate_join_specs_section(self, doc: RequirementsDocument) -> str:
        """Generate join specifications section"""
        content = ["## 🔗 Join Relationships\n"]

        has_content = False
        for query in doc.all_queries:
            if not query.join_specs:
                continue

            has_content = True
            content.append(f"### {query.question_id}\n")
            for join_spec in query.join_specs:
                optional = " (optional)" if "optional" in join_spec.lower() else " (required)"
                content.append(f"- {join_spec}{optional}\n")
            content.append("\n")

        if not has_content:
            return ""

        return "".join(content)

    def _generate_aggregation_patterns_section(self, doc: RequirementsDocument) -> str:
        """Generate aggregation patterns section"""
        content = ["## 📊 Aggregation Patterns\n"]

        # Collect patterns from all queries
        pattern_usage = defaultdict(list)
        for query in doc.all_queries:
            for pattern in query.aggregation_patterns:
                pattern_usage[pattern].append(query.question_id)

        if not pattern_usage:
            return ""

        for pattern, question_ids in sorted(pattern_usage.items()):
            content.append(f"### {pattern}\n")
            content.append(f"**Used in:** {', '.join(question_ids)}\n\n")

        return "".join(content)

    def _generate_formula_library_section(self, doc: RequirementsDocument) -> str:
        """Generate formula library section (Phase 2)"""
        if not doc.all_formulas:
            return ""

        content = ["## 📐 Formula Library\n"]
        content.append("Reusable metric formulas used across queries.\n\n")

        for formula in doc.all_formulas:
            content.append(f"### {formula.name}\n")
            content.append(f"**Formula:** `{formula.formula}`\n\n")
            content.append(f"**Description:** {formula.description}\n\n")

            if formula.required_columns:
                content.append("**Required Columns:**\n")
                for col in formula.required_columns:
                    content.append(f"- `{col}`\n")
                content.append("\n")

            if formula.required_tables:
                content.append("**Required Tables:**\n")
                for table in formula.required_tables:
                    content.append(f"- `{table}`\n")
                content.append("\n")

            if formula.notes:
                content.append(f"**Notes:** {formula.notes}\n\n")

            if formula.example_usage:
                content.append("**Example Usage:**\n```sql\n")
                content.append(f"{formula.example_usage}\n")
                content.append("```\n\n")

            content.append("---\n\n")

        return "".join(content)

    def _generate_platform_notes_section(self, doc: RequirementsDocument) -> str:
        """Generate platform-specific logic section (Phase 2)"""
        if not doc.platform_notes:
            return ""

        content = ["## 🎮 Platform-Specific Logic\n"]
        content.append("Platform restrictions, transformations, and requirements.\n\n")

        # Group by platform
        by_platform = defaultdict(list)
        for note in doc.platform_notes:
            by_platform[note.platform].append(note)

        for platform in sorted(by_platform.keys()):
            notes = by_platform[platform]
            content.append(f"### {platform}\n")

            # Group by note type
            by_type = defaultdict(list)
            for note in notes:
                by_type[note.note_type].append(note)

            for note_type in ["restriction", "requirement", "transformation", "limitation"]:
                if note_type in by_type:
                    type_notes = by_type[note_type]
                    content.append(f"\n**{note_type.title()}s:**\n")

                    for note in type_notes:
                        content.append(f"\n- {note.description}\n")

                        if note.affected_tables:
                            content.append(f"  - **Tables:** {', '.join([f'`{t}`' for t in note.affected_tables[:3]])}")
                            if len(note.affected_tables) > 3:
                                content.append(f" (+{len(note.affected_tables)-3} more)")
                            content.append("\n")

                        if note.affected_queries:
                            content.append(f"  - **Queries:** {', '.join(note.affected_queries[:5])}")
                            if len(note.affected_queries) > 5:
                                content.append(f" (+{len(note.affected_queries)-5} more)")
                            content.append("\n")

                        if note.example_code:
                            content.append(f"  - **Example:** `{note.example_code}`\n")

            content.append("\n---\n\n")

        return "".join(content)

    def _generate_query_analysis_section(self, doc: RequirementsDocument) -> str:
        """Generate LLM query analysis section (Phase 2)"""
        # Check if any queries have analysis data
        analyzed_queries = [q for q in doc.all_queries if q.intent or q.complexity or q.optimization_notes]

        if not analyzed_queries:
            return ""

        content = ["## 🤖 Query Analysis\n"]
        content.append("AI-powered analysis of query intent, complexity, and optimization opportunities.\n\n")

        for query in analyzed_queries:
            content.append(f"### {query.question_id}: {query.description}\n")

            if query.intent:
                content.append(f"**Intent:** {query.intent.title()}\n")

            if query.complexity:
                complexity_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(query.complexity, "⚪")
                content.append(f"**Complexity:** {complexity_emoji} {query.complexity.title()}\n")

            if query.optimization_notes:
                content.append("\n**Optimization Suggestions:**\n")
                for note in query.optimization_notes:
                    content.append(f"- {note}\n")

            content.append("\n")

        return "".join(content)

    def _generate_result_examples_section(self, doc: RequirementsDocument) -> str:
        """Generate query result examples section (Phase 2)"""
        # Check if any queries have result examples
        queries_with_results = [q for q in doc.all_queries if q.result_example and q.result_example.sample_rows]

        if not queries_with_results:
            return ""

        content = ["## 📋 Query Result Examples\n"]
        content.append("Sample outputs for validation and understanding.\n\n")

        for query in queries_with_results:
            result = query.result_example
            content.append(f"### {query.question_id}\n")

            if result.column_names and result.sample_rows:
                # Generate markdown table
                content.append("| " + " | ".join(result.column_names) + " |\n")
                content.append("|" + "|".join(["---" for _ in result.column_names]) + "|\n")

                for row in result.sample_rows[:10]:  # Limit to 10 rows
                    values = [str(row.get(col, "-")) for col in result.column_names]
                    content.append("| " + " | ".join(values) + " |\n")

            if result.notes:
                content.append(f"\n**Notes:** {result.notes}\n")

            content.append("\n")

        return "".join(content)


def generate_markdown(doc: RequirementsDocument, output_path: str) -> str:
    """
    Convenience function to generate markdown documentation.
    
    Args:
        doc: RequirementsDocument to convert
        output_path: Path where output will be saved
        
    Returns:
        Generated markdown content
    """
    generator = MarkdownGenerator()
    markdown = generator.generate(doc, output_path)
    
    # Save to file
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        logger.info(f"Markdown saved to: {output_path}")
    except Exception as e:
        logger.error(f"Error saving markdown: {e}")
        raise
    
    return markdown
