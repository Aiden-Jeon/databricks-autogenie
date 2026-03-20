"""Per-page caching system for PDF parsing."""

import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime


class PageCacheManager:
    """Manages per-page caching for PDF parsing."""

    VERSION = "1.0"

    def __init__(self, cache_dir: str = ".parse_page_cache"):
        """
        Initialize page cache manager.

        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = Path(cache_dir)
        self.pages_dir = self.cache_dir / "pages"
        self.index_file = self.cache_dir / "index.json"

        # Ensure directories exist
        self.pages_dir.mkdir(parents=True, exist_ok=True)

        # Load or initialize index
        self.index = self._load_index()

    def _load_index(self) -> Dict:
        """Load cache index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {"version": self.VERSION, "pdfs": {}}
        return {"version": self.VERSION, "pdfs": {}}

    def _save_index(self):
        """Save cache index to disk."""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, indent=2, ensure_ascii=False)

    def _compute_pdf_hash(self, pdf_path: str) -> str:
        """
        Generate hash from path + mtime + size.

        Args:
            pdf_path: Path to PDF file

        Returns:
            16-character hash string
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        stat = path.stat()
        key = f"{pdf_path}:{stat.st_mtime}:{stat.st_size}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _compute_config_hash(self, vision_model: str, prompt_version: str = "v1") -> str:
        """
        Generate hash from vision model and prompt configuration.

        Args:
            vision_model: Vision model name
            prompt_version: Prompt version identifier

        Returns:
            8-character hash string
        """
        key = f"{vision_model}:{prompt_version}"
        return hashlib.sha256(key.encode()).hexdigest()[:8]

    def get_cached_page(
        self,
        pdf_path: str,
        page_num: int,
        vision_model: str,
        config_hash: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Retrieve cached page if valid.

        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-indexed)
            vision_model: Vision model used for parsing
            config_hash: Optional config hash (will be computed if not provided)

        Returns:
            Cached page data if valid, None otherwise
        """
        try:
            pdf_hash = self._compute_pdf_hash(pdf_path)
            if config_hash is None:
                config_hash = self._compute_config_hash(vision_model)

            # Check if PDF is in index
            pdf_key = f"{pdf_hash}:{config_hash}"
            if pdf_key not in self.index["pdfs"]:
                return None

            pdf_meta = self.index["pdfs"][pdf_key]

            # Check if page exists in cache
            page_file = self.pages_dir / f"{pdf_hash}_{config_hash}_{page_num:03d}.json"
            if not page_file.exists():
                return None

            # Load cached page
            with open(page_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)

            # Validate cache version
            if cached.get("version") != self.VERSION:
                return None

            # Validate vision model
            if cached.get("vision_model") != vision_model:
                return None

            return cached

        except Exception:
            return None

    def save_page_result(
        self,
        pdf_path: str,
        page_num: int,
        result_data: Dict,
        total_pages: int,
        vision_model: str,
        config_hash: Optional[str] = None
    ):
        """
        Save page result to cache.

        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-indexed)
            result_data: Parsed data for this page
            total_pages: Total number of pages in PDF
            vision_model: Vision model used for parsing
            config_hash: Optional config hash (will be computed if not provided)
        """
        try:
            pdf_hash = self._compute_pdf_hash(pdf_path)
            if config_hash is None:
                config_hash = self._compute_config_hash(vision_model)

            # Update index
            pdf_key = f"{pdf_hash}:{config_hash}"
            if pdf_key not in self.index["pdfs"]:
                self.index["pdfs"][pdf_key] = {
                    "pdf_path": str(pdf_path),
                    "pdf_hash": pdf_hash,
                    "config_hash": config_hash,
                    "vision_model": vision_model,
                    "total_pages": total_pages,
                    "cached_pages": [],
                    "last_updated": datetime.now().isoformat()
                }

            pdf_meta = self.index["pdfs"][pdf_key]
            if page_num not in pdf_meta["cached_pages"]:
                pdf_meta["cached_pages"].append(page_num)
                pdf_meta["cached_pages"].sort()
            pdf_meta["last_updated"] = datetime.now().isoformat()

            # Save page data
            page_file = self.pages_dir / f"{pdf_hash}_{config_hash}_{page_num:03d}.json"
            cache_entry = {
                "version": self.VERSION,
                "pdf_path": str(pdf_path),
                "page_num": page_num,
                "vision_model": vision_model,
                "config_hash": config_hash,
                "cached_at": datetime.now().isoformat(),
                "page_data": result_data
            }

            with open(page_file, 'w', encoding='utf-8') as f:
                json.dump(cache_entry, f, indent=2, ensure_ascii=False)

            # Save updated index
            self._save_index()

        except Exception as e:
            # Fail silently - caching is optional
            pass

    def get_cache_stats(self, pdf_path: str, vision_model: str) -> Dict:
        """
        Get cache statistics for a PDF.

        Args:
            pdf_path: Path to PDF file
            vision_model: Vision model name

        Returns:
            Dictionary with cache statistics
        """
        try:
            pdf_hash = self._compute_pdf_hash(pdf_path)
            config_hash = self._compute_config_hash(vision_model)
            pdf_key = f"{pdf_hash}:{config_hash}"

            if pdf_key not in self.index["pdfs"]:
                return {
                    "total_pages": 0,
                    "cached_pages": 0,
                    "cache_hit_rate": 0.0,
                    "missing_pages": []
                }

            pdf_meta = self.index["pdfs"][pdf_key]
            total_pages = pdf_meta.get("total_pages", 0)
            cached_pages_list = pdf_meta.get("cached_pages", [])
            cached_count = len(cached_pages_list)

            missing = []
            if total_pages > 0:
                all_pages = set(range(1, total_pages + 1))
                missing = sorted(list(all_pages - set(cached_pages_list)))

            cache_hit_rate = cached_count / total_pages if total_pages > 0 else 0.0

            return {
                "total_pages": total_pages,
                "cached_pages": cached_count,
                "cache_hit_rate": cache_hit_rate,
                "missing_pages": missing
            }

        except Exception:
            return {
                "total_pages": 0,
                "cached_pages": 0,
                "cache_hit_rate": 0.0,
                "missing_pages": []
            }

    def clear_cache(self, pdf_path: Optional[str] = None):
        """
        Clear cache for a specific PDF or all cached data.

        Args:
            pdf_path: Optional path to PDF (clears all if not provided)
        """
        if pdf_path is None:
            # Clear all cache
            for file in self.pages_dir.glob("*.json"):
                file.unlink()
            self.index = {"version": self.VERSION, "pdfs": {}}
            self._save_index()
        else:
            # Clear specific PDF
            try:
                pdf_hash = self._compute_pdf_hash(pdf_path)

                # Remove from index
                keys_to_remove = [k for k in self.index["pdfs"].keys() if k.startswith(pdf_hash)]
                for key in keys_to_remove:
                    del self.index["pdfs"][key]

                # Remove page files
                for file in self.pages_dir.glob(f"{pdf_hash}_*.json"):
                    file.unlink()

                self._save_index()
            except Exception:
                pass
