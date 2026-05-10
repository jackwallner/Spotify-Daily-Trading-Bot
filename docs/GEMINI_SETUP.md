# Gemini API Setup for Trade Analysis

The bot can optionally use Google's Gemini API to generate AI analysis of trading decisions, including confidence levels and insights.

## Setup

### 1. Get a Gemini API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the API key

### 2. Add to GitHub Secrets

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add:
   - **Name**: `GEMINI_API_KEY`
   - **Secret**: Your Gemini API key
5. Click **Add secret**

### 3. Local Testing (Optional)

If you want to test locally, add to your `.env` file:

```
GEMINI_API_KEY=your_gemini_api_key_here
```

## What the Analysis Includes

After each run, the bot will generate:
- **Why trades were or weren't executed** based on sentiment
- **Confidence level (1-10)** for the trading decision
- **Market condition insights**

The analysis is:
- Saved to `analysis.log`
- Displayed in the console output
- Included in the HTML report at `docs/index.html`

## Note

The Gemini API key is **optional**. If not provided, the bot will run normally without generating analysis.

