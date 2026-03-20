"""
Platform Analyzer Module
Extracts and organizes platform-specific logic and restrictions.
"""

import re
import logging
from typing import Dict, List, Set
from collections import defaultdict

from genie.parsing.requirements_structurer import PlatformNote, TableInfo, SQLQuery

logger = logging.getLogger(__name__)


class PlatformAnalyzer:
    """
    Analyzes tables and queries for platform-specific logic.
    Identifies restrictions, transformations, and special requirements.
    """

    # Platform keywords to detect
    PLATFORM_KEYWORDS = {
        "PUBG": ["pubg", "gcoin", "battlegrounds"],
        "Steam": ["steam", "wishlist", "review", "store"],
        "Discord": ["discord", "message", "reaction", "channel"],
        "General": []
    }

    # Restriction patterns
    RESTRICTION_PATTERNS = {
        "platform_only": r"(?:PUBG|Steam|Discord)\s+only",
        "not_available": r"not\s+available\s+for\s+(?:other\s+)?(?:games?|platforms?)",
        "requires": r"requires?\s+([^.]+)",
        "must_specify": r"must\s+(?:be\s+)?specif(?:y|ied)\s+([^.]+)",
    }

    # Transformation patterns
    TRANSFORMATION_PATTERNS = {
        "from_unixtime": r"FROM_UNIXTIME\s*\([^)]+\)",
        "timestamp_conversion": r"(?:to_timestamp|cast\s*\([^)]+\s+as\s+timestamp)",
        "date_trunc": r"DATE_TRUNC\s*\([^)]+\)",
        "timezone_conversion": r"(?:AT\s+TIME\s+ZONE|'Asia/Seoul'|'UTC')",
    }

    def __init__(self):
        """Initialize platform analyzer"""
        pass

    def analyze_tables(self, tables: List[TableInfo]) -> List[PlatformNote]:
        """
        Analyze tables for platform-specific notes.

        Args:
            tables: List of table information

        Returns:
            List of PlatformNote objects
        """
        logger.info(f"Analyzing {len(tables)} tables for platform-specific logic")

        platform_notes = []

        for table in tables:
            # Detect platform from table name
            platform = self._detect_platform(table.full_name)

            # Check table remarks for restrictions
            for remark in table.table_remarks:
                note_type, description = self._classify_remark(remark)

                if note_type:
                    platform_notes.append(PlatformNote(
                        platform=platform,
                        note_type=note_type,
                        description=description,
                        affected_tables=[table.full_name]
                    ))

            # Check for platform-only indicators in table name
            if any(keyword in table.full_name.lower() for keyword in ["pubg", "steam", "discord"]):
                if "only" in " ".join(table.table_remarks).lower():
                    platform_notes.append(PlatformNote(
                        platform=platform,
                        note_type="restriction",
                        description=f"Table available for {platform} only",
                        affected_tables=[table.full_name]
                    ))

        logger.info(f"Extracted {len(platform_notes)} platform notes from tables")
        return platform_notes

    def analyze_queries(self, queries: List[SQLQuery]) -> List[PlatformNote]:
        """
        Analyze queries for platform-specific transformations and logic.

        Args:
            queries: List of SQL queries

        Returns:
            List of PlatformNote objects
        """
        logger.info(f"Analyzing {len(queries)} queries for platform-specific logic")

        platform_notes = []

        # Track transformation usage
        transformation_usage = defaultdict(list)

        for query in queries:
            # Detect transformations
            for trans_name, pattern in self.TRANSFORMATION_PATTERNS.items():
                if re.search(pattern, query.query, re.IGNORECASE):
                    transformation_usage[trans_name].append(query.question_id)

                    # Extract the actual transformation code
                    match = re.search(pattern, query.query, re.IGNORECASE)
                    if match:
                        code_example = match.group(0)

                        # Determine platform from query context
                        platform = self._detect_platform_from_query(query)

                        platform_notes.append(PlatformNote(
                            platform=platform,
                            note_type="transformation",
                            description=self._get_transformation_description(trans_name),
                            affected_queries=[query.question_id],
                            example_code=code_example
                        ))

        logger.info(f"Extracted {len(platform_notes)} platform notes from queries")
        return platform_notes

    def _detect_platform(self, text: str) -> str:
        """Detect platform from text (table name, query, etc.)"""
        text_lower = text.lower()

        for platform, keywords in self.PLATFORM_KEYWORDS.items():
            if any(keyword in text_lower for keyword in keywords):
                return platform

        return "All"

    def _detect_platform_from_query(self, query: SQLQuery) -> str:
        """Detect platform from query tables and content"""
        # Check tables used
        for table in query.tables_used:
            platform = self._detect_platform(table)
            if platform != "All":
                return platform

        # Check query text
        return self._detect_platform(query.query)

    def _classify_remark(self, remark: str) -> tuple:
        """
        Classify a remark into note_type and extract description.

        Returns:
            (note_type, description) tuple
        """
        remark_lower = remark.lower()

        # Check for restrictions
        if any(pattern in remark_lower for pattern in ["only", "not available", "restricted"]):
            return ("restriction", remark)

        # Check for requirements
        if any(pattern in remark_lower for pattern in ["required", "must", "need"]):
            return ("requirement", remark)

        # Check for transformations
        if any(pattern in remark_lower for pattern in ["convert", "transform", "format"]):
            return ("transformation", remark)

        # Check for limitations
        if any(pattern in remark_lower for pattern in ["limit", "cannot", "max", "maximum"]):
            return ("limitation", remark)

        # Default: general note
        return ("requirement", remark)

    def _get_transformation_description(self, trans_name: str) -> str:
        """Get human-readable description for transformation type"""
        descriptions = {
            "from_unixtime": "Convert Unix timestamp to readable datetime format",
            "timestamp_conversion": "Convert string or numeric value to timestamp type",
            "date_trunc": "Truncate date to specific granularity (day, week, month)",
            "timezone_conversion": "Convert timestamp between timezones (UTC, Asia/Seoul)",
        }
        return descriptions.get(trans_name, "Data transformation")

    def deduplicate_notes(self, notes: List[PlatformNote]) -> List[PlatformNote]:
        """
        Deduplicate platform notes by description and platform.
        Merge affected_tables and affected_queries.
        """
        notes_dict = {}

        for note in notes:
            key = (note.platform, note.note_type, note.description)

            if key in notes_dict:
                # Merge affected resources
                existing = notes_dict[key]
                existing.affected_tables.extend(note.affected_tables)
                existing.affected_queries.extend(note.affected_queries)
                # Keep first example code
                if not existing.example_code and note.example_code:
                    existing.example_code = note.example_code
            else:
                notes_dict[key] = note

        # Deduplicate affected resources
        for note in notes_dict.values():
            note.affected_tables = list(set(note.affected_tables))
            note.affected_queries = list(set(note.affected_queries))

        return list(notes_dict.values())


def analyze_platform_logic(tables: List[TableInfo], queries: List[SQLQuery]) -> List[PlatformNote]:
    """
    Convenience function to analyze all platform-specific logic.

    Args:
        tables: List of table information
        queries: List of SQL queries

    Returns:
        Deduplicated list of PlatformNote objects
    """
    analyzer = PlatformAnalyzer()

    # Analyze tables and queries
    table_notes = analyzer.analyze_tables(tables)
    query_notes = analyzer.analyze_queries(queries)

    # Combine and deduplicate
    all_notes = table_notes + query_notes
    return analyzer.deduplicate_notes(all_notes)
