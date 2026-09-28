#!/usr/bin/env bash
# Usage: ./run_cmd.sh name < body.py   — queue a command for driver.py and wait for its output.
set -e
dir="${BHULEKH_DATA:-$(dirname "$0")/private}/out/cmd"; name="$1"
cat > "$dir/$name.tmp" && mv "$dir/$name.tmp" "$dir/$name.py"
for _ in $(seq 1 ${WAIT:-600}); do [ -f "$dir/$name.out" ] && { cat "$dir/$name.out"; exit 0; }; sleep 1; done
echo "timeout waiting for $name"; exit 1
