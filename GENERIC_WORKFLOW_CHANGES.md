# Generic Workflow & Scope Limiting Changes

## Summary

The agent has been enhanced to:
1. **Logically limit findings** based on query type (e.g., top 10/20 for standings)
2. **Work generically** for ANY query, not just F1 standings
3. **Use GMAIL_USER_EMAIL from .env** for email sending

## Key Changes

### 1. Perception Layer (`modules/perception.py`)

**Added Fields:**
- `scope_limit`: Number indicating how many results to retrieve (e.g., 10, 20)
- `scope_type`: Type of scope ("top", "recent", "current", "latest")

**Auto-Detection Logic:**
- Queries with "standings", "rankings", "leaderboard", "points" → defaults to `scope_limit: 10`, `scope_type: "top"`
- Explicit "top 20" or "top 10" → extracts number and sets scope_limit
- "current" or "latest" → sets `scope_type: "current"`, `scope_limit: 10`

**Example:**
- "Find the Current Point Standings of F1 Racers" → `scope_limit: 10`, `scope_type: "top"`
- "Find top 20 players" → `scope_limit: 20`, `scope_type: "top"`

### 2. Decision Layer (`modules/decision.py`)

**Generic Workflow:**
- Removed F1-specific guidance
- Workflow now applies to ANY query type
- Uses scope limits when constructing search queries
- Limits data extraction to `scope_limit` rows when adding to sheet

**Enhanced Queries:**
- If `scope_limit=10`, search query is enhanced with "top 10"
- Example: "F1 standings" → "F1 current point standings 2024 top 10"

### 3. Loop Layer (`core/loop.py`)

**Stores Perception:**
- Stores `current_perception` for access to scope limits throughout the workflow

**Dynamic Guidance:**
- Sheet titles are generated from query entities (not hardcoded "F1 Standings")
- Email subjects are generated from query entities
- Data extraction limited to `scope_limit` rows when specified

**Email Configuration:**
- Reads `GMAIL_USER_EMAIL` from `.env` file
- Falls back to OAuth account email if not in `.env`

### 4. Gmail Server (`mcp_server_gmail.py`)

**Email Priority:**
1. First tries `GMAIL_USER_EMAIL` from `.env` file
2. Falls back to OAuth account email from token

**Updated `send_email_with_link`:**
- Automatically uses `.env` email if `to` parameter is empty or placeholder
- Removed requirement for agent to know email address

## Environment Variables

Add to your `.env` file:

```env
GMAIL_USER_EMAIL=your-email@gmail.com
```

## Examples

### Example 1: F1 Standings (Default Top 10)
**Query:** "Find the Current Point Standings of F1 Racers"

**Perception:**
- `scope_limit: 10`
- `scope_type: "top"`

**Workflow:**
1. Search: "F1 current point standings 2024 top 10"
2. Create sheet: "F1 Standings"
3. Add data: Extract top 10 drivers with points
4. Get link
5. Send email to `GMAIL_USER_EMAIL` from `.env`

### Example 2: Cricket Scores (Top 20)
**Query:** "Find top 20 cricket scores"

**Perception:**
- `scope_limit: 20`
- `scope_type: "top"`

**Workflow:**
1. Search: "cricket latest scores top 20"
2. Create sheet: "Cricket Scores"
3. Add data: Extract top 20 scores
4. Get link
5. Send email to `GMAIL_USER_EMAIL` from `.env`

### Example 3: Generic Query
**Query:** "Find current stock prices"

**Perception:**
- `scope_limit: 10` (default for current/latest)
- `scope_type: "current"`

**Workflow:**
1. Search: "current stock prices top 10"
2. Create sheet: "Stock Prices"
3. Add data: Extract top 10 stocks
4. Get link
5. Send email to `GMAIL_USER_EMAIL` from `.env`

## Testing

1. **Set up `.env` file:**
   ```bash
   echo "GMAIL_USER_EMAIL=your-email@gmail.com" >> .env
   ```

2. **Test with different queries:**
   - "Find the Current Point Standings of F1 Racers" (should limit to top 10)
   - "Find top 20 cricket players" (should limit to top 20)
   - "Find current weather" (should limit to top 10)

3. **Verify:**
   - Sheet titles are relevant to query
   - Data rows are limited to scope_limit
   - Email is sent to `GMAIL_USER_EMAIL` from `.env`

## Notes

- If `scope_limit` is not set, all available data is extracted
- The workflow is now generic and works for any query type
- Email address is automatically retrieved from `.env` or OAuth token
- Sheet titles and email subjects are dynamically generated from query entities

