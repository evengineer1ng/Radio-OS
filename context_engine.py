"""
Character Context Engine
========================

Per-character optional context lookup system for accurate data injection.

Supports three engine types:
- API: HTTP requests to external APIs
- DB: SQLite queries against local databases  
- Text: File-based RAG with keyword/semantic search

Used by Character Manager to provide accurate context before host generation.
"""

import os
import json
import time
import sqlite3
import requests
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path


# ==============================================
# Configuration & Utilities
# ==============================================

def resolve_context_path(station_dir: str, path: str) -> str:
    """Resolve context engine file paths (db, text files)"""
    if not path:
        return ""
    
    if os.path.isabs(path):
        return path
    
    # Try station dir first
    cand = os.path.join(station_dir, path)
    if os.path.exists(cand):
        return cand
    
    # Try radio os root
    base = os.path.dirname(__file__)
    cand = os.path.join(base, path)
    if os.path.exists(cand):
        return cand
    
    return os.path.join(station_dir, path)


def get_env_or_config(key: str, config_value: Optional[str] = None) -> Optional[str]:
    """Get value from environment variable or fall back to config"""
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    return config_value


# ==============================================
# Cache System
# ==============================================

class ContextCache:
    """Simple in-memory cache with TTL"""
    
    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}
    
    def get(self, key: str, ttl: int = 300) -> Optional[Any]:
        """Get cached value if not expired"""
        if key not in self._cache:
            return None
        
        value, timestamp = self._cache[key]
        if time.time() - timestamp > ttl:
            del self._cache[key]
            return None
        
        return value
    
    def set(self, key: str, value: Any):
        """Cache a value with current timestamp"""
        self._cache[key] = (value, time.time())
    
    def clear(self):
        """Clear all cached values"""
        self._cache.clear()


_global_cache = ContextCache()


# ==============================================
# API Engine
# ==============================================

def query_api_engine(config: Dict[str, Any], params: Dict[str, Any], station_dir: str = "") -> Optional[Dict[str, Any]]:
    """
    Execute API context lookup.
    
    Config:
        source: API endpoint URL (supports {param} templates)
        api_key_env: Environment variable name for API key
        api_key: Direct API key (less secure)
        method: GET or POST
        headers: Additional headers
        timeout: Request timeout in seconds
        cache_ttl: Cache time-to-live in seconds
    
    Params:
        query_params: Dict to populate URL template and query string
    
    Returns:
        API response as dict or None on error
    """
    
    source = config.get("source", "").strip()
    if not source:
        return None
    
    # Build URL with template substitution
    url = source
    for key, val in params.items():
        placeholder = f"{{{key}}}"
        if placeholder in url:
            url = url.replace(placeholder, str(val))
    
    # Get API key
    api_key_env = config.get("api_key_env", "")
    api_key = get_env_or_config(api_key_env, config.get("api_key"))
    
    # Build headers
    headers = dict(config.get("headers", {}))
    if api_key:
        # Try common auth patterns
        if "Authorization" not in headers:
            # Try Bearer token
            if config.get("auth_type") == "bearer":
                headers["Authorization"] = f"Bearer {api_key}"
            # Try API key header
            elif config.get("auth_type") == "apikey":
                key_header = config.get("api_key_header", "X-API-Key")
                headers[key_header] = api_key
            else:
                # Default to query param
                pass
    
    # Cache key
    cache_key = f"api:{url}:{json.dumps(params, sort_keys=True)}"
    cache_ttl = int(config.get("cache_ttl", 300))
    
    # Check cache
    cached = _global_cache.get(cache_key, cache_ttl)
    if cached is not None:
        return cached
    
    # Make request
    method = config.get("method", "GET").upper()
    timeout = int(config.get("timeout", 10))
    
    try:
        if method == "POST":
            # POST with JSON body
            body = params.copy()
            resp = requests.post(url, json=body, headers=headers, timeout=timeout)
        else:
            # GET with query params (only non-templated params)
            query_params = {k: v for k, v in params.items() if f"{{{k}}}" not in source}
            if api_key and not headers.get("Authorization") and config.get("auth_type") != "apikey":
                query_params["apikey"] = api_key
            resp = requests.get(url, params=query_params, headers=headers, timeout=timeout)
        
        if resp.status_code == 200:
            result = resp.json()
            _global_cache.set(cache_key, result)
            return result
        
        return None
    
    except Exception as e:
        print(f"API context engine error: {e}")
        return None


# ==============================================
# Database Engine
# ==============================================

def query_db_engine(config: Dict[str, Any], params: Dict[str, Any], station_dir: str = "") -> Optional[List[Dict[str, Any]]]:
    """
    Execute database context lookup.
    
    Config:
        source: Path to SQLite database file
        query: SQL query template with {param} placeholders
        cache_ttl: Cache time-to-live in seconds
    
    Params:
        query_params: Dict to populate SQL query placeholders
    
    Returns:
        List of result rows as dicts or None on error
    """
    
    db_path = config.get("source", "").strip()
    if not db_path:
        return None
    
    db_path = resolve_context_path(station_dir, db_path)
    if not os.path.exists(db_path):
        return None
    
    query_template = config.get("query", "").strip()
    if not query_template:
        return None
    
    # Build query with parameter substitution
    query = query_template
    query_params = []
    
    # Replace {param} with ? for parameterized query (SQL injection safe)
    for key in params.keys():
        placeholder = f"{{{key}}}"
        if placeholder in query:
            query = query.replace(placeholder, "?")
            query_params.append(params[key])
    
    # Cache key
    cache_key = f"db:{db_path}:{query}:{json.dumps(query_params, sort_keys=True)}"
    cache_ttl = int(config.get("cache_ttl", 300))
    
    cached = _global_cache.get(cache_key, cache_ttl)
    if cached is not None:
        return cached
    
    # Execute query
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(query, query_params)
        rows = cursor.fetchall()
        
        # Convert to list of dicts
        result = [dict(row) for row in rows]
        
        conn.close()
        
        _global_cache.set(cache_key, result)
        return result
    
    except Exception as e:
        print(f"DB context engine error: {e}")
        return None


