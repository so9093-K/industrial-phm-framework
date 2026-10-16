#!/bin/sh
# Unpack the source snapshot streamed on stdin and run the requested verification stages.
set -eu
tar -xf - -C "$HOME/work" --no-same-owner --warning=no-unknown-keyword
cd "$HOME/work"
exec sh tools/verify/gate.sh "$@"
