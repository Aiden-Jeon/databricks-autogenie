"""
LLM Enricher Module
Uses LLM to enrich and refine requirements with descriptions, summaries, and refinements.
"""

import logging
import json
from typing import Dict, List, Optional
from dataclasses import asdict

from genie.parsing.requirements_structurer import RequirementsDocument, Question, TableInfo, SQLQuery

logger = logging.getLogger(__name__)


class LLMEnricher:
    """
    Enriches requirements document using LLM.
    Adds descriptions, summaries, and refines content.
    """
    
    def __init__(self, llm_client, enrichment_progress_callback=None):
        """
        Initialize LLM enricher.

        Args:
            llm_client: LLM client (DatabricksFoundationModelClient)
            enrichment_progress_callback: Optional callback for progress updates
        """
        self.llm_client = llm_client
        self.enrichment_progress_callback = enrichment_progress_callback
    
    def enrich_document(self, doc: RequirementsDocument) -> tuple[RequirementsDocument, dict]:
        """
        Enrich requirements document with LLM-generated content.

        Args:
            doc: RequirementsDocument to enrich

        Returns:
            Tuple of (Enriched RequirementsDocument, enrichment reasoning dict)
        """
        logger.info("Enriching requirements document with LLM")

        reasoning = {}

        # Enrich tables (add descriptions if missing)
        if self.enrichment_progress_callback:
            self.enrichment_progress_callback("tables_start", f"Starting to enrich {len([t for t in doc.all_tables if not t.description or t.description == 'Unknown'])} table descriptions")

        tables_enriched = self._enrich_tables(doc.all_tables)
        reasoning["tables_enrichment"] = f"Enriched {tables_enriched} table descriptions using LLM to provide business context and purpose"

        if self.enrichment_progress_callback:
            self.enrichment_progress_callback("tables_complete", f"✓ Enriched {tables_enriched} table descriptions with business context")

        # Enrich queries (add descriptions if missing)
        if self.enrichment_progress_callback:
            self.enrichment_progress_callback("queries_start", f"Starting to enhance {len([q for q in doc.all_queries if not q.description or q.description.startswith('Query for')])} SQL query descriptions")

        queries_enriched = self._enrich_queries(doc.all_queries)
        reasoning["queries_enrichment"] = f"Enhanced {queries_enriched} SQL query descriptions to clarify business questions and key metrics"

        if self.enrichment_progress_callback:
            self.enrichment_progress_callback("queries_complete", f"✓ Enhanced {queries_enriched} SQL query descriptions")

        # Generate business scenarios
        if self.enrichment_progress_callback:
            self.enrichment_progress_callback("scenarios_start", "Analyzing questions to generate business scenarios")

        scenarios = self._generate_scenarios(doc)
        doc.metadata["business_scenarios"] = scenarios
        reasoning["scenarios_generation"] = f"Generated {len(scenarios)} realistic business scenarios based on question categories and patterns"

        if self.enrichment_progress_callback:
            self.enrichment_progress_callback("scenarios_complete", f"✓ Generated {len(scenarios)} business scenarios")

        # Generate document summary
        if self.enrichment_progress_callback:
            self.enrichment_progress_callback("summary_start", "Creating comprehensive document summary")

        summary = self._generate_summary(doc)
        doc.metadata["summary"] = summary
        reasoning["summary_generation"] = f"Created comprehensive document summary covering {len(doc.all_questions)} questions across {len(doc.all_tables)} tables"

        if self.enrichment_progress_callback:
            self.enrichment_progress_callback("summary_complete", f"✓ Created document summary ({len(doc.all_questions)} questions, {len(doc.all_tables)} tables)")

        reasoning["overall"] = f"LLM enrichment complete: Enhanced {tables_enriched} tables, {queries_enriched} queries, generated {len(scenarios)} scenarios"

        logger.info("Document enrichment complete")

        return doc, reasoning
    
    def _enrich_tables(self, tables: List[TableInfo]) -> int:
        """Enrich table descriptions using LLM. Returns count of enriched tables."""
        logger.info(f"Enriching {len(tables)} tables")

        enriched_count = 0
        for table in tables:
            if not table.description or table.description == "Unknown":
                try:
                    description = self._generate_table_description(table)
                    table.description = description
                    enriched_count += 1
                    logger.debug(f"Generated description for {table.full_name}")
                except Exception as e:
                    logger.error(f"Error enriching table {table.full_name}: {e}")

        return enriched_count
    
    def _enrich_queries(self, queries: List[SQLQuery]) -> int:
        """Enrich query descriptions using LLM. Returns count of enriched queries."""
        logger.info(f"Enriching {len(queries)} queries")

        enriched_count = 0
        for query in queries:
            if not query.description or query.description.startswith("Query for"):
                try:
                    description = self._generate_query_description(query)
                    query.description = description
                    enriched_count += 1
                    logger.debug(f"Generated description for query {query.question_id}")
                except Exception as e:
                    logger.error(f"Error enriching query {query.question_id}: {e}")

        return enriched_count
    
    def _generate_table_description(self, table: TableInfo) -> str:
        """Generate description for a table using LLM"""
        prompt = f"""Generate a concise 1-2 sentence description for this database table:

Table: {table.full_name}
Columns: {', '.join([col.name for col in table.columns])}
Related KPI: {table.related_kpi or 'None'}

Description should explain:
1. What data this table contains
2. What business purpose it serves

Respond with ONLY the description, no additional text."""
        
        try:
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.1,
                max_tokens=200
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating table description: {e}")
            return table.description or "Database table"
    
    def _generate_query_description(self, query: SQLQuery) -> str:
        """Generate description for a SQL query using LLM"""
        # Truncate query if too long
        query_text = query.query[:1000] + "..." if len(query.query) > 1000 else query.query
        
        prompt = f"""Generate a concise 1-2 sentence description for this SQL query:

Query:
{query_text}

Description should explain:
1. What business question this query answers
2. Key metrics or data it returns

Respond with ONLY the description, no additional text."""
        
        try:
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.1,
                max_tokens=200
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating query description: {e}")
            return query.description or "SQL query"
    
    def _generate_scenarios(self, doc: RequirementsDocument) -> List[Dict]:
        """Generate business scenario examples using LLM"""
        logger.info("Generating business scenarios")
        
        # Select top 3-5 questions from different categories
        sample_questions = []
        seen_categories = set()
        
        for question in doc.all_questions:
            if question.category not in seen_categories and len(sample_questions) < 5:
                sample_questions.append(question)
                seen_categories.add(question.category)
        
        if not sample_questions:
            return []
        
        questions_text = "\n".join([f"{i+1}. {q.text}" for i, q in enumerate(sample_questions)])
        
        prompt = f"""Based on these business questions, generate 3-5 realistic business scenarios where these questions would be asked:

Questions:
{questions_text}

For each scenario, provide:
1. Title (brief, 3-5 words)
2. Description (1-2 sentences)
3. Related questions (by number)

Return as JSON array:
[
  {{
    "title": "...",
    "description": "...",
    "related_questions": [1, 2]
  }}
]

Respond with ONLY valid JSON, no additional text."""
        
        try:
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.3,
                max_tokens=1000
            )
            
            # Parse JSON response
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            elif response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            
            scenarios = json.loads(response_clean.strip())
            return scenarios
        except Exception as e:
            logger.error(f"Error generating scenarios: {e}")
            return []
    
    def _generate_summary(self, doc: RequirementsDocument) -> str:
        """Generate summary of requirements document using LLM"""
        logger.info("Generating document summary")
        
        # Prepare statistics
        stats = {
            "num_questions": len(doc.all_questions),
            "num_tables": len(doc.all_tables),
            "num_queries": len(doc.all_queries),
            "categories": list(set([q.category for q in doc.all_questions])),
            "domains": doc.metadata.get("domains", [])
        }
        
        # Sample questions (first 10)
        sample_questions = [q.text for q in doc.all_questions[:10]]
        
        prompt = f"""Generate a concise 2-3 paragraph summary of this requirements document:

Statistics:
- Questions: {stats['num_questions']}
- Tables: {stats['num_tables']}
- SQL Queries: {stats['num_queries']}
- Categories: {', '.join(stats['categories'])}
- Domains: {', '.join(stats['domains'])}

Sample Questions:
{chr(10).join([f'- {q}' for q in sample_questions])}

Summary should cover:
1. Overall purpose and scope
2. Key question categories
3. Main data sources

Write in clear, professional language."""
        
        try:
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.2,
                max_tokens=500
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return f"Requirements document with {stats['num_questions']} questions across {stats['num_tables']} tables."
    
    def refine_questions(self, questions: List[Question]) -> List[Question]:
        """
        Refine question phrasing for clarity using LLM.
        
        Args:
            questions: List of questions to refine
            
        Returns:
            List of refined questions
        """
        logger.info(f"Refining {len(questions)} questions")
        
        for question in questions:
            try:
                refined_text = self._refine_question_text(question.text)
                if refined_text and refined_text != question.text:
                    question.text = refined_text
                    logger.debug(f"Refined question {question.id}")
            except Exception as e:
                logger.error(f"Error refining question {question.id}: {e}")
        
        return questions
    
    def _refine_question_text(self, question_text: str) -> str:
        """Refine a single question text using LLM"""
        prompt = f"""Refine this business question for clarity while preserving its meaning and language (Korean/English):

Original: {question_text}

Guidelines:
- Keep the same language (if Korean, respond in Korean)
- Make it more precise and professional
- Preserve all key information
- Keep it concise

Respond with ONLY the refined question, no additional text."""
        
        try:
            response = self.llm_client.generate(
                prompt=prompt,
                temperature=0.1,
                max_tokens=150
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Error refining question: {e}")
            return question_text


def enrich_requirements(doc: RequirementsDocument, llm_client) -> tuple[RequirementsDocument, dict]:
    """
    Convenience function to enrich requirements document.

    Args:
        doc: RequirementsDocument to enrich
        llm_client: LLM client for enrichment

    Returns:
        Tuple of (Enriched RequirementsDocument, enrichment reasoning dict)
    """
    enricher = LLMEnricher(llm_client)
    return enricher.enrich_document(doc)
