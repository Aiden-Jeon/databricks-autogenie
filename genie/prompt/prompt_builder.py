"""Build prompts for LLM to generate Genie space configurations."""

from pathlib import Path
from typing import Optional
from genie.extractor.domain_extractor import DomainKnowledge


class PromptBuilder:
    """Builds prompts for generating Genie space configurations."""

    def __init__(
        self,
        context_doc_path: str,
        output_doc_path: str,
        input_data_path: str,
        workspace_root: Optional[str] = None,
        domain_patterns_path: Optional[str] = None
    ):
        """
        Initialize the prompt builder.

        Args:
            context_doc_path: Path to the context document (curate_effective_genie.md)
            output_doc_path: Path to the output format document (genie_api.md)
            input_data_path: Path to the input data (demo_requirements.md)
            workspace_root: Root directory of the workspace (defaults to current directory)
            domain_patterns_path: Optional path to domain-specific patterns file
                                  (e.g., domain_patterns/your_domain.md)
        """
        if workspace_root is None:
            workspace_root = Path.cwd()
        else:
            workspace_root = Path(workspace_root)

        self.context_doc_path = workspace_root / context_doc_path
        self.output_doc_path = workspace_root / output_doc_path
        self.input_data_path = workspace_root / input_data_path

        # Set optional domain patterns path
        if domain_patterns_path:
            self.domain_patterns_path = workspace_root / domain_patterns_path
        else:
            self.domain_patterns_path = None

        # Set path to template file
        templates_dir = Path(__file__).parent / "templates"
        self.guide_prompt_path = templates_dir / "guide_prompt_with_reasoning.md"

    def _read_file(self, path: Path) -> str:
        """Read file contents."""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def build_prompt(self, domain_knowledge: Optional[DomainKnowledge] = None) -> str:
        """
        Build the complete prompt for the LLM with reasoning support.

        Args:
            domain_knowledge: Optional extracted domain knowledge to inject into prompt

        Returns:
            The formatted prompt string
        """
        # Read all documents
        context_content = self._read_file(self.context_doc_path)
        output_content = self._read_file(self.output_doc_path)
        input_content = self._read_file(self.input_data_path)

        # Inject domain patterns if provided
        if self.domain_patterns_path and self.domain_patterns_path.exists():
            domain_patterns = self._read_file(self.domain_patterns_path)
            context_content = f"{context_content}\n\n{'=' * 60}\n\n## Domain-Specific Patterns\n\n{domain_patterns}"

        # Inject domain knowledge if provided
        if domain_knowledge:
            domain_context = domain_knowledge.to_structured_context()
            if domain_context:
                # Insert domain knowledge before the input content
                input_content = f"{domain_context}\n\n{'=' * 60}\n\n{input_content}"

        # Read the guide prompt template
        guide_template = self._read_file(self.guide_prompt_path)

        # Format the template with the content
        prompt = guide_template.format(
            context_content=context_content,
            output_content=output_content,
            input_content=input_content
        )

        return prompt
