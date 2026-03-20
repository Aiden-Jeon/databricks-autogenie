"""
Prompt Loader for Genie Space Enhancement V2

Loads the 4 specialized prompt templates:
- metric_view_analysis.txt
- metadata_analysis.txt
- sample_query_analysis.txt
- instruction_analysis.txt
"""

from pathlib import Path
from typing import Dict
import json


class PromptLoader:
    """Load and manage V2 prompt templates."""

    # Available prompt types
    PROMPT_TYPES = [
        "metric_view_analysis",
        "metadata_analysis",
        "sample_query_analysis",
        "instruction_analysis",
        "answer_comparison",  # Used by benchmark scorer
    ]

    def __init__(self, prompts_dir: Path = None):
        """
        Initialize prompt loader.

        Args:
            prompts_dir: Path to prompts directory. If None, uses current file's directory.
        """
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent
        self.prompts_dir = Path(prompts_dir)
        self._cache = {}

    def load(self, prompt_name: str) -> str:
        """
        Load prompt template from file.

        Args:
            prompt_name: Name of prompt file (without .txt extension)

        Returns:
            Prompt template content
        """
        if prompt_name not in self._cache:
            file_path = self.prompts_dir / f"{prompt_name}.txt"
            if not file_path.exists():
                raise FileNotFoundError(f"Prompt file not found: {file_path}")
            self._cache[prompt_name] = file_path.read_text(encoding='utf-8')
        return self._cache[prompt_name]

    def load_all_analysis_prompts(self) -> Dict[str, str]:
        """
        Load all 4 analysis prompts.

        Returns:
            {
                "metric_view": "...",
                "metadata": "...",
                "sample_query": "...",
                "instruction": "..."
            }
        """
        return {
            "metric_view": self.load("metric_view_analysis"),
            "metadata": self.load("metadata_analysis"),
            "sample_query": self.load("sample_query_analysis"),
            "instruction": self.load("instruction_analysis"),
        }

    def format_answer_comparison_prompt(
        self,
        question: str,
        expected_result: str,
        genie_result: str
    ) -> str:
        """
        Format answer comparison prompt for scoring.

        Args:
            question: The question being evaluated
            expected_result: Expected answer/result
            genie_result: Genie's actual answer/result

        Returns:
            Formatted prompt ready for LLM
        """
        template = self.load("answer_comparison")

        return template.format(
            question=question,
            expected_result=self._format_result(expected_result),
            genie_result=self._format_result(genie_result)
        )

    def _format_result(self, result) -> str:
        """Format query result for display in prompt."""
        if isinstance(result, (dict, list)):
            return json.dumps(result, indent=2, ensure_ascii=False)
        return str(result)

    def clear_cache(self):
        """Clear the cached prompts."""
        self._cache.clear()


# Example usage
if __name__ == "__main__":
    loader = PromptLoader()

    print("Loading V2 prompts...")
    prompts = loader.load_all_analysis_prompts()

    for name, content in prompts.items():
        print(f"  {name}: {len(content)} characters")

    print("\n✅ All V2 prompts loaded successfully")
