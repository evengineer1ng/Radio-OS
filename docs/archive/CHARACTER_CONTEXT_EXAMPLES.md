# Character Context Engine Examples
#
# Add these configurations to your station manifest under the `characters:` section

# Example 1: API Engine (Sports Stats)
characters:
  stats_guru:
    voice: voices/en_US-hfc_male-medium.onnx
    focus: ["stats", "analytics", "numbers", "records"]
    traits: ["analytical", "precise"]
    context_engine:
      enabled: true
      type: "api"
      description: "NBA game scores and player statistics"
      source: "https://api.sportsdata.io/v3/nba/scores/json/GamesByDate/{date}"
      api_key_env: "NBA_STATS_API_KEY"  # Set this environment variable
      method: "GET"
      auth_type: "apikey"
      api_key_header: "Ocp-Apim-Subscription-Key"
      cache_ttl: 300  # Cache for 5 minutes
      timeout: 10

# Example 2: Database Engine (Local Game Database)
characters:
  game_expert:
    voice: voices/en_US-amy-medium.onnx
    focus: ["gameplay", "mechanics", "strategy"]
    traits: ["experienced", "helpful"]
    context_engine:
      enabled: true
      type: "db"
      description: "Local game stats database"
      source: "data/games.db"  # Relative to station directory
      query: "SELECT * FROM games WHERE title LIKE '%{game_name}%' LIMIT 5"
      cache_ttl: 600  # Cache for 10 minutes

# Example 3: Text/RAG Engine (Documentation Files)
characters:
  rule_keeper:
    voice: voices/en_GB-alan-medium.onnx
    focus: ["rules", "regulations", "guidelines"]
    traits: ["authoritative", "clear"]
    context_engine:
      enabled: true
      type: "text"
      description: "Game rulebooks and guides"
      source: "data/rulebooks/"  # Directory of .txt and .md files
      search_mode: "keyword"  # or "semantic" (future)
      max_results: 3
      chunk_size: 500
      cache_ttl: 3600  # Cache for 1 hour

# Example 4: Music Streaming API
characters:
  music_expert:
    voice: voices/en_US-lessac-high.onnx
    focus: ["charts", "streaming", "popularity"]
    traits: ["enthusiastic", "trendy"]
    context_engine:
      enabled: true
      type: "api"
      description: "Spotify Charts API"
      source: "https://api.spotify.com/v1/tracks/{track_id}"
      api_key_env: "SPOTIFY_ACCESS_TOKEN"
      method: "GET"
      auth_type: "bearer"
      headers:
        Accept: "application/json"
      cache_ttl: 1800  # Cache for 30 minutes

# Example 5: Stock Market API
characters:
  market_analyst:
    voice: voices/en_US-danny-low.onnx
    focus: ["stocks", "markets", "trading"]
    traits: ["professional", "cautious"]
    context_engine:
      enabled: true
      type: "api"
      description: "Stock prices and market data"
      source: "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}"
      api_key_env: "ALPHAVANTAGE_API_KEY"
      method: "GET"
      timeout: 15
      cache_ttl: 60  # Cache for 1 minute (stocks change fast)

# Configuration Tips:
#
# 1. API Keys: Always use environment variables for security
#    - Set them before launching: $env:NBA_STATS_API_KEY="your_key_here"
#    - Or add to your shell profile
#
# 2. Caching: Adjust cache_ttl based on data freshness needs
#    - Real-time data (stocks): 60-300 seconds
#    - Daily data (game scores): 3600+ seconds  
#    - Static data (docs): 7200+ seconds
#
# 3. Query Parameters: The Character Manager extracts these automatically
#    - URL templates use {param_name} syntax
#    - DB queries use {param_name} which get replaced with ? (safe from SQL injection)
#    - Text search uses query and keywords params
#
# 4. Optional Character Manager Model:
#    Add to your manifest models section if you want a separate model:
#    
#    models:
#      character_manager: "llama3.2:latest"  # Lightweight model for routing
#      host: "qwen2.5:14b"  # Main host model
#
#    If not specified, uses the host model for character management.
