#!/bin/bash
# Runs on boot to unseal Vault after a restart.
# Install: add to crontab with:  @reboot sleep 30 && /home/piadmin/cybervault/scripts/vault-unseal.sh

VAULT_URL="http://localhost:8200"
KEYS_FILE="$(dirname "$0")/../.vault-keys.json"

if [ ! -f "$KEYS_FILE" ]; then
    echo "vault-unseal: .vault-keys.json not found, skipping"
    exit 1
fi

UNSEAL_KEY=$(jq -r '.keys[0]' "$KEYS_FILE")

until curl -s "$VAULT_URL/v1/sys/health" -o /dev/null; do
    sleep 5
done

SEALED=$(curl -s "$VAULT_URL/v1/sys/health" | jq -r '.sealed')
if [ "$SEALED" = "true" ]; then
    curl -s -X POST "$VAULT_URL/v1/sys/unseal" \
        -H "Content-Type: application/json" \
        -d "{\"key\":\"$UNSEAL_KEY\"}" > /dev/null
    echo "vault-unseal: Vault unsealed at $(date)"
else
    echo "vault-unseal: Vault already unsealed"
fi
