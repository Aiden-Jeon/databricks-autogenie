"""
Instruction quality scoring for Genie configurations.

This module scores the quality of instructions in Genie configurations based on:
- Specificity (concrete vs vague)
- Structure (markdown formatting)
- Completeness (covers key areas)
- Clarity (no vague terms)
"""

import re
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class InstructionScore:
    """Score for a single instruction."""
    content: str
    total_score: float  # 0-100
    specificity_score: float  # 0-100
    structure_score: float  # 0-100
    clarity_score: float  # 0-100
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def grade(self) -> str:
        """Get letter grade for the score."""
        if self.total_score >= 90:
            return "A"
        elif self.total_score >= 80:
            return "B"
        elif self.total_score >= 70:
            return "C"
        elif self.total_score >= 60:
            return "D"
        else:
            return "F"


@dataclass
class ConfigInstructionQualityReport:
    """Overall instruction quality report for a configuration."""
    instruction_scores: List[InstructionScore]
    average_score: float
    total_instructions: int
    high_quality_count: int  # >= 80
    medium_quality_count: int  # 60-79
    low_quality_count: int  # < 60

    def summary(self) -> str:
        """Get human-readable summary."""
        return (
            f"Instruction Quality Report\n"
            f"{'=' * 50}\n"
            f"Total Instructions: {self.total_instructions}\n"
            f"Average Score: {self.average_score:.1f}/100\n"
            f"High Quality (≥80): {self.high_quality_count}\n"
            f"Medium Quality (60-79): {self.medium_quality_count}\n"
            f"Low Quality (<60): {self.low_quality_count}\n"
        )


