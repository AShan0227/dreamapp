#!/usr/bin/env bash
# DreamApp CI + branch-protection bootstrap.
#
# What this script does (in order):
#   1. Refresh `gh auth` to add the `workflow` scope (interactive, opens browser).
#   2. Push the .github/workflows/*.yml files (which the initial commit had to skip).
#   3. Wait for the first CI run to finish + report status.
#   4. Apply main-branch protection rules (only works if repo is PUBLIC or
#      the account has GitHub Pro). If 403, prints clear next-step.
#
# Run from the dreamapp/ project root:
#     bash scripts/setup-ci-and-protection.sh
#
# Idempotent: safe to re-run.

set -euo pipefail

REPO="AShan0227/dreamapp"

# ----- 1. Refresh auth ------------------------------------------------------

echo "▸ Step 1/4 — refreshing gh token to include 'workflow' scope"
echo "  (This will open a browser for you to confirm.)"
gh auth status -h github.com 2>&1 | grep -q "'workflow'" || \
  gh auth refresh -h github.com -s workflow

# Verify
gh auth status -h github.com 2>&1 | grep "Token scopes" | grep -q workflow || {
  echo "✗ workflow scope still missing. Aborting."
  exit 1
}
echo "✓ workflow scope present"
echo

# ----- 2. Commit + push the workflow files ----------------------------------

echo "▸ Step 2/4 — pushing .github/workflows/*.yml"
git add .github/workflows/
if git diff --cached --quiet; then
  echo "  (nothing new in workflows — skipping commit)"
else
  git commit -m "ci: add GitHub Actions pipeline (unit + alembic + frontend build)"
  git push origin main
fi
echo "✓ workflow files on origin/main"
echo

# ----- 3. Watch first CI run ------------------------------------------------

echo "▸ Step 3/4 — waiting for first CI run to finish"
sleep 5
RUN_ID=$(gh run list --workflow=ci.yml --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || echo "")
if [ -z "$RUN_ID" ]; then
  echo "  No run found yet — Actions may still be queueing."
  echo "  Check manually: gh run list --workflow=ci.yml"
else
  echo "  Watching run $RUN_ID..."
  gh run watch "$RUN_ID" --exit-status || echo "✗ CI run failed — see details with: gh run view $RUN_ID"
fi
echo

# ----- 4. Branch protection -------------------------------------------------

echo "▸ Step 4/4 — applying main branch protection"
PROTECTION_PAYLOAD=$(cat <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Unit tests", "Alembic migrations", "Frontend build"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON
)

RESPONSE=$(echo "$PROTECTION_PAYLOAD" | gh api -X PUT \
  "/repos/${REPO}/branches/main/protection" --input - 2>&1 || true)

if echo "$RESPONSE" | grep -q '"protection_url"'; then
  echo "✓ main branch protected"
  echo "    - Required status checks: Unit tests, Alembic migrations, Frontend build"
  echo "    - Required PR review (1 approval, dismiss stale on push)"
  echo "    - Linear history enforced (no merge commits — squash/rebase only)"
  echo "    - No force push, no deletion"
  echo "    - Conversation resolution required"
elif echo "$RESPONSE" | grep -qi "Upgrade"; then
  cat <<'EOM'
✗ Free-tier private repos can't enable branch protection.

  Two ways forward:

  (A) Make repo public (lets branch protection + unlimited free Actions):
        gh repo edit AShan0227/dreamapp --visibility public --accept-visibility-change-consequences
      Then re-run this script.

  (B) Stay private + upgrade to GitHub Pro ($4/mo):
        https://github.com/account/billing
      Then re-run this script.

  Either way, the CI workflow itself is now running on every push — the
  protection is what GATES merging into main on a passing CI.
EOM
else
  echo "⚠ Unexpected response:"
  echo "$RESPONSE" | head -5
fi
