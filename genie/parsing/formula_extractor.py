"""
Formula Extractor Module
Extracts and catalogs reusable metric formulas from queries.
"""

import re
import logging
from typing import Dict, List, Set
from collections import defaultdict

from genie.parsing.requirements_structurer import FormulaDefinition, SQLQuery

logger = logging.getLogger(__name__)


class FormulaExtractor:
    """
    Extracts reusable metric formulas from SQL queries.
    Identifies common patterns like DAU, ARPU, retention rates, etc.
    """

    # Known formula patterns with their signatures
    FORMULA_PATTERNS = {
        "DAU": {
            "pattern": r"COUNT\s*\(\s*DISTINCT\s+(?:\w+\.)?user_id\s*\)",
            "description": "Daily Active Users - count of unique users",
            "required_columns": ["user_id"],
            "example": "COUNT(DISTINCT user_id)"
        },
        "MAU": {
            "pattern": r"COUNT\s*\(\s*DISTINCT\s+(?:\w+\.)?user_id\s*\)",
            "description": "Monthly Active Users - count of unique users over a month",
            "required_columns": ["user_id"],
            "example": "COUNT(DISTINCT user_id)"
        },
        "ARPU": {
            "pattern": r"(?:try_)?divide\s*\(\s*SUM\s*\([^)]+\)\s*,\s*COUNT\s*\(\s*DISTINCT\s+(?:\w+\.)?user_id\s*\)",
            "description": "Average Revenue Per User",
            "required_columns": ["revenue", "user_id"],
            "example": "try_divide(SUM(revenue), COUNT(DISTINCT user_id))"
        },
        "ARPPU": {
            "pattern": r"(?:try_)?divide\s*\(\s*SUM\s*\([^)]+\)\s*,\s*COUNT\s*\(\s*DISTINCT\s+(?:\w+\.)?paying_user",
            "description": "Average Revenue Per Paying User",
            "required_columns": ["revenue", "paying_user_id"],
            "example": "try_divide(SUM(revenue), COUNT(DISTINCT paying_user_id))"
        },
        "CONVERSION_RATE": {
            "pattern": r"(?:try_)?divide\s*\(\s*COUNT\s*\(\s*DISTINCT.*?paying.*?\)\s*,\s*COUNT\s*\(\s*DISTINCT.*?user",
            "description": "Conversion Rate - percentage of paying users",
            "required_columns": ["paying_user_id", "user_id"],
            "example": "try_divide(COUNT(DISTINCT paying_user_id), COUNT(DISTINCT user_id))"
        },
        "RETENTION_RATE": {
            "pattern": r"(?:try_)?divide\s*\(\s*COUNT\s*\(\s*DISTINCT.*?retained.*?\)\s*,\s*COUNT\s*\(\s*DISTINCT.*?user",
            "description": "Retention Rate - percentage of users who return",
            "required_columns": ["user_id", "cohort_date"],
            "example": "try_divide(COUNT(DISTINCT retained_users), COUNT(DISTINCT cohort_users))"
        },
        "ENGAGEMENT_RATE": {
            "pattern": r"(?:try_)?divide\s*\(\s*SUM\s*\(.*?(?:event|action|engagement).*?\)\s*,\s*COUNT\s*\(\s*DISTINCT",
            "description": "Engagement Rate - average actions per user",
            "required_columns": ["event_count", "user_id"],
            "example": "try_divide(SUM(event_count), COUNT(DISTINCT user_id))"
        }
    }

    def __init__(self):
        """Initialize formula extractor"""
        pass

    def extract_formulas(self, queries: List[SQLQuery]) -> List[FormulaDefinition]:
        """
        Extract formula definitions from queries.

        Args:
            queries: List of SQL queries to analyze

        Returns:
            List of FormulaDefinition objects
        """
        logger.info(f"Extracting formulas from {len(queries)} queries")

        formulas = []
        formula_usage = defaultdict(list)  # Track which queries use which formulas

        for query in queries:
            # Check each known formula pattern
            for formula_name, pattern_info in self.FORMULA_PATTERNS.items():
                if re.search(pattern_info["pattern"], query.query, re.IGNORECASE):
                    formula_usage[formula_name].append(query.question_id)

        # Create formula definitions for detected patterns
        for formula_name, query_ids in formula_usage.items():
            pattern_info = self.FORMULA_PATTERNS[formula_name]

            formula = FormulaDefinition(
                name=formula_name,
                formula=pattern_info["example"],
                description=pattern_info["description"],
                required_columns=pattern_info["required_columns"],
                notes=f"Used in {len(query_ids)} queries: {', '.join(query_ids[:5])}{'...' if len(query_ids) > 5 else ''}",
                example_usage=self._extract_actual_formula(queries, query_ids[0], pattern_info["pattern"])
            )
            formulas.append(formula)

        logger.info(f"Extracted {len(formulas)} formula definitions")
        return formulas

    def _extract_actual_formula(self, queries: List[SQLQuery], query_id: str, pattern: str) -> str:
        """Extract the actual formula text from a query"""
        for query in queries:
            if query.question_id == query_id:
                match = re.search(pattern, query.query, re.IGNORECASE | re.DOTALL)
                if match:
                    # Clean up whitespace
                    formula_text = ' '.join(match.group(0).split())
                    return formula_text
        return ""

    def extract_custom_formulas(self, queries: List[SQLQuery]) -> List[FormulaDefinition]:
        """
        Extract custom formulas from query descriptions or comments.
        Looks for patterns like "Formula:", "Metric:", etc.

        Args:
            queries: List of SQL queries to analyze

        Returns:
            List of custom FormulaDefinition objects
        """
        custom_formulas = []

        for query in queries:
            # Look for formula definitions in descriptions
            desc_lower = query.description.lower()

            # Check for formula keywords
            if any(keyword in desc_lower for keyword in ["formula:", "metric:", "calculation:"]):
                # Try to extract the formula name and definition
                formula_match = re.search(
                    r"(?:formula|metric|calculation):\s*([^-\n]+?)(?:\s*-\s*(.+?))?(?:\n|$)",
                    query.description,
                    re.IGNORECASE
                )

                if formula_match:
                    formula_name = formula_match.group(1).strip()
                    formula_desc = formula_match.group(2).strip() if formula_match.group(2) else ""

                    # Try to extract the actual SQL expression
                    # Look for expressions in SELECT clause
                    select_match = re.search(
                        r"SELECT\s+(.+?)\s+(?:as|AS)\s+" + re.escape(formula_name),
                        query.query,
                        re.IGNORECASE | re.DOTALL
                    )

                    if select_match:
                        formula_expr = ' '.join(select_match.group(1).split())

                        custom_formulas.append(FormulaDefinition(
                            name=formula_name,
                            formula=formula_expr,
                            description=formula_desc or f"Custom metric from {query.question_id}",
                            notes=f"Defined in {query.question_id}",
                            example_usage=formula_expr
                        ))

        logger.info(f"Extracted {len(custom_formulas)} custom formulas")
        return custom_formulas

    def deduplicate_formulas(self, formulas: List[FormulaDefinition]) -> List[FormulaDefinition]:
        """Remove duplicate formulas based on name"""
        seen_names = set()
        unique_formulas = []

        for formula in formulas:
            if formula.name not in seen_names:
                seen_names.add(formula.name)
                unique_formulas.append(formula)

        return unique_formulas


def extract_formulas(queries: List[SQLQuery]) -> List[FormulaDefinition]:
    """
    Convenience function to extract all formulas from queries.

    Args:
        queries: List of SQL queries

    Returns:
        Deduplicated list of FormulaDefinition objects
    """
    extractor = FormulaExtractor()

    # Extract both known patterns and custom formulas
    known_formulas = extractor.extract_formulas(queries)
    custom_formulas = extractor.extract_custom_formulas(queries)

    # Combine and deduplicate
    all_formulas = known_formulas + custom_formulas
    return extractor.deduplicate_formulas(all_formulas)
