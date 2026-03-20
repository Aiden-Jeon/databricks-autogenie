"""
PDF Parser Module - Image-Based Approach
Converts PDF pages to images using PyMuPDF (no poppler dependency) and sends them to multimodal LLM for interpretation.
"""

import pdfplumber
import json
import logging
import asyncio
import warnings
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from PIL import Image
from contextlib import contextmanager, redirect_stderr
from io import StringIO

# Import PyMuPDF for PDF to image conversion (no poppler dependency)
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

logger = logging.getLogger(__name__)

# Prompt version for cache invalidation (bump when prompt changes)
PROMPT_VERSION = "v2-exhaustive-extraction"

# Suppress pdfplumber font warnings
warnings.filterwarnings('ignore', message='.*Could not get FontBBox.*')
warnings.filterwarnings('ignore', message='.*cannot be parsed as 4 floats.*')

# Suppress pdfminer.six logging warnings
logging.getLogger('pdfminer').setLevel(logging.ERROR)
logging.getLogger('pdfminer.converter').setLevel(logging.ERROR)
logging.getLogger('pdfminer.pdffont').setLevel(logging.ERROR)


@contextmanager
def suppress_stderr():
    """Context manager to suppress stderr output (for pdfplumber font warnings).
    Thread-safe version using StringIO buffer instead of file handle."""
    with redirect_stderr(StringIO()):
        yield


def is_pymupdf_available() -> bool:
    """
    Check if PyMuPDF is available.

    Returns:
        bool: True if PyMuPDF is available, False otherwise
    """
    return PYMUPDF_AVAILABLE


@dataclass
class EmbeddedImage:
    """Metadata for an embedded image extracted from PDF"""
    image: Image.Image
    page_number: int
    image_index: int  # Index of image on the page
    width: int
    height: int
    format: str  # e.g., 'JPEG', 'PNG'
    xref: int  # PyMuPDF cross-reference number


@dataclass
class PDFContent:
    """Raw content extracted from PDF"""
    text_by_page: List[str]
    tables_by_page: List[List[List[str]]]
    images: List[Image.Image]  # Full page images
    embedded_images: List[EmbeddedImage]  # Embedded images from within PDF
    metadata: Dict[str, str]

    def to_dict(self) -> dict:
        # Don't include images in dict representation
        data = asdict(self)
        data['images'] = f"<{len(self.images)} PIL Image objects>"
        data['embedded_images'] = f"<{len(self.embedded_images)} embedded images>"
        return data


