#!/usr/bin/env bash
# Pull annotations from every job in a GitHub Actions run and report by level.
#
# Use this whenever a run "looks green" but you need to confirm there are no
# residual warnings (deprecation notices, etc.) — exit conclusion alone hides
# warning-level annotations.
#
# Usage:
#   scripts/ci/check_run_annotations.sh                       # latest run on current branch
#   scripts/ci/check_run_annotations.sh <run-id>              # specific run
#   scripts/ci/check_run_annotations.sh --branch <name>       # latest on a named branch
#   scripts/ci/check_run_annotations.sh --branch <name> --workflow <name>
#                                                             # latest of a specific workflow
#                                                             # on the named branch
#
# Output: per-job annotations grouped by level, plus a summary line.
# Exit code: 0 if no failure-level annotations, 1 otherwise.
#            Warnings (e.g. Node 20 deprecation) are reported but do not fail.

set -euo pipefail

err() { printf 'error: %s\n' "$*" >&2; exit 2; }

command -v gh >/dev/null || err "gh CLI not found"
command -v jq >/dev/null || err "jq not found"

run_id=""
branch=""
workflow=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)
      branch="${2:-}"; [[ -z "$branch" ]] && err "--branch requires a value"
      shift 2
      ;;
    --workflow)
      workflow="${2:-}"; [[ -z "$workflow" ]] && err "--workflow requires a value"
      shift 2
      ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    --)
      shift; break
      ;;
    -*)
      err "unknown flag: $1"
      ;;
    *)
      [[ -n "$run_id" ]] && err "unexpected extra argument: $1"
      run_id="$1"
      shift
      ;;
  esac
done

if [[ -z "$run_id" ]]; then
  if [[ -z "$branch" ]]; then
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    [[ -z "$branch" || "$branch" == "HEAD" ]] && err "could not detect current branch; pass --branch or a run-id"
  fi

  filter='.[0].databaseId'
  if [[ -n "$workflow" ]]; then
    filter='[.[] | select(.name == $w)] | .[0].databaseId'
  fi

  run_id="$(gh run list --branch "$branch" --limit 20 \
                --json databaseId,name \
                --jq "$filter" \
                --arg w "$workflow" 2>/dev/null || true)"

  [[ -z "$run_id" || "$run_id" == "null" ]] && err "no matching run found on branch '$branch'${workflow:+ for workflow '$workflow'}"
fi

repo="$(gh repo view --json nameWithOwner --jq '.nameWithOwner')"

run_meta="$(gh run view "$run_id" --json name,headBranch,event,conclusion,status,url,jobs)"

run_name="$(jq -r '.name'        <<<"$run_meta")"
run_branch="$(jq -r '.headBranch' <<<"$run_meta")"
run_concl="$(jq -r '.conclusion'  <<<"$run_meta")"
run_status="$(jq -r '.status'     <<<"$run_meta")"
run_url="$(jq -r '.url'           <<<"$run_meta")"

printf 'Run %s — %s [%s]\n' "$run_id" "$run_name" "$run_branch"
printf 'Status: %s / Conclusion: %s\n' "$run_status" "${run_concl:-(none)}"
printf 'URL: %s\n\n' "$run_url"

# gh exposes jobs[].databaseId, but annotations live on the check-run resource.
# job.databaseId == check_run.id, so the API path is direct.
totals_failure=0
totals_warning=0
totals_notice=0

while IFS=$'\t' read -r job_id job_name job_concl; do
  ann_json="$(gh api "repos/${repo}/check-runs/${job_id}/annotations" --paginate 2>/dev/null || echo '[]')"
  ann_count="$(jq 'length' <<<"$ann_json")"

  if [[ "$ann_count" -eq 0 ]]; then
    continue
  fi

  printf '── %s [%s] ──\n' "$job_name" "${job_concl:-?}"
  jq -r '.[] | "[\(.annotation_level | ascii_upcase)] \(.path):\(.start_line // 0) — \(.message | gsub("\n"; " ") | .[0:300])"' <<<"$ann_json"
  printf '\n'

  totals_failure=$(( totals_failure + $(jq '[.[] | select(.annotation_level == "failure")] | length' <<<"$ann_json") ))
  totals_warning=$(( totals_warning + $(jq '[.[] | select(.annotation_level == "warning")] | length' <<<"$ann_json") ))
  totals_notice=$((  totals_notice  + $(jq '[.[] | select(.annotation_level == "notice")]  | length' <<<"$ann_json") ))
done < <(jq -r '.jobs[] | [.databaseId, .name, .conclusion] | @tsv' <<<"$run_meta")

printf 'Summary: %d failure, %d warning, %d notice\n' "$totals_failure" "$totals_warning" "$totals_notice"

if [[ "$totals_failure" -gt 0 ]]; then
  exit 1
fi
exit 0
