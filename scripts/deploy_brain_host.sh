#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
local_app="${project_root}/apps/pulso-brain-host"
remote="${PULSO_UBUNTU_REMOTE:-}"
remote_root="${PULSO_REMOTE_PROJECT_ROOT:-/mnt/linux-data/pulso/repo}"
ssh_key="${PULSO_UBUNTU_SSH_KEY:-${project_root}/.tools/ssh/pulso_ubuntu_ed25519}"

if [[ -z "$remote" ]]; then
  echo "Set PULSO_UBUNTU_REMOTE=user@host before deploying." >&2
  exit 2
fi

if [[ "$remote_root" != /* || "$remote_root" == "/" ]]; then
  echo "PULSO_REMOTE_PROJECT_ROOT must be a specific absolute path" >&2
  exit 2
fi
for required in start.sh stop.sh status.sh supervise.sh run.sh pyproject.toml; do
  if [[ ! -f "${local_app}/${required}" ]]; then
    echo "Missing brain-host release input: ${local_app}/${required}" >&2
    exit 2
  fi
done
if [[ ! -r "$ssh_key" ]]; then
  echo "Missing SSH key: $ssh_key" >&2
  exit 2
fi
command -v python3 >/dev/null || {
  echo "python3 is required to calculate the source digest" >&2
  exit 2
}
command -v rsync >/dev/null || {
  echo "rsync is required" >&2
  exit 2
}
command -v ssh >/dev/null || {
  echo "ssh is required" >&2
  exit 2
}

source_digest="$(python3 - "$local_app" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys

root = Path(sys.argv[1])
digest = sha256()
files = sorted(
    path
    for path in root.rglob("*")
    if path.is_file()
    and ".runtime" not in path.parts
    and "__pycache__" not in path.parts
    and path.suffix != ".pyc"
)
for path in files:
    relative = path.relative_to(root).as_posix().encode("utf-8")
    digest.update(relative)
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
PY
)"
release_id="$(date -u '+%Y%m%dT%H%M%SZ')-${source_digest:0:12}-$$"
release_root="${remote_root}/.releases/pulso-brain-host"
staging="${release_root}/.staging-${release_id}"
release="${release_root}/${release_id}"
active_link="${remote_root}/apps/pulso-brain-host"
next_link="${remote_root}/apps/.pulso-brain-host.next-${release_id}"
ssh_options=(-i "$ssh_key" -o BatchMode=yes -o ConnectTimeout=8)
rsync_ssh="ssh -i ${ssh_key} -o BatchMode=yes -o ConnectTimeout=8"
rsync_filters=(--exclude=.runtime/ --exclude=__pycache__/ --exclude='*.pyc')

ssh "${ssh_options[@]}" "$remote" bash -s -- \
  "$release_root" "$staging" "$release" "$active_link" "$next_link" <<'REMOTE'
set -euo pipefail
release_root="$1"
staging="$2"
release="$3"
active_link="$4"
next_link="$5"

mkdir -p "$release_root" "$(dirname "$active_link")"
if [[ -e "$staging" || -L "$staging" || -e "$release" || -L "$release" ]]; then
  echo "Refusing to reuse an existing release or staging path" >&2
  exit 3
fi
if [[ (-e "$active_link" || -L "$active_link") && ! -L "$active_link" ]]; then
  echo "Refusing to replace non-symlink app path: $active_link" >&2
  exit 3
fi
if [[ -e "$next_link" || -L "$next_link" ]]; then
  echo "Refusing to reuse temporary activation link: $next_link" >&2
  exit 3
fi
mkdir "$staging"
REMOTE

rsync -a --delete "${rsync_filters[@]}" -e "$rsync_ssh" \
  "${local_app}/" "${remote}:${staging}/"

verification="$(rsync -aicn --delete --out-format='%i %n%L' \
  "${rsync_filters[@]}" -e "$rsync_ssh" \
  "${local_app}/" "${remote}:${staging}/")"
if [[ -n "$verification" ]]; then
  echo "Remote checksum verification failed:" >&2
  printf '%s\n' "$verification" >&2
  echo "Staging was preserved for inspection: ${remote}:${staging}" >&2
  exit 4
fi

ssh "${ssh_options[@]}" "$remote" bash -s -- \
  "$staging" "$release" "$active_link" "$next_link" "$release_id" "$source_digest" <<'REMOTE'
set -euo pipefail
staging="$1"
release="$2"
active_link="$3"
next_link="$4"
release_id="$5"
source_digest="$6"

for required in start.sh stop.sh status.sh supervise.sh run.sh pyproject.toml; do
  [[ -f "${staging}/${required}" ]] || {
    echo "Verified staging is missing $required" >&2
    exit 4
  }
done
for executable in start.sh stop.sh status.sh supervise.sh run.sh; do
  [[ -x "${staging}/${executable}" ]] || {
    echo "Verified staging is not executable: $executable" >&2
    exit 4
  }
done

mv "$staging" "$release"
relative_target="../.releases/pulso-brain-host/${release_id}"
ln -s "$relative_target" "$next_link"
mv -Tf "$next_link" "$active_link"
resolved="$(readlink -f "$active_link")"
if [[ "$resolved" != "$release" ]]; then
  echo "Activation verification failed: $active_link resolved to $resolved" >&2
  exit 5
fi
printf 'activated=%s\nrelease=%s\nsource_sha256=%s\n' \
  "$active_link" "$release" "$source_digest"
REMOTE

echo "Deployment activated atomically. No process or simulation was started."
echo "Previous releases remain under ${remote}:${release_root} for explicit rollback."
