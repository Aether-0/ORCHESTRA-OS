#!/usr/bin/env bash
set +e

if [[ $# -lt 4 || $1 != "--label" || $4 != "--" ]]; then
    printf 'usage: %s --label LABEL OUTPUT_DIR -- COMMAND [ARGUMENTS...]\n' "$0" >&2
    exit 2
fi

label=$2
output_dir=$3
shift 4

campaign_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mkdir -p -- "$campaign_dir/$output_dir"

safe_label=$(printf '%s' "$label" | tr '/ ' '__' | tr -cd '[:alnum:]_.-')
timestamp=$(date +%Y%m%d-%H%M%S)
stdout_file="$campaign_dir/$output_dir/${timestamp}-${safe_label}.stdout"
stderr_file="$campaign_dir/$output_dir/${timestamp}-${safe_label}.stderr"

{
    printf 'timestamp=%s\n' "$(date -Iseconds)"
    printf 'working_directory=%s\n' "$PWD"
    printf 'label=%s\n' "$label"
    printf 'command='
    printf '%q ' "$@"
    printf '\nstdout=%s\nstderr=%s\n' "$stdout_file" "$stderr_file"
} >> "$campaign_dir/COMMANDS.log"

"$@" >"$stdout_file" 2>"$stderr_file"
return_code=$?

{
    printf 'return_code=%s\n' "$return_code"
    printf '\n'
} >> "$campaign_dir/COMMANDS.log"

printf 'label=%s\nreturn_code=%s\nstdout=%s\nstderr=%s\n' \
    "$label" "$return_code" "$stdout_file" "$stderr_file"
exit "$return_code"
