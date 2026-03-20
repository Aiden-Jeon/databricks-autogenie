"""Parse cache manager for tracking document parsing state."""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone


class ParseCacheManager:
    """
    Manages caching metadata for document parsing to avoid expensive re-parsing.
    
    Tracks:
    - Input file modification times and sizes
    - Output file modification time
    - Parsing configuration (models, settings)
    - Timestamp of last successful parse
    """
    
    VERSION = "1.0"
    
    def __init__(self, cache_file: str = ".parse_cache.json"):
        """
        Initialize cache manager.
        
        Args:
            cache_file: Path to cache metadata file (default: .parse_cache.json)
        """
        self.cache_file = Path(cache_file)
        self.cache_data: Optional[Dict[str, Any]] = None
    
    def load(self) -> bool:
        """
        Load cache metadata from file.
        
        Returns:
            True if cache loaded successfully, False otherwise
        """
        if not self.cache_file.exists():
            return False
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                self.cache_data = json.load(f)
            return True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load cache file: {e}")
            self.cache_data = None
            return False
    
    def save(
        self,
        output_path: str,
        input_dir: str,
        config: Dict[str, Any]
    ) -> bool:
        """
        Save cache metadata to file.
        
        Args:
            output_path: Path to generated output file
            input_dir: Directory containing input files
            config: Parsing configuration (models, settings)
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Collect input file metadata
            input_files = {}
            input_path = Path(input_dir)
            
            # Track all PDF and markdown files
            for pattern in ["*.pdf", "*.md"]:
                for file_path in input_path.glob(pattern):
                    if file_path.is_file():
                        stat = file_path.stat()
                        input_files[str(file_path)] = {
                            "mtime": stat.st_mtime,
                            "size": stat.st_size
                        }
            
            # Get output file mtime
            output_mtime = None
            output_file = Path(output_path)
            if output_file.exists():
                output_mtime = output_file.stat().st_mtime
            
            # Build cache data
            self.cache_data = {
                "version": self.VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "output_path": str(output_path),
                "output_mtime": output_mtime,
                "input_files": input_files,
                "config": config
            }
            
            # Write to file
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except (IOError, OSError) as e:
            print(f"Warning: Failed to save cache file: {e}")
            return False
    
    def is_valid(
        self,
        output_path: str,
        input_dir: str,
        config: Dict[str, Any],
        verbose: bool = False
    ) -> bool:
        """
        Check if cache is valid (no changes detected).
        
        Cache is valid when ALL conditions are met:
        1. Cache data loaded successfully
        2. Output file exists
        3. All current input files are tracked in cache
        4. All tracked input files still exist with same mtime/size
        5. Parsing configuration matches
        
        Args:
            output_path: Expected output file path
            input_dir: Directory containing input files
            config: Current parsing configuration
            verbose: Print validation details
            
        Returns:
            True if cache is valid, False otherwise
        """
        # Load cache if not already loaded
        if self.cache_data is None:
            if not self.load():
                if verbose:
                    print("   Cache: No cache file found")
                return False
        
        # Check version
        if self.cache_data.get("version") != self.VERSION:
            if verbose:
                print(f"   Cache: Version mismatch (cache: {self.cache_data.get('version')}, current: {self.VERSION})")
            return False
        
        # Check output path matches
        if self.cache_data.get("output_path") != str(output_path):
            if verbose:
                print(f"   Cache: Output path mismatch")
            return False
        
        # Check output file exists
        output_file = Path(output_path)
        if not output_file.exists():
            if verbose:
                print("   Cache: Output file missing")
            return False
        
        # Check output file mtime matches
        current_output_mtime = output_file.stat().st_mtime
        cached_output_mtime = self.cache_data.get("output_mtime")
        if cached_output_mtime is None or abs(current_output_mtime - cached_output_mtime) > 1:
            if verbose:
                print("   Cache: Output file modified")
            return False
        
        # Check configuration matches
        cached_config = self.cache_data.get("config", {})
        if cached_config != config:
            if verbose:
                print("   Cache: Configuration changed")
                print(f"     Cached: {cached_config}")
                print(f"     Current: {config}")
            return False
        
        # Get current input files
        input_path = Path(input_dir)
        current_files = {}
        
        for pattern in ["*.pdf", "*.md"]:
            for file_path in input_path.glob(pattern):
                if file_path.is_file():
                    stat = file_path.stat()
                    current_files[str(file_path)] = {
                        "mtime": stat.st_mtime,
                        "size": stat.st_size
                    }
        
        cached_files = self.cache_data.get("input_files", {})
        
        # Check if file sets match
        current_file_set = set(current_files.keys())
        cached_file_set = set(cached_files.keys())
        
        if current_file_set != cached_file_set:
            if verbose:
                added = current_file_set - cached_file_set
                removed = cached_file_set - current_file_set
                if added:
                    print(f"   Cache: Files added: {added}")
                if removed:
                    print(f"   Cache: Files removed: {removed}")
            return False
        
        # Check if any file has changed (mtime or size)
        for file_path, current_meta in current_files.items():
            cached_meta = cached_files.get(file_path)
            
            if cached_meta is None:
                if verbose:
                    print(f"   Cache: File not in cache: {file_path}")
                return False
            
            # Compare mtime and size
            if current_meta["size"] != cached_meta["size"]:
                if verbose:
                    print(f"   Cache: File size changed: {file_path}")
                return False
            
            # Allow 1 second tolerance for mtime (filesystem precision)
            if abs(current_meta["mtime"] - cached_meta["mtime"]) > 1:
                if verbose:
                    print(f"   Cache: File modified: {file_path}")
                return False
        
        # All checks passed
        if verbose:
            print("   Cache: Valid (no changes detected)")
        return True
    
    def invalidate(self) -> bool:
        """
        Delete cache file to force re-parsing.
        
        Returns:
            True if cache was deleted, False if it didn't exist
        """
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
                self.cache_data = None
                return True
            except OSError:
                return False
        return False
    
    def get_metadata(self) -> Optional[Dict[str, Any]]:
        """
        Get cache metadata.
        
        Returns:
            Cache metadata dict or None if not loaded
        """
        return self.cache_data
