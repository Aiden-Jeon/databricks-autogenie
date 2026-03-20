"""Benchmark validation utilities."""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class ValidationError:
    """Represents a validation error."""
    field: str
    message: str
    benchmark_index: int = -1


class BenchmarkValidator:
    """Validates benchmark format and content."""

    REQUIRED_FIELDS = ["question"]
    OPTIONAL_FIELDS = ["expected_answer", "expected_sql", "category", "description"]

    @staticmethod
    def validate_benchmarks(data: Any) -> Tuple[bool, List[ValidationError], List[Dict]]:
        """
        Validate benchmark data.

        Args:
            data: Parsed JSON data (should be list of dicts)

        Returns:
            Tuple of (is_valid, errors, benchmarks)
        """
        errors = []

        # Check if data is a list
        if not isinstance(data, list):
            errors.append(ValidationError(
                field="root",
                message="Benchmark file must contain a JSON array of benchmark objects"
            ))
            return False, errors, []

        # Check if empty
        if len(data) == 0:
            errors.append(ValidationError(
                field="root",
                message="Benchmark file is empty. Please provide at least one benchmark."
            ))
            return False, errors, []

        # Validate each benchmark
        valid_benchmarks = []
        for idx, benchmark in enumerate(data):
            benchmark_errors = BenchmarkValidator._validate_single_benchmark(benchmark, idx)
            errors.extend(benchmark_errors)

            if not benchmark_errors:
                valid_benchmarks.append(benchmark)

        # Return validation result
        is_valid = len(errors) == 0
        return is_valid, errors, valid_benchmarks

    @staticmethod
    def _validate_single_benchmark(benchmark: Any, index: int) -> List[ValidationError]:
        """Validate a single benchmark object."""
        errors = []

        # Check if it's a dictionary
        if not isinstance(benchmark, dict):
            errors.append(ValidationError(
                field="benchmark",
                message=f"Benchmark must be an object/dict, not {type(benchmark).__name__}",
                benchmark_index=index
            ))
            return errors

        # Check required fields
        for field in BenchmarkValidator.REQUIRED_FIELDS:
            if field not in benchmark:
                errors.append(ValidationError(
                    field=field,
                    message=f"Missing required field: '{field}'",
                    benchmark_index=index
                ))
            elif not isinstance(benchmark[field], str):
                errors.append(ValidationError(
                    field=field,
                    message=f"Field '{field}' must be a string",
                    benchmark_index=index
                ))
            elif not benchmark[field].strip():
                errors.append(ValidationError(
                    field=field,
                    message=f"Field '{field}' cannot be empty",
                    benchmark_index=index
                ))

        # Validate optional fields if present
        if "expected_answer" in benchmark and not isinstance(benchmark["expected_answer"], str):
            errors.append(ValidationError(
                field="expected_answer",
                message="Field 'expected_answer' must be a string",
                benchmark_index=index
            ))

        if "expected_sql" in benchmark and not isinstance(benchmark["expected_sql"], str):
            errors.append(ValidationError(
                field="expected_sql",
                message="Field 'expected_sql' must be a string",
                benchmark_index=index
            ))

        # Check for unknown fields (warning, not error)
        known_fields = set(BenchmarkValidator.REQUIRED_FIELDS + BenchmarkValidator.OPTIONAL_FIELDS)
        unknown_fields = set(benchmark.keys()) - known_fields
        if unknown_fields:
            # Not adding to errors, just a note
            pass

        return errors

    @staticmethod
    def format_errors(errors: List[ValidationError]) -> str:
        """Format validation errors as a readable string."""
        if not errors:
            return "No errors"

        lines = ["Benchmark Validation Errors:"]
        for error in errors:
            if error.benchmark_index >= 0:
                lines.append(f"  • Benchmark #{error.benchmark_index + 1}: {error.message}")
            else:
                lines.append(f"  • {error.message}")

        return "\n".join(lines)

    @staticmethod
    def get_example_benchmark() -> Dict:
        """Get an example benchmark for reference."""
        return {
            "question": "Show top 10 customers by total revenue",
            "expected_answer": "List of customer names with revenue amounts, sorted descending",
            "expected_sql": "SELECT customer_name, SUM(amount) as revenue FROM orders GROUP BY customer_name ORDER BY revenue DESC LIMIT 10",
            "category": "aggregation",
            "description": "Tests ability to aggregate data and sort results"
        }

    @staticmethod
    def get_template() -> List[Dict]:
        """Get a benchmark template with examples."""
        return [
            {
                "question": "Show top 10 customers by total revenue",
                "expected_answer": "List of customer names with revenue amounts",
                "category": "aggregation"
            },
            {
                "question": "What was the revenue growth rate last quarter?",
                "expected_answer": "Percentage growth compared to previous quarter",
                "category": "calculation"
            },
            {
                "question": "List all products that are out of stock",
                "expected_answer": "Product names where inventory is zero",
                "category": "filtering"
            }
        ]