class PDFParser:
    """
    Hybrid PDF parser using pdfplumber for extraction and LLM for interpretation.
    Supports two modes: batch (all images at once) and per-page (image by image).
    Per-page mode is 2.21x faster based on benchmarks with async parallel processing.
    """
    
    def __init__(self, llm_client=None, use_images: bool = True, per_page: bool = True, page_cache_manager=None):
        """
        Initialize PDF parser.

        Args:
            llm_client: Optional LLM client for interpretation (DatabricksFoundationModelClient)
            use_images: Whether to extract PDF pages as images (default: True)
            per_page: Whether to process images page-by-page vs all-at-once (default: True)
                     - per_page=True: Process each page separately with async parallel (2.21x faster)
                     - per_page=False: Process all pages in one batch (fewer API calls)
            page_cache_manager: Optional PageCacheManager for per-page caching
        """
        self.llm_client = llm_client
        self.per_page = per_page
        self.page_cache_manager = page_cache_manager

        # Check if PyMuPDF is available when use_images is requested
        if use_images and not is_pymupdf_available():
            logger.warning(
                "PyMuPDF not available - disabling image-based extraction. "
                "To enable image extraction, install PyMuPDF: pip install PyMuPDF"
            )
            self.use_images = False
        else:
            self.use_images = use_images
    
    def _extract_embedded_images(self, pdf_path: str) -> List[EmbeddedImage]:
        """
        Extract embedded images from PDF using PyMuPDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of EmbeddedImage objects with metadata
        """
        embedded_images = []

        if not is_pymupdf_available():
            logger.warning("PyMuPDF not available - cannot extract embedded images")
            return embedded_images

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)

                logger.debug(f"Page {page_num + 1}: Found {len(image_list)} embedded images")

                for img_index, img_info in enumerate(image_list):
                    try:
                        xref = img_info[0]  # Cross-reference number
                        base_image = doc.extract_image(xref)

                        if base_image:
                            image_bytes = base_image["image"]
                            image_ext = base_image["ext"]  # Format like 'png', 'jpeg'

                            # Convert to PIL Image
                            pil_image = Image.open(BytesIO(image_bytes))

                            # Create metadata object
                            embedded_img = EmbeddedImage(
                                image=pil_image,
                                page_number=page_num + 1,
                                image_index=img_index,
                                width=pil_image.width,
                                height=pil_image.height,
                                format=image_ext.upper(),
                                xref=xref
                            )

                            embedded_images.append(embedded_img)
                            logger.debug(f"Extracted image {img_index} from page {page_num + 1}: "
                                       f"{pil_image.width}x{pil_image.height} {image_ext}")

                    except Exception as e:
                        logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {e}")
                        continue

            doc.close()

            logger.info(f"Extracted {len(embedded_images)} embedded images from PDF")

        except Exception as e:
            logger.error(f"Error extracting embedded images: {e}")

        return embedded_images

    def extract_raw_content(self, pdf_path: str) -> PDFContent:
        """
        Extract raw content from PDF (text, tables, and optionally images).

        Args:
            pdf_path: Path to PDF file

        Returns:
            PDFContent with extracted content
        """
        logger.info(f"Extracting content from PDF: {pdf_path}")

        text_by_page = []
        tables_by_page = []
        images = []
        metadata = {}

        try:
            # Extract images if enabled and PyMuPDF is available
            if self.use_images:
                if not is_pymupdf_available():
                    logger.warning(
                        "PyMuPDF not available - falling back to text-only extraction. "
                        "Install PyMuPDF for image-based PDF parsing: pip install PyMuPDF"
                    )
                    # Disable image extraction for this instance
                    self.use_images = False
                else:
                    logger.info("Converting PDF pages to images using PyMuPDF...")
                    try:
                        # Open PDF with PyMuPDF
                        doc = fitz.open(pdf_path)

                        # Convert each page to an image
                        for page_num in range(len(doc)):
                            page = doc[page_num]
                            # Render page to pixmap at 120 DPI
                            # matrix = fitz.Matrix(120/72, 120/72) is the DPI scaling
                            pix = page.get_pixmap(matrix=fitz.Matrix(120/72, 120/72))

                            # Convert pixmap to PIL Image
                            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            images.append(img)

                        doc.close()

                        logger.info(f"Converted {len(images)} pages to images")
                        metadata["num_pages"] = len(images)
                        metadata["file_name"] = Path(pdf_path).name
                    except Exception as e:
                        logger.error(f"Error extracting PDF content: {e}")
                        logger.warning("Falling back to text-only extraction")
                        self.use_images = False
            
            # Also extract text and tables for reference (suppress stderr warnings)
            with suppress_stderr():
                with pdfplumber.open(pdf_path) as pdf:
                    if not self.use_images:
                        metadata = {
                            "num_pages": len(pdf.pages),
                            "file_name": Path(pdf_path).name,
                        }
                    
                    # Extract content from each page
                    for page_num, page in enumerate(pdf.pages, start=1):
                        # Extract text
                        text = page.extract_text()
                        if text:
                            text_by_page.append(text)
                        else:
                            text_by_page.append("")
                        
                        # Extract tables
                        tables = page.extract_tables()
                        if tables:
                            tables_by_page.append(tables)
                        else:
                            tables_by_page.append([])
                        
                        logger.debug(f"Page {page_num}: {len(text) if text else 0} chars, {len(tables)} tables")
        
        except Exception as e:
            logger.error(f"Error extracting PDF content: {e}")
            raise

        # Extract embedded images from PDF
        embedded_images = self._extract_embedded_images(pdf_path)

        logger.info(f"Extracted {len(text_by_page)} pages, "
                   f"{sum(len(t) for t in tables_by_page)} tables, "
                   f"{len(images)} page images, "
                   f"{len(embedded_images)} embedded images")

        return PDFContent(
            text_by_page=text_by_page,
            tables_by_page=tables_by_page,
            images=images,
            embedded_images=embedded_images,
            metadata=metadata
        )
    
    def interpret_with_llm(self, raw_content: PDFContent) -> Dict:
        """
        Use LLM to interpret raw PDF content and extract structured information.
        Uses images if available, otherwise falls back to text.
        For per-page processing, uses async implementation via asyncio.run().
        
        Args:
            raw_content: Raw content extracted from PDF
            
        Returns:
            Dictionary with structured information (questions, tables, queries, metadata)
        """
        if not self.llm_client:
            logger.warning("No LLM client provided, skipping interpretation")
            return self._create_empty_structure()
        
        # If per_page mode is enabled, use async version for better performance
        if self.per_page and raw_content.images and len(raw_content.images) > 1:
            logger.info("Using per-page mode (delegating to async version)")
            return asyncio.run(self.interpret_with_llm_async(raw_content))
        
        logger.info("Interpreting PDF content with LLM (batch mode)")
        
        # Build prompt
        if raw_content.images:
            logger.info(f"Using image-based interpretation with {len(raw_content.images)} images")
            prompt = self._get_image_based_prompt()
            images = raw_content.images
        else:
            logger.info("Using text-based interpretation")
            combined_text = "\n\n---PAGE BREAK---\n\n".join(raw_content.text_by_page)
            tables_json = json.dumps(raw_content.tables_by_page, ensure_ascii=False, indent=2)
            system_prompt = self._get_system_prompt()
            user_prompt = self._get_user_prompt(combined_text, tables_json)
            prompt = f"{system_prompt}\n\n{user_prompt}"
            images = None
        
        try:
            # Call LLM with or without images
            response = self.llm_client.generate(
                prompt=prompt,
                images=images,
                temperature=0.1,
                max_tokens=16000
            )

            # Parse response
            structured_data = self._parse_llm_response(response)

            # Validate structure
            self._validate_structure(structured_data)

            # Log extraction statistics
            llm_table_count = len(structured_data.get('tables', []))
            logger.info(f"LLM interpretation complete: {len(structured_data.get('questions', []))} questions, "
                       f"{llm_table_count} tables")

            # Compare with pdfplumber tables (validation check)
            if raw_content.tables_by_page:
                pdfplumber_table_count = sum(len(page_tables) for page_tables in raw_content.tables_by_page)
                if pdfplumber_table_count > 0:
                    logger.info(f"Table extraction comparison: pdfplumber found {pdfplumber_table_count} tables, "
                               f"LLM extracted {llm_table_count} table definitions")
                    if llm_table_count < pdfplumber_table_count:
                        logger.warning(f"LLM may have missed tables: {pdfplumber_table_count - llm_table_count} "
                                      f"more tables detected by pdfplumber")

            return structured_data

        except Exception as e:
            logger.error(f"Error during LLM interpretation: {e}")
            raise
    
    def _get_image_based_prompt(self) -> str:
        """Enhanced prompt for comprehensive extraction (concise version)"""
        return """Extract structured information from these technical document pages as JSON.

EXTRACT:
1. Questions: id, text, category (KPI/Social/Sentiment/Trend/Comparison/Regional/Other), tables_needed
2. Tables: full_name, description, key_columns, related_kpi, table_remarks (special notes)
3. SQL Queries: question_id, query (EXACT formatting), description, aggregation_patterns, filtering_rules, join_specs
4. Joins: left_table, right_table, join_type, join_condition, is_optional
5. Metadata: document_title, domain

CRITICAL - TABLE EXTRACTION RULES:
- Extract ALL tables mentioned in the document - be exhaustive and complete
- Do not skip or omit any table, even if it seems minor or is only referenced briefly
- If a table is mentioned multiple times, capture all unique column information from all mentions
- Extract complete column schemas - do not truncate or limit the number of columns
- If unsure whether something is a table, include it - better to over-extract than miss tables
- At the end of extraction, count the total tables found and include this in metadata

KEY INSTRUCTIONS:
- Preserve exact SQL formatting and indentation
- Mark columns as "optional" if marked "선택적" or "(optional)"
- Extract aggregation patterns: ["COALESCE", "CTE", "UNION_ALL", "window_function", "try_divide"]
- Extract filtering rules from WHERE clauses (e.g., "event_date >= DATE '2025-07-26'")
- Extract join relationships with exact conditions
- Capture table remarks: special notes about capabilities, constraints, platform restrictions
- Distinguish column usage: event_date (filtering) vs created_at (display/sorting)
- Note transformation rules: FROM_UNIXTIME for Steam timestamps

JSON SCHEMA:
{
  "questions": [{
    "id": "Q1",
    "text": "question (preserve Korean/English)",
    "category": "KPI/Social/...",
    "tables_needed": ["catalog.schema.table"]
  }],
  "tables": [{
    "full_name": "catalog.schema.table",
    "description": "brief description",
    "key_columns": [
      {"name": "col1", "data_type": "bigint", "is_required": true, "usage_type": "join_key"},
      {"name": "event_date", "data_type": "date", "is_required": true, "usage_type": "filtering", "transformation_rule": "partition column"},
      {"name": "created_at", "data_type": "timestamp", "is_required": false, "usage_type": "display"}
    ],
    "related_kpi": "DAU/ARPU/null",
    "table_remarks": ["week_start_day specification required", "PUBG Only"]
  }],
  "sql_queries": [{
    "question_id": "Q1",
    "query": "SELECT ... (exact SQL with formatting)",
    "description": "what this answers",
    "aggregation_patterns": ["COALESCE", "CTE"],
    "filtering_rules": ["event_date >= DATE '2025-07-26'", "product_category = 'electronics'"],
    "join_specs": ["LEFT JOIN reaction ON message.message_id = reaction.message_id (required)", "LEFT JOIN channel_list ON message.channel_id = channel_list.channel_id (optional)"]
  }],
  "join_specifications": [{
    "left_table": "main.log_discord.message",
    "right_table": "main.log_discord.reaction",
    "join_type": "LEFT",
    "join_condition": "message.message_id = reaction.message_id",
    "is_optional": false
  }],
  "metadata": {
    "document_title": "extracted title",
    "domain": "social_analytics/kpi_analytics/combined"
  }
}

Return ONLY valid JSON, no markdown blocks."""
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM interpretation"""
        return """You are an expert at extracting structured information from technical documents.
