# Character Context Engine UI Guide

## Overview

The Character Context Engine UI has been integrated into both the Station Wizard and Editor Window, allowing users to configure per-character knowledge sources through a user-friendly interface.

## Location in UI

### Station Wizard
- Navigate to the "Characters" step in the Station Wizard
- Select a character from the list on the left
- Scroll down to see the **"⚡ Context Engine (Optional)"** section

### Editor Window
- Open the Station Editor (click station → Settings)
- Go to the "Characters" tab
- Select a character from the list on the left
- Scroll down to see the **"⚡ Context Engine (Optional)"** section

## Configuration Fields

### Basic Settings

1. **Enable Checkbox** - Turn the context engine on/off for this character
2. **Type Dropdown** - Choose the engine type:
   - `api` - REST API endpoint
   - `db` - SQLite database query
   - `text` - Text file search (keyword or semantic)
3. **Description** - Brief explanation of what this engine provides
4. **Source** - URL, database path, or directory (browse button available for db/text)

### Type-Specific Configuration

#### API Configuration
- **API Key (env var)** - Environment variable name containing API key (e.g., `NBA_API_KEY`)
- **Method** - HTTP method (GET or POST)
- **Auth Type** - Authentication method (bearer, apikey, or none)

#### Database Configuration
- **SQL Query** - SQL query with `{param}` placeholders
  - Example: `SELECT * FROM players WHERE name LIKE '%{player}%'`
- **Browse Button** - Select .db or .sqlite file

#### Text Configuration
- **Search Mode** - How to search files (keyword or semantic)
- **Max Results** - Maximum number of results to return (1-20)
- **Browse Button** - Select directory containing text files

### Common Settings (All Types)

- **Cache TTL (sec)** - How long to cache results (0-7200 seconds)

## Testing Your Configuration

Click the **"🧪 Test Query"** button to verify your configuration:

1. A dialog will appear asking for test parameters
2. Enter JSON parameters matching your query placeholders
   - Example: `{"player": "LeBron", "team": "Lakers"}`
3. Click "Run Test" to execute the query
4. Results will be displayed if successful, errors shown if failed

### Test Examples

**API Test** (NBA stats):
```json
{"player": "LeBron James"}
```

**Database Test** (player lookup):
```json
{"player": "James", "season": "2023"}
```

**Text Test** (document search):
```json
{"keyword": "championship", "year": "2020"}
```

## Workflow

1. **Enable** the context engine
2. **Select type** (API, DB, or Text)
3. **Configure source** and type-specific fields
4. **Test** with sample parameters
5. **Apply changes** to save
6. **Save station** configuration

## Examples by Use Case

### Basketball Statistics API
- Type: `api`
- Source: `https://api.balldontlie.io/v1/players`
- API Key: `BALLDONTLIE_API_KEY`
- Method: `GET`
- Auth: `apikey`
- Description: "Current player stats and game data"

### Hockey Player Database
- Type: `db`
- Source: `c:\hockey\players.db` (use Browse)
- Query: `SELECT * FROM players WHERE name LIKE '%{player}%' AND season = {season}`
- Description: "Historical player statistics"

### Racing Documents
- Type: `text`
- Source: `c:\racing\docs` (use Browse)
- Search Mode: `keyword`
- Max Results: `5`
- Description: "Race results and driver info"

## Saving Configuration

Context engine settings are saved automatically when you:
- Click "Apply character changes" (Station Wizard)
- Click "Apply Changes" (Editor Window)
- Click "Save Configuration" (Editor Window)

Settings are stored in the `manifest.yaml` under each character:

```yaml
characters:
  analyst:
    role: "Technical Analyst"
    traits: ["analytical", "data-driven"]
    focus: ["statistics", "trends"]
    context_engine:
      enabled: true
      type: "api"
      description: "Player statistics API"
      source: "https://api.example.com/stats"
      api_key_env: "STATS_API_KEY"
      method: "GET"
      auth_type: "bearer"
      cache_ttl: 300
```

## Troubleshooting

### Test Query Fails
- Check API key is set in environment variable
- Verify source path exists (for db/text)
- Check JSON parameters match query placeholders
- Test API endpoint with curl/Postman first

### Character Manager Not Using Context
- Ensure context engine is **enabled**
- Verify `context_engine.py` exists in radio_os directory
- Check runtime logs for context lookups
- Confirm Character Manager model is configured

### Results Are Stale
- Reduce cache TTL for more frequent updates
- Set to 0 to disable caching (not recommended for APIs with rate limits)

## Advanced Tips

1. **Environment Variables** - Set API keys in your shell before launching:
   ```powershell
   $env:NBA_API_KEY = "your_key_here"
   python shell.py
   ```

2. **Query Placeholders** - Use descriptive names that Character Manager can extract:
   - Good: `{player}`, `{team}`, `{date}`
   - Bad: `{p}`, `{x}`, `{val}`

3. **Multiple Engines** - Different characters can have different engines:
   - Host: News API for headlines
   - Analyst: Database for historical stats
   - Color Commentator: Text files for trivia

4. **Testing Without Runtime** - Use test query feature to debug without starting station

## Integration with Character Manager

When enabled, the Character Manager will:
1. Analyze each segment before generation
2. Determine which characters need context
3. Extract query parameters from segment content
4. Execute context queries
5. Inject results into character prompts

See [CHARACTER_CONTEXT_EXAMPLES.md](CHARACTER_CONTEXT_EXAMPLES.md) for implementation details.
