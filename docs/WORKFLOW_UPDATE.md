# Workflow Update Instructions

Since workflow files can't be pushed via git, please update the workflow file on GitHub:

1. Go to: https://github.com/jackwallner/kalshi-trading-bot/edit/main/.github/workflows/trading_bot.yml

2. Find the "Checkout repository" step (around line 15) and change it to:
   ```yaml
   - name: Checkout repository
     uses: actions/checkout@v3
     with:
       token: ${{ secrets.GITHUB_TOKEN }}
   ```

3. After the "Run trading script" step (around line 38), add these two new steps:
   ```yaml
   - name: Generate HTML report
     if: always()
     run: |
       python generate_report.py || echo "Report generation failed"

   - name: Commit and push report
     if: always()
     run: |
       git config --local user.email "action@github.com"
       git config --local user.name "GitHub Action"
       git add docs/index.html || true
       git diff --staged --quiet || git commit -m "Update trade report [skip ci]"
       git push origin main || echo "Push failed (may already be up to date)"
   ```

4. Click "Commit changes"

After this update, the workflow will automatically generate and update the HTML report!

