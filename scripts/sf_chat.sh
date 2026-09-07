#!/usr/bin/env bash
# Send one local StarFur chat/Core-command request through the API.
#
# This is intentionally a presentation/client convenience only. Conversation
# isolation, command dispatch, and all persistence rules remain Core-owned.

set -euo pipefail

if [[ $# -lt 2 ]]; then
  printf 'Usage: %s <conversation-id> <message...>\n' "${0##*/}" >&2
  exit 64
fi

if ! command -v curl >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
  printf '%s requires curl and jq.\n' "${0##*/}" >&2
  exit 69
fi

conversation_id=$1
shift
message=$*
api_base=${STARFUR_API_BASE:-http://127.0.0.1:8001/v1}
api_key=${STARFUR_API_KEY:-starfur-local}

payload=$(jq -n --arg content "$message" '{
  model: "starfur-assistant",
  messages: [{role: "user", content: $content}]
}')

curl --silent --show-error --fail-with-body -X POST \
  -H "Authorization: Bearer ${api_key}" \
  -H "X-StarFur-Conversation: ${conversation_id}" \
  -H 'Content-Type: application/json' \
  "${api_base}/chat/completions" \
  --data-binary "$payload" \
  | jq --raw-output '.choices[0].message.content // .error.message // .'
