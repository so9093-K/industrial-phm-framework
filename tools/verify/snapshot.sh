#!/bin/sh
# Stream the working tree as git sees it (tracked and untracked, never ignored) as a tar,
# so uncommitted changes are verified without the host's build outputs or virtualenvs.
set -eu
cd "$(dirname "$0")/../.."
git ls-files --cached --others --exclude-standard | while IFS= read -r path; do
  [ -f "$path" ] && printf '%s\n' "$path"
done | COPYFILE_DISABLE=1 tar -cf - -T -
