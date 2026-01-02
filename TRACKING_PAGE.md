# Trade Report Tracking Page

## Quick Access

### Option 1: View on GitHub (Recommended for Private Repos)
**Direct link to the report:**
```
https://github.com/jackwallner/kalshi-trading-bot/blob/main/docs/index.html
```

Or navigate: Repository → `docs` folder → `index.html`

GitHub will render the HTML file in your browser. This works even for private repositories!

### Option 2: View Locally
Run the viewer script to open the report in your browser:
```bash
python view_report.py
```

Or manually open: `docs/index.html` in your browser

### Option 3: GitHub Pages (Requires Public Repo)
⚠️ **Note:** GitHub Pages only works with public repositories (or GitHub Enterprise).

If you want to make your repo public (not recommended if it contains API keys):
1. Go to repository Settings → Pages
2. Source: Branch `main`, Folder `/docs`
3. Save

Then visit: `https://jackwallner.github.io/kalshi-trading-bot/`

**Recommendation:** Keep the repo private and use Option 1 or 2 for security.

## What the Report Shows

- **Total Trades**: Number of trades executed
- **Successful**: Trades that completed successfully
- **Failed**: Trades that failed
- **No Trade (Neutral)**: Runs where sentiment was neutral (40-60)
- **Full Trade History**: Table with all trades including:
  - Timestamp
  - Market ticker
  - Action (Buy YES/NO)
  - Status

## Report Updates

The report is automatically updated after each workflow run (every 15 minutes or on manual trigger). The HTML file is committed to the `docs/index.html` file in your repository.

