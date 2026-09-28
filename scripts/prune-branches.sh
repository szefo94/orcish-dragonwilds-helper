#!/usr/bin/env bash
# Prune the reviewed remote branches of szefo94/orcish-dragonwilds-helper.
# Git Bash on Windows: bash scripts/prune-branches.sh [--apply]
# Dry run is the default. --apply creates and verifies an external backup first.
set -euo pipefail

if [[ $# -gt 1 || ( $# -eq 1 && $1 != --apply ) ]]; then
  echo "Usage: bash scripts/prune-branches.sh [--apply]" >&2
  exit 2
fi
apply=0
[[ $# -eq 1 ]] && apply=1

root=$(git rev-parse --show-toplevel)
cd "$root"
remote_url=$(git remote get-url origin)
case "$remote_url" in
  https://github.com/szefo94/orcish-dragonwilds-helper|\
  https://github.com/szefo94/orcish-dragonwilds-helper.git|\
  git@github.com:szefo94/orcish-dragonwilds-helper|\
  git@github.com:szefo94/orcish-dragonwilds-helper.git|\
  ssh://git@github.com/szefo94/orcish-dragonwilds-helper|\
  ssh://git@github.com/szefo94/orcish-dragonwilds-helper.git) ;;
  *) echo "Refusing: origin is $remote_url" >&2; exit 1 ;;
esac

# Fetch every branch, including in clones configured with a single-branch refspec.
git fetch --prune origin '+refs/heads/*:refs/remotes/origin/*'

branches=$(cat <<'BRANCHES'
aim-capture-motion-fixes 5ca2c1372282a05fcc422a4112e3260d3cc0163f
aim-lab-scout-fusion da2eb703066bb78be24ce994383ca25925e01c44
audit-context-reimplementation e3c6751e7082c0a7c6288e3f30b262cf138dca88
cache-wingdk-target-for-recovery 11ee47eb7c95e61231edad4269d3da5f857b0821
claude/dragonwilds-repo-onboarding-e98nsl a98ee22ab67c8fa0709a33cdef9f101fcc5a5ca1
docs/llm-context-hygiene f0f0caa44d33475202682db5bb178c11cd7c944c
experimental-ue4ss-wingdk-recovery 42cbc3201855e4ae4ab76e7ff0931bfe70a1b6ed
fishing-active-status 5d9584479e35498ac8207028afbebbc2f29e3440
fishing-bot-101 24b320421b018e7024bb36ae7b6a940834bb64e7
fishing-burndown-bar 8c72b4b3fea14f614647deb33adb01730c7a0a65
fishing-fast-signals d529965162d03c2423ccf7552e9d4a1561b12f92
fishing-hold-until-transition 7de7b9ea5a02b691364f6750a95ff99a962cebcc
fishing-overlay-minimized-status 6e04e6982aadad451ec217b58a6187c6ef13692e
fishing-overlay-toggle ce5f48ddc18a73ae7c3f1bb101b644fa13b172cb
fishing-phase-signals bb0df235b0680e2067b8eeb31c5d6c4f74332d6d
fishing-recurring-active-signal d4440da9638ced5f5aa577aa483be65ada5bfd5f
fishing-recurring-active-signal-v2 eaa4a6ac0d96e113c391fb45b0a046d5c465b774
fishing-reel-priority b00055a7f540559160b8690b516fef88bcd774f0
fishing-show-old-region-while-editing 1ce4633ac9d49af2719c11d87e12cbdba0b16867
fishing-sticky-direction 1691411c2d64ee7cc77033c708bf5ff9e354b3b1
fix/fishing-left-fill-feedback 2db6c878b7a8b1a9f4b0b0cd22e7ff39474d9116
fix/fishing-mss-and-normal-outcomes 31443877962fc76fbde73ee01b27ad8722f8f173
fix/fishing-overlay-dedupe 3b04f543baedfcc9ec2ab782421af2050b28b2eb
fix/fishing-reel-ad-handoff fe57c549d1dc137e1e4d56dbd4bf370d77fe8841
fix/fishing-reel-night-hysteresis 9c38da724c98dd9d639ce8419bdf9cb919898dbe
fix/fishing-session-log-handle c7de879f296072ee886cad3c210ff317e3b37fa0
fix/fishing-session-resilience 63078fb5a796bdb1f6eb14cde9341357165b1aa5
fix-setup-option9-launch 6e6ceb716b17d5c312bd53b4e5fd5a0189ad4a68
fix-telemetry-powershell-parser 8aab96e799cb2b8559df5e5d1b05140ca6830850
fix-win-gdk-elevation-target bb6be8898d297d81b3b5ac2b8b0661b99b158866
four-corner-overlay 072d3b999ee5c1305f5807e241c33aab1f4a9387
github-zip-updater 2a8bc7d216d155a1b8455c3c90c10ecd0131b79a
global-control-bar-telemetry-setup 18dc62ef4967ea1058d5a500025d4fc2321b83fc
improve/fishing-101-observability b7706136d27b672b0a918af4f54209d4e642b60d
lifecycle-reset-cleanup fc7c4eb95c1a4079b1ff8fb6d43933fbc867720b
overlay-resilience-target-hud 58cd7944dd6f485d8b7509cde3e820568056042a
refresh-wingdk-bridge 999b69d5cb473046e00b417025c2a6e1eb742034
scout-analyzer 1e4311191790fdbf8d40b59be79b90b95fc3477e
scout-analyzer-all efbeafd0925aa82823035a00699a945415c41a3e
scout-internal-telemetry 2c48674a6d86812735ec4818c24367b4d840962d
scout-lab-telemetry 142e55c35b38d93c95efb9ecd5c150aa07128dce
scout-latency-overlay-calibration 16477472bf63494b617787bb4278176a2d85e0a1
scout-phase-a-logger cc9ba8f4e385d277ec6db3ad80b62789ffa211aa
scout-research-design 75fe46e4e89a4f5f4088042f4324996b75b2b923
scout-review-camera-comp b8bc12c1e2487155fc5d74dc77408e674ae99319
scout-sample-capture-overlay dc16e1b7b1d33c50a2efd47711e6b5e9a6ae58ac
scout-semantic-candidates c62485e423b3661125fbc07c23c270e9aeb13648
telemetry-installer-repair 56601f54313f58c7f5c63563e4d683a276e6ce99
telemetry-toolkit-installer 32344020c484c7e76745505b047ed5b0b257de23
ue4ss-bridge-startup-events d1f72dfb9de6de067979eadc2a637748bf971bbb
ue4ss-bridge-status-diagnostics 14b832d56bfa283d66849f1b6b03bdcbbb8ec46d
ui-command-center-revamp 1c307a883f3dc76d2b464e941c100fba58eb6308
wingdk-installer-scope-fix f9a2a80b82f78d126ee15838fd9746b3ea35cfce
wingdk-target-support f093b89584848bc3aea281d50ad8ef65e1563abf
BRANCHES
)

# Abort the entire run on stale or missing refs. The push lease checks them again.
while read -r branch expected; do
  [[ -n "$branch" ]] || continue
  [[ "$branch" != main && "$branch" != experimental ]] || {
    echo "Refusing to touch $branch" >&2; exit 1;
  }
  actual=$(git rev-parse --verify "refs/remotes/origin/$branch^{commit}" 2>/dev/null) || {
    echo "Missing origin/$branch" >&2; exit 1;
  }
  [[ "$actual" == "$expected" ]] || {
    echo "Changed origin/$branch: expected $expected, found $actual" >&2; exit 1;
  }
done <<< "$branches"

declare -a tags=(
  "archive/refresh-wingdk-bridge-pr39:999b69d5cb473046e00b417025c2a6e1eb742034"
  "archive/fishing-recurring-active-signal-v1:d4440da9638ced5f5aa577aa483be65ada5bfd5f"
)
for entry in "${tags[@]}"; do
  tag=${entry%%:*}
  expected=${entry#*:}
  remote_tag=$(git ls-remote --tags origin "refs/tags/$tag" | awk -v ref="refs/tags/$tag" '$2 == ref {print $1}')
  [[ -z "$remote_tag" || "$remote_tag" == "$expected" ]] || {
    echo "Remote tag $tag points to $remote_tag; refusing to replace it" >&2; exit 1;
  }
  local_tag=$(git rev-parse --verify "refs/tags/$tag^{commit}" 2>/dev/null || true)
  [[ -z "$local_tag" || "$local_tag" == "$expected" ]] || {
    echo "Local tag $tag points to $local_tag; refusing to replace it" >&2; exit 1;
  }
done

if [[ $apply -eq 0 ]]; then
  echo "Dry run: validated 54 branch heads and archival tags."
  echo "Apply with: bash scripts/prune-branches.sh --apply"
  exit 0
fi

stamp=$(date +%Y%m%d_%H%M%S)
bundle="$(dirname "$root")/orcish-branches-backup-$stamp.bundle"
[[ ! -e "$bundle" ]] || { echo "Backup already exists: $bundle" >&2; exit 1; }
git bundle create "$bundle" --remotes=origin
git bundle verify "$bundle"
bundle_heads=$(git bundle list-heads "$bundle")
while read -r branch expected; do
  [[ -n "$branch" ]] || continue
  ref="refs/remotes/origin/$branch"
  if ! awk -v sha="$expected" -v ref="$ref" '$1 == sha && $2 == ref { found = 1 } END { exit !found }' <<< "$bundle_heads"; then
    echo "Backup lacks $ref at $expected; refusing to delete branches" >&2
    exit 1
  fi
done <<< "$branches"
echo "Verified backup: $bundle"

# Archive two reviewed branch tips as convenient remote tags as well.
for entry in "${tags[@]}"; do
  tag=${entry%%:*}
  expected=${entry#*:}
  git tag "$tag" "$expected" 2>/dev/null || true
  git push origin "refs/tags/$tag:refs/tags/$tag"
done

failed=0
while read -r branch expected; do
  [[ -n "$branch" ]] || continue
  if ! git push origin --force-with-lease="refs/heads/$branch:$expected" ":refs/heads/$branch"; then
    echo "SKIPPED $branch (moved, protected, or push rejected)" >&2
    failed=$((failed + 1))
  fi
done <<< "$branches"

echo "Remaining remote heads:"
git ls-remote --heads origin
echo "Verified backup: $bundle"
[[ $failed -eq 0 ]] || { echo "$failed branches were not deleted" >&2; exit 1; }
