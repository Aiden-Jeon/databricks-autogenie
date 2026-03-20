"""
Genie Enhancement Library v3.0

Batch-oriented enhancement with 4-stage Databricks Job support.

Modules:
- genie_client: Genie Conversational API
- space_api: Genie Space import/export
- scorer: Benchmark scoring with LLM judge
- enhancer: Fix generation (batch)
- applier: Fix application (batch)
- llm: Databricks LLM client
- sql: SQL executor
- state: Job state management (Delta tables)
"""

from enhancer.api.genie_client import GenieConversationalClient
from enhancer.api.space_api import SpaceUpdater
from enhancer.scoring.scorer import BenchmarkScorer
from enhancer.scoring.benchmark_parser import BenchmarkParser, BenchmarkLoader
from enhancer.llm.llm import DatabricksLLMClient
from enhancer.utils.sql import SQLExecutor
from enhancer.enhancement.enhancer import EnhancementPlanner
from enhancer.enhancement.applier import BatchApplier
from enhancer.utils.state import JobState, get_job_state
from enhancer.utils.reporter import ProgressReporter
from enhancer.api.space_cloner import SpaceCloner
from enhancer.enhancement.sequential_enhancer import SequentialEnhancer

__all__ = [
    # API Clients
    "GenieConversationalClient",
    "SpaceUpdater",
    "DatabricksLLMClient",
    "SQLExecutor",
    # Scoring
    "BenchmarkScorer",
    "BenchmarkParser",
    "BenchmarkLoader",
    # Enhancement (Batch)
    "EnhancementPlanner",
    "BatchApplier",
    # Enhancement (Sequential)
    "SpaceCloner",
    "SequentialEnhancer",
    # State & Reporting
    "JobState",
    "get_job_state",
    "ProgressReporter",
]

__version__ = "3.0.0"