You will receive raw text and tables extracted from a PDF document.
Your task is to identify and structure:
1. Questions/requirements
2. Table schemas and descriptions
3. SQL queries
4. Metadata and relationships

Return your response as valid JSON only, with no additional text."""
    
    def _get_user_prompt(self, text: str, tables_json: str) -> str:
        """Get user prompt for LLM interpretation"""
        # Increased limits to reduce risk of truncation (20k->50k, 5k->20k)
        text_limit = 50000
        tables_limit = 20000

        # Log if truncation occurs
        if len(text) > text_limit:
            logger.warning(f"Text content truncated: {len(text)} chars -> {text_limit} chars")
        if len(tables_json) > tables_limit:
            logger.warning(f"Tables JSON truncated: {len(tables_json)} chars -> {tables_limit} chars")

        return f"""PDF Content:
{text[:text_limit]}

Extracted Tables:
{tables_json[:tables_limit]}  

Extract and structure this information as JSON:
{{
  "questions": [
    {{
      "id": "Q1",
      "text": "question text in Korean or English",
      "category": "KPI/Social/Sentiment/Trend/Comparison/Regional/Other",
      "tables_needed": ["catalog.schema.table"]
    }}
  ],
  "tables": [
    {{
      "full_name": "catalog.schema.table",
      "description": "brief description",
      "key_columns": ["col1", "col2"],
      "related_kpi": "DAU/ARPU/etc or null"
    }}
  ],
  "sql_queries": [
    {{
      "question_id": "Q1",
      "query": "SELECT ... (preserve exact SQL formatting)",
      "description": "what this query does"
    }}
  ],
  "metadata": {{
    "document_title": "extracted title",
    "domain": "social_analytics/kpi_analytics/combined"
  }}
}}

