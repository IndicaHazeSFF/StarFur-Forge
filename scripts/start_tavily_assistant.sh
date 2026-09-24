#!/usr/bin/env bash
# Start the trusted-local Tavily search session without saving the API key.
#
# The key is read only into this launcher process, inherited by the Assistant
# process for its lifetime, and unset when that process exits.  It is never
# written to StarFur configuration, a shell history command, or this script.

set -euo pipefail

read_masked_tavily_key() {
  # ``read -s`` is intentionally silent, but a silent paste is confusing in
  # terminal emulators. Show one harmless marker per received character while
  # keeping the key itself out of the display and shell history.
  local character=""
  STARFUR_TAVILY_API_KEY=""
  printf 'Tavily API key: '
  while IFS= read -r -s -n 1 character; do
    # Bash returns an empty value when Enter satisfies ``read -n 1``.
    [[ -z "$character" ]] && break
    case "$character" in
      $'\177'|$'\b')
        if [[ -n "$STARFUR_TAVILY_API_KEY" ]]; then
          STARFUR_TAVILY_API_KEY="${STARFUR_TAVILY_API_KEY%?}"
          printf '\b \b'
        fi
        ;;
      *)
        STARFUR_TAVILY_API_KEY+="$character"
        printf '*'
        ;;
    esac
  done
  printf '\n'
}

if [[ -z "${STARFUR_TAVILY_API_KEY:-}" ]]; then
  read_masked_tavily_key
fi

if [[ -z "${STARFUR_TAVILY_API_KEY:-}" ]]; then
  printf 'A Tavily API key is required to enable Tavily search.\n' >&2
  exit 64
fi

export STARFUR_TAVILY_API_KEY
trap 'unset STARFUR_TAVILY_API_KEY' EXIT

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_dir"
python3 starfur.py assistant --enable-tavily-search "$@"