# ==============================================
# Text/RAG Engine
# ==============================================

def query_text_engine(config: Dict[str, Any], params: Dict[str, Any], station_dir: str = "") -> Optional[List[Dict[str, Any]]]:
    """
    Execute text-based context lookup (simple keyword search).
    
    Config:
        source: Path to text file or directory
        search_mode: "keyword" or "semantic" (semantic needs embeddings - future)
        max_results: Maximum number of results to return
        chunk_size: Characters per chunk (for file splitting)
    
    Params:
        query: Search query string
        keywords: List of keywords to search for
    
    Returns:
        List of matching text chunks with metadata
    """
    
    text_path = config.get("source", "").strip()
    if not text_path:
        return None
    
    text_path = resolve_context_path(station_dir, text_path)
    if not os.path.exists(text_path):
        return None
    
    search_mode = config.get("search_mode", "keyword")
    max_results = int(config.get("max_results", 5))
    chunk_size = int(config.get("chunk_size", 500))
    
    # Get search terms
    query = params.get("query", "")
    keywords = params.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [keywords]
    
    search_terms = [query] + keywords
    search_terms = [t.lower().strip() for t in search_terms if t]
    
    if not search_terms:
        return None
    
    # Cache key
    cache_key = f"text:{text_path}:{json.dumps(search_terms, sort_keys=True)}"
    cache_ttl = int(config.get("cache_ttl", 600))  # Text changes less often
    
    cached = _global_cache.get(cache_key, cache_ttl)
    if cached is not None:
        return cached
    
    # Read files
    files_to_search = []
    if os.path.isfile(text_path):
        files_to_search.append(text_path)
    elif os.path.isdir(text_path):
        # Search all .txt and .md files in directory
        for ext in ["*.txt", "*.md"]:
            files_to_search.extend(Path(text_path).glob(ext))
    
    results = []
    
    for file_path in files_to_search:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Split into chunks
            chunks = []
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                chunks.append((i, chunk))
            
            # Score each chunk by keyword matches
            for offset, chunk in chunks:
                chunk_lower = chunk.lower()
                score = sum(1 for term in search_terms if term in chunk_lower)
                
                if score > 0:
                    results.append({
                        "file": os.path.basename(file_path),
                        "offset": offset,
                        "text": chunk.strip(),
                        "score": score,
                        "matches": [t for t in search_terms if t in chunk_lower]
                    })
        
        except Exception as e:
            print(f"Text engine error reading {file_path}: {e}")
            continue
    
    # Sort by score and limit
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:max_results]
    
    _global_cache.set(cache_key, results)
    return results


# ==============================================
# Unified Query Interface
# ==============================================

def query_context_engine(
    engine_config: Dict[str, Any],
    params: Dict[str, Any],
    station_dir: str = ""
) -> Optional[Any]:
    """
    Unified interface to query any context engine type.
    
    Args:
        engine_config: Character's context_engine config from manifest
        params: Query parameters from Character Manager
        station_dir: Station directory for path resolution
    
    Returns:
        Context data (format depends on engine type) or None
    """
    
    if not engine_config.get("enabled"):
        return None
    
    engine_type = engine_config.get("type", "").lower()
    
    if engine_type == "api":
        return query_api_engine(engine_config, params, station_dir)
    elif engine_type == "db":
        return query_db_engine(engine_config, params, station_dir)
    elif engine_type == "text":
        return query_text_engine(engine_config, params, station_dir)
    else:
        return None


# ==============================================
# Context Formatter
# ==============================================

def format_context_for_prompt(context_data: Any, engine_type: str) -> str:
    """
    Format context engine results for injection into host prompt.
    
    Args:
        context_data: Raw results from context engine
        engine_type: "api", "db", or "text"
    
    Returns:
        Formatted string for prompt injection
    """
    
    if not context_data:
        return ""
    
    lines = ["=== REFERENCE DATA (Context Engine) ==="]
    
    if engine_type == "api":
        # Format API JSON response
        if isinstance(context_data, dict):
            for key, value in context_data.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"{key}: {json.dumps(value, indent=2)}")
                else:
                    lines.append(f"{key}: {value}")
        else:
            lines.append(str(context_data))
    
    elif engine_type == "db":
        # Format database rows
        if isinstance(context_data, list) and context_data:
            for i, row in enumerate(context_data, 1):
                lines.append(f"\nResult {i}:")
                for key, value in row.items():
                    lines.append(f"  {key}: {value}")
    
    elif engine_type == "text":
        # Format text search results
        if isinstance(context_data, list) and context_data:
            for i, result in enumerate(context_data, 1):
                file = result.get("file", "unknown")
                text = result.get("text", "")[:300]  # Limit length
                matches = result.get("matches", [])
                lines.append(f"\n[{file}] Matched: {', '.join(matches)}")
                lines.append(f"  {text}...")
    
    lines.append("=== END REFERENCE DATA ===\n")
    
    return "\n".join(lines)
