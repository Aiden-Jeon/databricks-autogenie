"""
Parsing module for requirements conversion pipeline.

This module provides tools for extracting, structuring, and generating
requirements documentation from various sources (PDFs, markdown).
"""

from .pdf_parser import PDFParser, extract_pdf
from .markdown_parser import MarkdownParser, parse_markdown_file, parse_markdown_directory
from .requirements_structurer import (
    RequirementsStructurer,
    RequirementsDocument,
    Question,
    TableInfo,
    SQLQuery,
    structure_requirements
)
from .llm_enricher import LLMEnricher, enrich_requirements
from .markdown_generator import MarkdownGenerator, generate_markdown

__all__ = [
    # PDF parsing
    'PDFParser',
    'extract_pdf',
    
    # Markdown parsing
    'MarkdownParser',
    'parse_markdown_file',
    'parse_markdown_directory',
    
    # Structuring
    'RequirementsStructurer',
    'RequirementsDocument',
    'Question',
    'TableInfo',
    'SQLQuery',
    'structure_requirements',
    
    # Enrichment
    'LLMEnricher',
    'enrich_requirements',
    
    # Generation
    'MarkdownGenerator',
    'generate_markdown',
]
