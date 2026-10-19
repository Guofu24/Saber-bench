#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Missing Python 3: install only this missing prerequisite before running.' >&2
  exit 2
fi
if ! command -v claude >/dev/null 2>&1; then
  echo 'Missing Claude Code CLI: install and authenticate before running.' >&2
  exit 2
fi
# Subscription-only is the DEFAULT. Refuse API keys or other billable backend
# credentials during preflight. For pay-as-you-go, operator must explicitly use
# `./run.sh --billing-mode api --budget-usd <dollar_cap>`.
if [ "$#" -gt 0 ]; then
  exec python3 scripts/run_autonomous.py --strict-sandbox "$@"
fi
exec python3 scripts/run_autonomous.py --billing-mode subscription --strict-sandbox
