"""
Benchmark Parser for Genie Enhancement System

Parses markdown benchmark files and converts them to JSON format
for use with the benchmark scorer.
"""

import re
import json
import uuid
from pathlib import Path
from typing import List, Dict


class BenchmarkParser:
    """Parse markdown benchmark files into structured JSON."""

    def __init__(self):
        self.benchmarks = []

    def parse_file(self, file_path: str) -> List[Dict]:
        """
        Parse a single markdown benchmark file.

        Args:
            file_path: Path to markdown file

        Returns:
            List of benchmark dictionaries
        """
        content = Path(file_path).read_text(encoding='utf-8')
        file_name = Path(file_path).name

        # Split into question sections (## N. pattern)
        question_pattern = r'##\s+(\d+)\.\s+(.+?)(?=##\s+\d+\.|$)'
        sections = re.findall(question_pattern, content, re.DOTALL)

        benchmarks = []

        for question_num, section_content in sections:
            benchmark = self._parse_question_section(
                question_num,
                section_content,
                file_name
            )
            if benchmark:
                benchmarks.append(benchmark)

        return benchmarks

    def _parse_question_section(self,
                                 question_num: str,
                                 content: str,
                                 source_file: str) -> Dict:
        """
        Parse a single question section.

        Args:
            question_num: Question number
            content: Section content
            source_file: Source filename

        Returns:
            Benchmark dictionary or None if parsing fails
        """
        # Extract Korean question (first line after heading)
        korean_match = re.search(r'^(.+?)\s*✅?$', content.strip(), re.MULTILINE)
        korean_question = korean_match.group(1).strip() if korean_match else ""

        # Extract English question
        english_match = re.search(r'\*\*Question:\*\*\s*(.+?)(?=\n|$)', content)
        if not english_match:
            print(f"Warning: No English question found for question {question_num}")
            return None
        english_question = english_match.group(1).strip()

        # Extract SQL query (everything between ```sql and ```)
        sql_match = re.search(r'```sql\s*\n(.*?)\n```', content, re.DOTALL)
        if not sql_match:
            print(f"Warning: No SQL found for question {question_num}")
            return None
        sql_query = sql_match.group(1).strip()

        # Generate UUID for benchmark
        benchmark_id = uuid.uuid4().hex

        return {
            "id": benchmark_id,
            "question": english_question,
            "expected_sql": sql_query,
            "korean_question": korean_question,
            "source_file": source_file,
            "question_number": int(question_num)
        }

    def parse_directory(self, directory_path: str) -> List[Dict]:
        """
        Parse all markdown files in a directory.

        Args:
            directory_path: Path to directory containing benchmark files

        Returns:
            List of all benchmarks from all files
        """
        directory = Path(directory_path)
        all_benchmarks = []

        # Find all .md files
        md_files = sorted(directory.glob("*.md"))

        for md_file in md_files:
            print(f"Parsing {md_file.name}...")
            benchmarks = self.parse_file(str(md_file))
            all_benchmarks.extend(benchmarks)
            print(f"  Found {len(benchmarks)} benchmarks")

        return all_benchmarks

    def save_to_json(self, benchmarks: List[Dict], output_path: str):
        """
        Save benchmarks to JSON file.

        Args:
            benchmarks: List of benchmark dictionaries
            output_path: Path to output JSON file
        """
        output_data = {
            "benchmarks": benchmarks,
            "metadata": {
                "total_count": len(benchmarks),
                "source_files": list(set(b["source_file"] for b in benchmarks))
            }
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        print(f"\nSaved {len(benchmarks)} benchmarks to {output_path}")


class BenchmarkLoader:
    """Load benchmarks from JSON file for use in benchmark scorer."""

    def __init__(self, json_path: str):
        """
        Initialize loader.

        Args:
            json_path: Path to benchmarks JSON file
        """
        self.json_path = json_path
        self._data = None

    def load(self) -> List[Dict]:
        """
        Load benchmarks from JSON file.

        Returns:
            List of benchmark dictionaries
        """
        if self._data is None:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)

        return self._data["benchmarks"]

    def filter_by_source(self, source_file: str) -> List[Dict]:
        """
        Filter benchmarks by source file.

        Args:
            source_file: Source filename to filter by

        Returns:
            Filtered list of benchmarks
        """
        benchmarks = self.load()
        return [b for b in benchmarks if b["source_file"] == source_file]

    def get_benchmark_by_id(self, benchmark_id: str) -> Dict:
        """
        Get a specific benchmark by ID.

        Args:
            benchmark_id: Benchmark UUID

        Returns:
            Benchmark dictionary or None if not found
        """
        benchmarks = self.load()
        for benchmark in benchmarks:
            if benchmark["id"] == benchmark_id:
                return benchmark
        return None


def main():
    """
    Main function for CLI usage.

    Usage:
        python benchmark_parser.py
    """
    # Parse benchmarks directory
    parser = BenchmarkParser()

    benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
    output_file = Path(__file__).parent.parent / "benchmarks" / "benchmarks.json"

    print(f"Parsing benchmarks from: {benchmarks_dir}")
    print("-" * 60)

    all_benchmarks = parser.parse_directory(str(benchmarks_dir))

    print("-" * 60)
    print(f"Total benchmarks parsed: {len(all_benchmarks)}")

    # Save to JSON
    parser.save_to_json(all_benchmarks, str(output_file))

    # Print summary
    print("\nSummary by source file:")
    by_source = {}
    for b in all_benchmarks:
        source = b["source_file"]
        by_source[source] = by_source.get(source, 0) + 1

    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count} benchmarks")

    print("\nSample benchmark:")
    print(json.dumps(all_benchmarks[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
