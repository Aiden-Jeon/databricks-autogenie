"""
Feedback Parser for Genie Space Assessment Results

Parses raw feedback files containing questions, SQL queries, assessments,
and ground truth comparisons from Genie Space evaluations.
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class FeedbackEntry:
    """Represents a single feedback entry from Genie Space assessment"""
    
    question: str
    assessment: str  # "Good" or "Bad"
    score_reasons: List[str] = field(default_factory=list)
    
    # Model response
    model_output_type: str = ""  # "SQL" or "text"
    model_output: str = ""
    empty_result: bool = False
    
    # Failure analysis (for bad assessments)
    failure_reasoning: str = ""
    sql_differences: str = ""
    
    # Ground truth
    ground_truth_sql: str = ""
    
    def __repr__(self) -> str:
        return (
            f"FeedbackEntry(\n"
            f"  question='{self.question[:50]}...',\n"
            f"  assessment='{self.assessment}',\n"
            f"  score_reasons={self.score_reasons},\n"
            f"  model_output_type='{self.model_output_type}',\n"
            f"  empty_result={self.empty_result}\n"
            f")"
        )


class FeedbackParser:
    """Parser for Genie Space feedback files"""
    
    def __init__(self, content: str):
        self.content = content
        self.entries: List[FeedbackEntry] = []
    
    def parse(self) -> List[FeedbackEntry]:
        """Parse the feedback file into structured entries"""
        # Split by entry separator
        raw_entries = self.content.split('\n---\n')
        
        for raw_entry in raw_entries:
            if not raw_entry.strip():
                continue
            
            entry = self._parse_entry(raw_entry)
            if entry:
                self.entries.append(entry)
        
        return self.entries
    
    def _parse_entry(self, raw_entry: str) -> Optional[FeedbackEntry]:
        """Parse a single feedback entry"""
        lines = raw_entry.split('\n')
        
        if not lines:
            return None
        
        entry = FeedbackEntry(question="", assessment="")
        
        # First line is the question
        entry.question = lines[0].strip()
        
        i = 1
        while i < len(lines):
            line = lines[i].strip()
            
            # Assessment
            if line == "Assessment:":
                i += 1
                entry.assessment = lines[i].strip()
                i += 1
                continue
            
            # Score reason
            if line == "Score reason:":
                i += 1
                # Collect all score reasons until "Question" or other section header
                section_headers = ["Question", "Failure analysis", "Response", "Ground truth"]
                while i < len(lines) and lines[i].strip():
                    if lines[i].strip() in section_headers:
                        break
                    entry.score_reasons.append(lines[i].strip())
                    i += 1
                continue
            
            # Question (duplicate)
            if line == "Question":
                i += 1
                # Skip, we already have the question
                i += 1
                continue
            
            # Failure analysis
            if line == "Failure analysis":
                i += 1
                # Parse reasoning
                if i < len(lines) and lines[i].strip() == "Reasoning:":
                    i += 1
                    reasoning_lines = []
                    while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('SQL Differences:'):
                        reasoning_lines.append(lines[i].strip())
                        i += 1
                    entry.failure_reasoning = ' '.join(reasoning_lines)
                
                # Parse SQL differences
                if i < len(lines) and lines[i].strip().startswith('SQL Differences:'):
                    i += 1
                    # Skip "Show diff view"
                    if i < len(lines) and lines[i].strip() == "Show diff view":
                        i += 1
                    diff_lines = []
                    while i < len(lines) and lines[i].strip() and not lines[i].strip() == "Response":
                        diff_lines.append(lines[i].strip())
                        i += 1
                    entry.sql_differences = ' '.join(diff_lines)
                continue
            
            # Response
            if line == "Response":
                i += 1
                # Parse model output
                if i < len(lines):
                    output_header = lines[i].strip()
                    if output_header.startswith("Model output"):
                        # Determine type (SQL or text)
                        if "SQL" in output_header:
                            entry.model_output_type = "SQL"
                        else:
                            entry.model_output_type = "text"
                        i += 1
                        
                        # Collect model output until "Empty result" or "Ground truth"
                        output_lines = []
                        while i < len(lines):
                            line_content = lines[i].strip()
                            if line_content == "Empty result":
                                entry.empty_result = True
                                i += 1
                                # Skip "An empty result was generated."
                                if i < len(lines) and "empty result" in lines[i].lower():
                                    i += 1
                                break
                            if line_content.startswith("Ground truth SQL"):
                                break
                            output_lines.append(lines[i])
                            i += 1
                        
                        entry.model_output = '\n'.join(output_lines).strip()
                continue
            
            # Ground truth SQL
            if line.startswith("Ground truth SQL"):
                i += 1
                # Collect all SQL lines until end or next separator
                sql_lines = []
                while i < len(lines):
                    sql_lines.append(lines[i])
                    i += 1
                
                entry.ground_truth_sql = '\n'.join(sql_lines).strip()
                break
            
            i += 1
        
        return entry if entry.question else None
    
    def get_summary(self) -> Dict[str, any]:
        """Get summary statistics of the feedback"""
        total = len(self.entries)
        good = sum(1 for e in self.entries if e.assessment == "Good")
        bad = sum(1 for e in self.entries if e.assessment == "Bad")
        empty_results = sum(1 for e in self.entries if e.empty_result)
        
        # Count score reasons
        reason_counts = {}
        for entry in self.entries:
            for reason in entry.score_reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        
        return {
            "total_entries": total,
            "good_assessments": good,
            "bad_assessments": bad,
            "empty_results": empty_results,
            "score_reason_counts": reason_counts,
            "success_rate": f"{(good / total * 100):.1f}%" if total > 0 else "N/A"
        }
    
    def get_entries_by_reason(self, reason: str) -> List[FeedbackEntry]:
        """Get all entries with a specific score reason"""
        return [e for e in self.entries if reason in e.score_reasons]
    
    def export_to_dict(self) -> List[Dict]:
        """Export all entries as a list of dictionaries"""
        return [
            {
                "question": e.question,
                "assessment": e.assessment,
                "score_reasons": e.score_reasons,
                "model_output_type": e.model_output_type,
                "model_output": e.model_output,
                "empty_result": e.empty_result,
                "failure_reasoning": e.failure_reasoning,
                "sql_differences": e.sql_differences,
                "ground_truth_sql": e.ground_truth_sql
            }
            for e in self.entries
        ]


def parse_feedback_file(filepath: str) -> FeedbackParser:
    """Parse a feedback file and return the parser with results"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    parser = FeedbackParser(content)
    parser.parse()
    return parser


if __name__ == "__main__":
    # Example usage
    import sys
    import json
    
    if len(sys.argv) < 2:
        print("Usage: python feedback_parser.py <feedback_file.md>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    parser = parse_feedback_file(filepath)
    
    # Print summary
    summary = parser.get_summary()
    print("\n=== Feedback Summary ===")
    print(f"Total Entries: {summary['total_entries']}")
    print(f"Good Assessments: {summary['good_assessments']}")
    print(f"Bad Assessments: {summary['bad_assessments']}")
    print(f"Empty Results: {summary['empty_results']}")
    print(f"Success Rate: {summary['success_rate']}")
    
    print("\n=== Score Reason Breakdown ===")
    for reason, count in sorted(summary['score_reason_counts'].items(), key=lambda x: x[1], reverse=True):
        print(f"{reason}: {count}")
    
    # Export to JSON
    output_file = filepath.replace('.md', '_parsed.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "summary": summary,
            "entries": parser.export_to_dict()
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Parsed data exported to: {output_file}")
