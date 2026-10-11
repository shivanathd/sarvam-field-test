#!/bin/bash
# Writes a publishable copy of this folder to $1 (default ../sarvam-field-test-public):
# drops secrets, model weights, audio and downloads; replaces your home path and username; then scans for leaks.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:-../sarvam-field-test-public}
rm -rf "$OUT" && mkdir -p "$OUT"
rsync -a --exclude-from=.gitignore --exclude '.git/' --exclude '.venv' ./ "$OUT/"
cd "$OUT"
(LC_ALL=C grep -rIl "$HOME" . || true) | while read -r f; do perl -pi -e "s#\Q$HOME\E#~#g" "$f"; done
(LC_ALL=C grep -rIl "$(whoami)" . || true) | while read -r f; do perl -pi -e "s#$(whoami)#user#g" "$f"; done
if grep -rIqE '(sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{30,}|sk_[A-Za-z0-9]{30,})' .; then
  echo "possible secret found; not safe to publish" >&2; exit 1
fi
echo "public copy ready: $OUT ($(du -sh . | cut -f1), $(find . -type f | wc -l | tr -d ' ') files)"
