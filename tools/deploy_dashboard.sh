#!/bin/bash
# MANUAL deploy of the Asymmetry Bench dashboard — normally not needed.
#
# The normal publish path is CI: commit an exported runs/<run_id>/ folder,
# list it in runs/manifest.txt, and push — .github/workflows/publish-site.yml
# rebuilds and deploys the site (see runs/README.md). Use this script only to
# mirror a live run's progress before it completes, or to push the Miwi343
# mirror. The next CI deploy rebuilds from the committed manifest, so whatever
# this script publishes is overwritten on the next push.
#
# Usage: tools/deploy_dashboard.sh <run_id> [<run_id> ...]
#
# Exports data.json for the given runs FROM YOUR LOCAL DB (exemplars merged
# automatically when asymbench/reports/first_trial/exemplars.json covers one),
# copies the static page beside it, and pushes both to the gh-pages branch.
# It never touches the current branch or working tree.
set -euo pipefail
cd "$(dirname "$0")/.."

[ $# -ge 1 ] || { echo "usage: tools/deploy_dashboard.sh <run_id> [<run_id> ...]"; exit 2; }

.venv/bin/python tools/export_dashboard_data.py "$@" \
  --exemplars asymbench/reports/first_trial/exemplars.json \
  --out asymbench/reports/dashboard_data.json

WT=$(mktemp -d /tmp/asymbench-pages.XXXXXX)
cleanup() { git worktree remove --force "$WT" 2>/dev/null || true; rm -rf "$WT"; }
trap cleanup EXIT

if git ls-remote --exit-code origin gh-pages >/dev/null 2>&1; then
  git fetch origin gh-pages
  git worktree add "$WT" origin/gh-pages >/dev/null
  (cd "$WT" && git checkout -B gh-pages >/dev/null 2>&1)
else
  git worktree add --detach "$WT" >/dev/null
  (cd "$WT" && git checkout --orphan gh-pages >/dev/null 2>&1 && git rm -rfq . 2>/dev/null || true)
fi

cp asymbench/dashboard/index.html "$WT/index.html"
cp asymbench/reports/dashboard_data.json "$WT/data.json"
touch "$WT/.nojekyll"

cd "$WT"
git add -A
if git diff --cached --quiet; then
  echo "site unchanged; nothing to push"
else
  git commit -q -m "Dashboard sync $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git push -q origin gh-pages
  echo "pushed gh-pages (org repo; serves once an admin enables Pages)"
  # Live site: Miwi343/asymmetry-bench serves from its main branch.
  git push -q -f git@github.com:Miwi343/asymmetry-bench.git gh-pages:main
  echo "pushed -> https://miwi343.github.io/asymmetry-bench/"
fi