class InstructionQualityScorer:
    """
    Scores instruction quality based on best practices.

    Scoring criteria:
    1. Specificity (40 points): Concrete column names, table names, SQL patterns
    2. Structure (30 points): Markdown formatting, headers, lists
    3. Clarity (30 points): No vague terms, clear language

    Usage:
        scorer = InstructionQualityScorer()
        score = scorer.score_instruction(instruction_content)
        print(f"Score: {score.total_score}/100 (Grade: {score.grade()})")
    """

    # Vague terms that should be avoided
    VAGUE_TERMS = [
        'appropriate', 'relevant', 'good', 'bad', 'properly', 'correctly',
        'suitable', 'reasonable', 'as needed', 'when necessary', 'if needed',
        'handle', 'deal with', 'take care of', 'manage'
    ]

    # Specificity indicators (concrete references)
    SPECIFICITY_PATTERNS = {
        'column_references': r'`[a-zA-Z_][a-zA-Z0-9_]*`',  # `column_name`
        'table_references': r'`[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?`',  # `schema.table`
        'sql_keywords': r'`(?:SELECT|FROM|WHERE|JOIN|GROUP BY|ORDER BY|LIMIT|HAVING|CAST|SUM|COUNT|AVG)`',
        'date_functions': r'(?:CURRENT_DATE|DATE_SUB|DATE_ADD|DATE_TRUNC)',
        'concrete_examples': r'(?:e\.g\.|for example|such as)',
        'specific_values': r"'[^']+'" # String literals
    }

    # Structure indicators (markdown formatting)
    STRUCTURE_PATTERNS = {
        'headers': r'^##\s+.+$',  # Markdown headers
        'bullet_lists': r'^\s*[-*]\s+.+$',  # Bullet lists
        'numbered_lists': r'^\s*\d+\.\s+.+$',  # Numbered lists
        'bold_text': r'\*\*.+?\*\*',  # Bold text
        'code_inline': r'`.+?`',  # Inline code
        'code_blocks': r'```[\s\S]+?```',  # Code blocks
        'blockquotes': r'^>\s+.+$',  # Blockquotes
    }

    def __init__(self):
        """Initialize the instruction quality scorer."""
        pass

    def score_instruction(self, content: str, priority: int = None) -> InstructionScore:
        """
        Score a single instruction.

        Args:
            content: Instruction content
            priority: Optional priority value (1=critical, 2=important, 3+=optional)

        Returns:
            InstructionScore with detailed scoring
        """
        issues = []
        suggestions = []

        # 1. Score specificity (40 points)
        specificity_score, spec_issues, spec_suggestions = self._score_specificity(content)
        issues.extend(spec_issues)
        suggestions.extend(spec_suggestions)

        # 2. Score structure (30 points)
        structure_score, struct_issues, struct_suggestions = self._score_structure(content)
        issues.extend(struct_issues)
        suggestions.extend(struct_suggestions)

        # 3. Score clarity (30 points)
        clarity_score, clarity_issues, clarity_suggestions = self._score_clarity(content)
        issues.extend(clarity_issues)
        suggestions.extend(clarity_suggestions)

        # Calculate total score
        total_score = specificity_score + structure_score + clarity_score

        # Apply priority bonus/penalty
        if priority is not None:
            if priority == 1 and total_score < 80:
                # Critical instructions should be high quality
                issues.append("Critical instruction (priority 1) should score ≥80")
                suggestions.append("Improve specificity and clarity for critical instructions")

        return InstructionScore(
            content=content,
            total_score=total_score,
            specificity_score=specificity_score,
            structure_score=structure_score,
            clarity_score=clarity_score,
            issues=issues,
            suggestions=suggestions
        )

    def _score_specificity(self, content: str) -> Tuple[float, List[str], List[str]]:
        """
        Score specificity (0-40 points).

        Checks for:
        - Column references (backticks)
        - Table references
        - SQL keywords
        - Concrete examples
        - Specific values
        """
        score = 0.0
        issues = []
        suggestions = []
        max_score = 40.0

        # Count specificity indicators
        indicator_counts = {}
        for indicator, pattern in self.SPECIFICITY_PATTERNS.items():
            matches = re.findall(pattern, content, re.MULTILINE)
            indicator_counts[indicator] = len(matches)

        # Score based on presence and density of indicators
        total_indicators = sum(indicator_counts.values())

        if total_indicators == 0:
            score = 0
            issues.append("No specific references found (no column names, table names, or SQL keywords)")
            suggestions.append("Add concrete column names (e.g., `event_date`), table references, or SQL patterns")
        elif total_indicators <= 2:
            score = 10
            issues.append("Very few specific references")
            suggestions.append("Add more concrete examples with column names and SQL patterns")
        elif total_indicators <= 5:
            score = 20
            suggestions.append("Good specificity, but could add more concrete examples")
        elif total_indicators <= 10:
            score = 30
        else:
            score = max_score

        # Bonus for having diverse types of indicators
        indicator_types_present = sum(1 for count in indicator_counts.values() if count > 0)
        if indicator_types_present >= 3:
            score = min(max_score, score + 5)

        return score, issues, suggestions

    def _score_structure(self, content: str) -> Tuple[float, List[str], List[str]]:
        """
        Score structure (0-30 points).

        Checks for:
        - Markdown headers (##)
        - Bullet or numbered lists
        - Bold text for emphasis
        - Code formatting
        - Blockquotes for clarification questions
        """
        score = 0.0
        issues = []
        suggestions = []
        max_score = 30.0

        # Count structure elements
        structure_counts = {}
        for element, pattern in self.STRUCTURE_PATTERNS.items():
            matches = re.findall(pattern, content, re.MULTILINE)
            structure_counts[element] = len(matches)

        # Check for key structural elements
        has_headers = structure_counts['headers'] > 0
        has_lists = (structure_counts['bullet_lists'] + structure_counts['numbered_lists']) > 0
        has_emphasis = structure_counts['bold_text'] > 0
        has_code = (structure_counts['code_inline'] + structure_counts['code_blocks']) > 0

        # Score structure
        if not any(structure_counts.values()):
            score = 0
            issues.append("No markdown formatting found")
            suggestions.append("Use markdown: ## headers, - bullet lists, **bold**, `code`")
        else:
            # Award points for each structural element type
            if has_headers:
                score += 10
            else:
                suggestions.append("Add ## headers to organize related instructions")

            if has_lists:
                score += 8
            else:
                suggestions.append("Use bullet lists (-) for multiple related points")

            if has_emphasis:
                score += 6
            else:
                suggestions.append("Use **bold** for critical terms")

            if has_code:
                score += 6
            else:
                suggestions.append("Use `code formatting` for column/table names")

        # Length check - instructions should be substantial but not too long
        word_count = len(content.split())
        if word_count < 10:
            issues.append(f"Very short instruction ({word_count} words)")
            suggestions.append("Provide more detailed guidance")
        elif word_count > 500:
            issues.append(f"Very long instruction ({word_count} words)")
            suggestions.append("Consider breaking into multiple focused instructions")

        return min(max_score, score), issues, suggestions

    def _score_clarity(self, content: str) -> Tuple[float, List[str], List[str]]:
        """
        Score clarity (0-30 points).

        Checks for:
        - Absence of vague terms
        - Clear, actionable language
        - Specific directives
        """
        score = 30.0  # Start with perfect score, deduct for issues
        issues = []
        suggestions = []

        # Check for vague terms
        vague_terms_found = []
        content_lower = content.lower()

        for term in self.VAGUE_TERMS:
            if re.search(r'\b' + term + r'\b', content_lower):
                vague_terms_found.append(term)

        if vague_terms_found:
            # Deduct points based on number of vague terms
            deduction = min(15, len(vague_terms_found) * 3)
            score -= deduction
            issues.append(f"Contains vague terms: {', '.join(vague_terms_found[:3])}")
            suggestions.append("Replace vague terms with specific directives")

        # Check for unclear references (e.g., "it", "this", "that" without context)
        unclear_pronouns = ['it', 'this', 'that', 'these', 'those']
        unclear_count = 0
        for pronoun in unclear_pronouns:
            # Count pronouns that aren't followed by clear noun phrases
            pattern = r'\b' + pronoun + r'\b(?!\s+(?:column|table|field|value|query|instruction))'
            unclear_count += len(re.findall(pattern, content_lower))

        if unclear_count > 3:
            score -= 5
            issues.append("Multiple unclear pronoun references")
            suggestions.append("Use specific nouns instead of pronouns (e.g., 'the event_date column' instead of 'it')")

        # Check for passive voice (often less clear)
        passive_indicators = ['should be', 'must be', 'can be', 'will be', 'is used', 'are used']
        passive_count = sum(1 for indicator in passive_indicators if indicator in content_lower)

        if passive_count > 2:
            score -= 5
            suggestions.append("Use active voice for clearer instructions (e.g., 'Use event_date' instead of 'event_date should be used')")

        # Check for actionable language
        action_verbs = ['use', 'filter', 'join', 'group', 'order', 'select', 'include', 'exclude', 'calculate', 'apply']
        has_action_verbs = any(verb in content_lower for verb in action_verbs)

        if not has_action_verbs:
            score -= 5
            issues.append("Lacks clear action verbs")
            suggestions.append("Start instructions with clear action verbs (Use, Filter, Join, etc.)")

        return max(0, score), issues, suggestions

    def score_config_instructions(
        self,
        config: Dict[str, Any]
    ) -> ConfigInstructionQualityReport:
        """
        Score all instructions in a Genie configuration.

        Args:
            config: Genie space configuration dictionary

        Returns:
            ConfigInstructionQualityReport with overall quality metrics
        """
        instructions = config.get("instructions", [])
        instruction_scores = []

        for instruction in instructions:
            content = instruction.get("content", "")
            priority = instruction.get("priority")

            score = self.score_instruction(content, priority)
            instruction_scores.append(score)

        # Calculate summary statistics
        if instruction_scores:
            average_score = sum(s.total_score for s in instruction_scores) / len(instruction_scores)
            high_quality = sum(1 for s in instruction_scores if s.total_score >= 80)
            medium_quality = sum(1 for s in instruction_scores if 60 <= s.total_score < 80)
            low_quality = sum(1 for s in instruction_scores if s.total_score < 60)
        else:
            average_score = 0
            high_quality = medium_quality = low_quality = 0

        return ConfigInstructionQualityReport(
            instruction_scores=instruction_scores,
            average_score=average_score,
            total_instructions=len(instructions),
            high_quality_count=high_quality,
            medium_quality_count=medium_quality,
            low_quality_count=low_quality
        )


def generate_instruction_improvement_suggestions(score: InstructionScore) -> str:
    """
    Generate detailed improvement suggestions for a low-scoring instruction.

    Args:
        score: InstructionScore to generate suggestions for

    Returns:
        Formatted string with improvement suggestions
    """
    if score.total_score >= 80:
        return f"✅ High quality instruction (Score: {score.total_score:.1f}/100)"

    output = []
    output.append(f"⚠️ Instruction Score: {score.total_score:.1f}/100 (Grade: {score.grade()})")
    output.append(f"\nBreakdown:")
    output.append(f"  - Specificity: {score.specificity_score:.1f}/40")
    output.append(f"  - Structure: {score.structure_score:.1f}/30")
    output.append(f"  - Clarity: {score.clarity_score:.1f}/30")

    if score.issues:
        output.append(f"\n❌ Issues:")
        for issue in score.issues:
            output.append(f"  - {issue}")

    if score.suggestions:
        output.append(f"\n💡 Suggestions:")
        for suggestion in score.suggestions:
            output.append(f"  - {suggestion}")

    output.append(f"\n📄 Current instruction (first 200 chars):")
    output.append(f"  {score.content[:200]}...")

    return "\n".join(output)