Important:
- Preserve Korean text exactly as written
- Keep SQL queries with original formatting and indentation
- Identify table relationships from JOIN clauses
- Return ONLY valid JSON, no markdown code blocks"""
    
    def _parse_llm_response(self, response: str) -> Dict:
        """Parse LLM response into structured data"""
        try:
            # Try to extract JSON from response
            # Handle cases where LLM might wrap in markdown code blocks
            response_clean = response.strip()
            
            # Remove markdown code blocks if present
            if response_clean.startswith("```json"):
                response_clean = response_clean[7:]
            elif response_clean.startswith("```"):
                response_clean = response_clean[3:]
            
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            
            # Parse JSON
            structured_data = json.loads(response_clean.strip())
            return structured_data
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response: {response[:500]}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")
    
    def _validate_structure(self, data: Dict) -> None:
        """Validate the structure of interpreted data"""
        required_keys = ["questions", "tables", "sql_queries", "metadata"]
        
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Missing required key in LLM response: {key}")
        
        # Validate questions
        if not isinstance(data["questions"], list):
            raise ValueError("'questions' must be a list")
        
        # Validate tables
        if not isinstance(data["tables"], list):
            raise ValueError("'tables' must be a list")
        
        # Validate queries
        if not isinstance(data["sql_queries"], list):
            raise ValueError("'sql_queries' must be a list")
        
        logger.debug("Structure validation passed")
    
    def _create_empty_structure(self) -> Dict:
        """Create empty structure when LLM is not available"""
        return {
            "questions": [],
            "tables": [],
            "sql_queries": [],
            "metadata": {
                "document_title": "Unknown",
                "domain": "unknown"
            }
        }
    
    def parse_pdf(self, pdf_path: str, use_llm: bool = True) -> Dict:
        """
        Full pipeline: extract raw content and optionally interpret with LLM.
        
        Args:
            pdf_path: Path to PDF file
            use_llm: Whether to use LLM for interpretation
            
        Returns:
            Dictionary with structured information
        """
        # Step 1: Extract raw content
        raw_content = self.extract_raw_content(pdf_path)
        
        # Step 2: Interpret with LLM (optional)
        if use_llm and self.llm_client:
            structured_data = self.interpret_with_llm(raw_content)
        else:
            structured_data = self._create_empty_structure()
            # Add raw content for manual processing
            structured_data["raw_content"] = raw_content.to_dict()
        
        return structured_data
    
    async def _interpret_single_page_async(
        self,
        image: Image.Image,
        page_num: int,
        pdf_path: Optional[str] = None,
        total_pages: Optional[int] = None
    ) -> Tuple[Dict, bool]:
        """
        Interpret a single PDF page image with LLM (async).

        Args:
            image: Single page image
            page_num: Page number for logging
            pdf_path: Optional PDF path for caching
            total_pages: Optional total page count for caching

        Returns:
            Tuple of (structured data dict, cache_hit boolean)
        """
        logger.debug(f"Processing page {page_num}...")

        # Check cache first
        if self.page_cache_manager and pdf_path and self.llm_client:
            vision_model = getattr(self.llm_client, 'model_name', 'unknown')
            config_hash = self.page_cache_manager._compute_config_hash(vision_model, PROMPT_VERSION)
            cached = self.page_cache_manager.get_cached_page(
                pdf_path, page_num, vision_model, config_hash=config_hash
            )
            if cached:
                logger.debug(f"Cache HIT for page {page_num}")
                return cached['page_data'], True  # Cache HIT

        # Create PDFContent with just this one image
        single_page_content = PDFContent(
            text_by_page=[],
            tables_by_page=[],
            images=[image],
            embedded_images=[],  # Single page processing doesn't extract embedded images
            metadata={"page": page_num}
        )

        # Use standard interpretation
        prompt = self._get_image_based_prompt()

        try:
            response = await self.llm_client.generate_async(
                prompt=prompt,
                images=[image],
                temperature=0.1,
                max_tokens=16000
            )

            structured_data = self._parse_llm_response(response)
            self._validate_structure(structured_data)

            # Save to cache
            if self.page_cache_manager and pdf_path and self.llm_client:
                vision_model = getattr(self.llm_client, 'model_name', 'unknown')
                config_hash = self.page_cache_manager._compute_config_hash(vision_model, PROMPT_VERSION)
                self.page_cache_manager.save_page_result(
                    pdf_path, page_num, structured_data, total_pages or page_num, vision_model, config_hash=config_hash
                )

            return structured_data, False  # Cache MISS

        except Exception as e:
            logger.error(f"Error processing page {page_num}: {e}")
            # Return empty structure for failed pages
            return self._create_empty_structure(), False
    
    def _merge_page_results(self, page_results: List[Tuple[Dict, bool]]) -> Dict:
        """
        Merge results from multiple single-page interpretations.

        Args:
            page_results: List of (result_dict, cache_hit) tuples from individual pages

        Returns:
            Combined results dictionary
        """
        merged = {
            "questions": [],
            "tables": [],
            "sql_queries": [],
            "metadata": {}
        }

        # Collect unique questions (by ID)
        question_ids = set()
        for page_result, _ in page_results:
            for q in page_result.get("questions", []):
                q_id = q.get("id")
                if q_id and q_id not in question_ids:
                    merged["questions"].append(q)
                    question_ids.add(q_id)

        # Collect unique tables (by full_name)
        table_names = set()
        for page_result, _ in page_results:
            for t in page_result.get("tables", []):
                t_name = t.get("full_name")
                if t_name and t_name not in table_names:
                    merged["tables"].append(t)
                    table_names.add(t_name)

        # Collect all SQL queries
        for page_result, _ in page_results:
            merged["sql_queries"].extend(page_result.get("sql_queries", []))

        # Merge metadata from first page
        if page_results:
            merged["metadata"] = page_results[0][0].get("metadata", {})

        logger.info(f"Merged results: {len(merged['questions'])} questions, "
                   f"{len(merged['tables'])} tables, {len(merged['sql_queries'])} queries")

        return merged
    
    async def interpret_with_llm_async(self, raw_content: PDFContent, pdf_path: Optional[str] = None) -> Dict:
        """
        Async version of interpret_with_llm.
        Uses LLM to interpret raw PDF content and extract structured information.
        Supports both per-page and batch processing modes.

        Args:
            raw_content: Raw content extracted from PDF
            pdf_path: Optional PDF path for caching

        Returns:
            Dictionary with structured information (questions, tables, queries, metadata)
        """
        if not self.llm_client:
            logger.warning("No LLM client provided, skipping interpretation")
            return self._create_empty_structure()

        # Check if we should use per-page processing
        if self.per_page and raw_content.images and len(raw_content.images) > 1:
            logger.info(f"Using per-page interpretation with {len(raw_content.images)} images (async parallel)")
            total_pages = len(raw_content.images)

            try:
                # Process all pages in parallel
                tasks = [
                    self._interpret_single_page_async(img, idx + 1, pdf_path, total_pages)
                    for idx, img in enumerate(raw_content.images)
                ]

                page_results = await asyncio.gather(*tasks)

                # Calculate cache statistics
                cache_hits = sum(1 for _, is_hit in page_results if is_hit)
                cache_hit_rate = cache_hits / total_pages if total_pages > 0 else 0.0

                logger.info(f"Cache statistics: {cache_hits}/{total_pages} pages cached ({cache_hit_rate:.1%})")

                # Merge results
                merged_result = self._merge_page_results(page_results)

                logger.info(f"Per-page interpretation complete: {len(merged_result['questions'])} questions, "
                           f"{len(merged_result['tables'])} tables")

                return merged_result

            except Exception as e:
                logger.error(f"Error during per-page interpretation: {e}")
                raise
        
        # Fall back to batch processing
        logger.info("Interpreting PDF content with LLM (async, batch mode)")
        
        # Build prompt
        if raw_content.images:
            logger.info(f"Using image-based interpretation with {len(raw_content.images)} images")
            prompt = self._get_image_based_prompt()
            images = raw_content.images
        else:
            logger.info("Using text-based interpretation")
            combined_text = "\n\n---PAGE BREAK---\n\n".join(raw_content.text_by_page)
            tables_json = json.dumps(raw_content.tables_by_page, ensure_ascii=False, indent=2)
            system_prompt = self._get_system_prompt()
            user_prompt = self._get_user_prompt(combined_text, tables_json)
            prompt = f"{system_prompt}\n\n{user_prompt}"
            images = None
        
        try:
            # Call LLM with or without images (async)
            response = await self.llm_client.generate_async(
                prompt=prompt,
                images=images,
                temperature=0.1,
                max_tokens=16000
            )

            # Parse response
            structured_data = self._parse_llm_response(response)

            # Validate structure
            self._validate_structure(structured_data)

            # Log extraction statistics
            llm_table_count = len(structured_data.get('tables', []))
            logger.info(f"LLM interpretation complete: {len(structured_data.get('questions', []))} questions, "
                       f"{llm_table_count} tables")

            # Compare with pdfplumber tables (validation check)
            if raw_content.tables_by_page:
                pdfplumber_table_count = sum(len(page_tables) for page_tables in raw_content.tables_by_page)
                if pdfplumber_table_count > 0:
                    logger.info(f"Table extraction comparison: pdfplumber found {pdfplumber_table_count} tables, "
                               f"LLM extracted {llm_table_count} table definitions")
                    if llm_table_count < pdfplumber_table_count:
                        logger.warning(f"LLM may have missed tables: {pdfplumber_table_count - llm_table_count} "
                                      f"more tables detected by pdfplumber")

            return structured_data

        except Exception as e:
            logger.error(f"Error during LLM interpretation: {e}")
            raise
    
    async def parse_pdf_async(self, pdf_path: str, use_llm: bool = True) -> Dict:
        """
        Async version of parse_pdf.
        Full pipeline: extract raw content and optionally interpret with LLM.

        Args:
            pdf_path: Path to PDF file
            use_llm: Whether to use LLM for interpretation

        Returns:
            Dictionary with structured information
        """
        # Step 1: Extract raw content (run in executor since it's CPU-bound)
        loop = asyncio.get_event_loop()
        raw_content = await loop.run_in_executor(None, self.extract_raw_content, pdf_path)

        # Step 2: Interpret with LLM (optional)
        if use_llm and self.llm_client:
            structured_data = await self.interpret_with_llm_async(raw_content, pdf_path)
        else:
            structured_data = self._create_empty_structure()
            # Add raw content for manual processing
            structured_data["raw_content"] = raw_content.to_dict()

        return structured_data


def extract_pdf(pdf_path: str, llm_client=None, use_llm: bool = True) -> Dict:
    """
    Convenience function to extract content from a PDF.
    
    Args:
        pdf_path: Path to PDF file
        llm_client: Optional LLM client for interpretation
        use_llm: Whether to use LLM for interpretation
        
    Returns:
        Dictionary with structured information
    """
    parser = PDFParser(llm_client=llm_client)
    return parser.parse_pdf(pdf_path, use_llm=use_llm)
