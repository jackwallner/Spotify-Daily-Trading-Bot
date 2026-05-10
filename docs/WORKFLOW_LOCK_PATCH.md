# Workflow Lock Patch for GitHub Actions

## Problem
Concurrent workflow runs can cause race conditions when:
- Multiple runs try to read/append to `trades.jsonl` simultaneously
- The report generation reads while trades are being written
- Git commits/pushes conflict between overlapping runs

## Solution: Simple Lockfile Pattern

Add a lock step to `.github/workflows/trading_bot.yml` using `mkdir` (atomic on most filesystems):

```yaml
      - name: Acquire lock
        id: lock
        run: |
          MAX_WAIT=300  # 5 minutes max wait
          WAITED=0
          while ! mkdir .workflow_lock 2>/dev/null; do
            if [ $WAITED -ge $MAX_WAIT ]; then
              echo "Failed to acquire lock after ${MAX_WAIT}s"
              exit 1
            fi
            echo "Waiting for lock... ($WAITED seconds)"
            sleep 5
            WAITED=$((WAITED + 5))
          done
          echo "Lock acquired"
          echo "$(date -u +%s)" > .workflow_lock/timestamp
          echo "$$" > .workflow_lock/pid

      - name: Run trading bot
        run: python trading_bot.py

      - name: Generate report
        run: python generate_report.py

      - name: Commit and push changes
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add trades.jsonl docs/index.html trades.log || true
          git diff --staged --quiet || git commit -m "Update trade report and log [skip ci]"
          git push origin main || echo "Push failed (may already be up to date)"

      - name: Release lock
        if: always()
        run: |
          if [ -d .workflow_lock ]; then
            rm -rf .workflow_lock
            echo "Lock released"
          fi
```

## Alternative: Concurrency Control (Simpler)

Add this at the top of your workflow file (before `jobs:`):

```yaml
concurrency:
  group: trading-bot-execution
  cancel-in-progress: false
```

This ensures only one workflow runs at a time (queues subsequent runs).

## Recommendation

Use **concurrency control** (simpler, built-in) unless you need fine-grained lock control within steps.
