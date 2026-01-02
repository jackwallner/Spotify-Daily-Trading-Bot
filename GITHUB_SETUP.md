# GitHub Setup Guide for Spotify Daily Markets Bot

Follow these steps to publish your bot to GitHub and set up GitHub Actions.

## Step 1: Initialize Git Repository (if not already done)

Open Terminal and navigate to your project directory:

```bash
cd /path/to/your/repo
```

Initialize a new git repository (if needed):

```bash
git init
```

## Step 2: Stage and Commit Your Files

Add all the necessary files (`.env` is already in `.gitignore`, so it won't be committed):

```bash
git add .gitignore .github requirements.txt README.md trading_bot.py .env.example
```

Commit the files:

```bash
git commit -m "Initial commit: Spotify daily markets bot"
```

## Step 3: Create a GitHub Repository

1. Go to [GitHub.com](https://github.com) and sign in
2. Click the **"+"** icon in the top right corner
3. Select **"New repository"**
4. Fill in the repository details:
   - **Repository name**: `spotify-daily-markets-bot` (or any name you prefer)
   - **Description**: "Automated trading bot for Spotify daily markets on Kalshi"
   - **Visibility**: Choose **Private** (recommended for trading bots with API keys)
   - **DO NOT** initialize with README, .gitignore, or license (we already have these)
5. Click **"Create repository"**

## Step 4: Connect Local Repository to GitHub

GitHub will show you commands to push an existing repository. Run these commands:

```bash
git remote add origin https://github.com/YOUR_USERNAME/kalshi-trading-bot.git
```

Replace `YOUR_USERNAME` with your GitHub username.

```bash
git branch -M main
git push -u origin main
```

You'll be prompted for your GitHub credentials. Use a Personal Access Token if you have 2FA enabled.

## Step 5: Add GitHub Secrets for API Credentials

**IMPORTANT:** Never commit your `.env` file. Instead, we'll use GitHub Secrets.

1. Go to your repository on GitHub
2. Click **"Settings"** (top menu bar)
3. In the left sidebar, click **"Secrets and variables"** → **"Actions"**
4. Click **"New repository secret"** button
5. Add the following secrets:

### Secret 1: KALSHI_API_KEY_ID
   - **Name**: `KALSHI_API_KEY_ID`
   - **Secret**: `66747c1c-8c15-46fd-b182-283fcc0cc0e1`
   - Click **"Add secret"**

### Secret 2: KALSHI_PRIVATE_KEY
   - **Name**: `KALSHI_PRIVATE_KEY`
   - **Secret**: Copy and paste your ENTIRE private key, including the BEGIN/END lines:
     ```
     -----BEGIN RSA PRIVATE KEY-----
     MIIEpAIBAAKCAQEAzl0DOnkCHSbGMYvh6g/syekvIoqaH/LA200rSwtUSLumUeTF
     esJtoBb15xcGdiu4VlzJexMkoVsFWSS0MjudXOcnk7+s6pqNhhr0ebKlf6urbGmt
     Udp/Xfur6/AZScJe/nydBwFEkb4f195MUS97Nl9Vr6WRoQNrcQw32WkoRnxm18U+
     774VWN9xva+oo8yug/4RiXSgEKVCNb8fdrdMXwj2Tjjz587RiaxhJw4mCYyuyBEM
     7cRqAFToxw27o7VSy8Toew/CjSDBSAr/iATE8zNktZI/B9ujxuNgTPFh3J+OBnaw
     VLCB4MPUaKXqN4dnzN4Z0rIzTTq8/vw2/7c7swIDAQABAoIBABNUnSfODAelCS28
     97WQNlMXl8W5jARwHeatDOAjuIpzoXnMXz9HlTNI01IJUx6gq8zTNkBkI6tFtnOK
     P6Lw+KWqNYfejZkQTy9/uOTpeh1CfHVUVNr1B7dLCui3/fZt0a4vCBqO4NhyIdN7
     zFRSiU0nkwQ4EzMs+dSGG3kvI4mulHeoVJYiaC6d2/IJAOITEKpTtERGWUVFNjuS
     kIlA7JLo5vPQwEwTbJ8RscJLrUweMyywH2C5Qf0bS1HxBQhOG1UDYkUmdtZlspvj
     j2wt1gXmXFb6dwq54qGkqY4P2Y0CTsAq0L6rPf8MyebYkKESHRMtmtwUCA1lUFTT
     BK4N0HECgYEA57zqYb1SU/ta1l7o0FJm5SxAcYDsYE+gp6hANo8BJXGiBxkqXRTs
     tBjmr7lxeFsbFvCeususEi5VnYRubLGvttUmjaMMWKJVwSe4Xf8aHlaUmTR1SjuD
     Gbk3FqmsuN9GuC8YgFbaAX6mwvTZmzI55ZJ1sVAgKPlPYa8CGYs/h8kCgYEA4/gA
     bRYbQo2Df89+34dm7FraVQPLXUCPXMLsM9lDkOVAKJlb+xRICz0M4hfbfxxDKwyk
     5qKsWbkscB0eibrN9D0QD4KfH9Iq1AY2DZeK8IQq8M/vdcUtJ94/RiV7eIoXqtQC
     Hb+JqUeEfNi8W/aNLfBnEn6yZQJBGsEN8YqMXZsCgYB6Igq1MH5vXI3nZWX2RTeN
     mODt8TCjIdReCEKvfnbwMQ9gBldZb2nBEU6jVm0DLaD9WhuN/0HU4y6kMeOwzYT6
     KySCiWg8XnIrtq9oesZdLuxqQkd+tBbIO+FYxFwPoz02XTvgh+Wl3AYvwbPeI354
     C9STetM4RQ0dQossw0LcYQKBgQDXeV0lvsRrZokJsJ2SOFBfTQybWKfK76/SFOff
     phdICHhZJ4OaUbQ68yyPM8+jWJpgQWZIHTBc6jsHiW6I7kmm9mSM1IEFOciDeY9z
     z25jIfnYfiIvpfyld1tFOT54U8ZFEHkjlxxOJawjuVRodCVDa7xw7dI+yR+yYxGD
     4doEywKBgQCTNibb3g3JXE1SzuyrT1tE8j3pkIjbSNtvx0hYLZARh8zrxOXxg64K
     oKXTS8wO6EOJEgG82A0R33EHXU4iej29wz+kbuaz0ne5wAF/t+T3ZT2pcnGm9gMj
     9/sdayJFuwnyoLC5rMQVid+UZmd93J6TRCSjhl0qjq2TTuFjYvkzeA==
     -----END RSA PRIVATE KEY-----
     ```
   - Click **"Add secret"**

## Step 6: Verify GitHub Actions Workflow

The workflow file is already in your repository at `.github/workflows/trading_bot.yml`. It's configured to:
- Run every 15 minutes automatically
- Run manually (via workflow_dispatch)
- Install dependencies
- Create `.env` file from secrets
- Execute the trading bot
- Upload trade logs as artifacts

## Step 7: Test the Workflow

1. Go to the **"Actions"** tab in your GitHub repository
2. You should see "Kalshi Trading Bot" workflow listed
3. Click on it, then click **"Run workflow"** button (top right)
4. Select the main branch and click **"Run workflow"**
5. Wait a few moments, then click on the workflow run to see the logs

## Step 8: Monitor Your Bot

- **Actions Tab**: View all workflow runs and logs
- **Artifacts**: Download `trades.log` from each run to see trade history
- The bot runs automatically every 15 minutes

## Troubleshooting

**Workflow fails with "No module named 'kalshi_python_sync'":**
- Check that `requirements.txt` is committed correctly

**Workflow fails with authentication errors:**
- Verify your secrets are set correctly
- Make sure the private key includes BEGIN/END lines and all newlines

**Workflow runs but no trades:**
- Check the logs in Actions tab
- Verify Fear & Greed Index API is accessible
- Check that BTC markets are available

## Security Notes

✅ **GOOD**: Your `.env` file is in `.gitignore` - it won't be committed
✅ **GOOD**: Using GitHub Secrets to store credentials
✅ **GOOD**: Private repository recommended for trading bots
⚠️ **REMEMBER**: Never commit API keys or private keys to git

## Next Steps

1. Monitor the first few runs to ensure everything works
2. Check `trades.log` artifacts to verify trades are executing
3. Adjust trading logic if needed
4. Consider adding email notifications for trades (optional)

Your bot is now live and will run every 15 minutes! 🚀

