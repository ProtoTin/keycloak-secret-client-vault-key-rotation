#!/bin/bash
set -e

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.pi.yml"
VAULT_URL="http://localhost:8200"
KEYCLOAK_URL="http://localhost:8080"

echo "=== CyberVault Pi Deployment ==="

# ── Step 1: Start Vault only ───────────────────────────────────────────────
echo "[1/6] Starting Vault..."
$COMPOSE up -d vault

echo "      Waiting for Vault to respond..."
until curl -s "$VAULT_URL/v1/sys/health" -o /dev/null; do sleep 2; done

# ── Step 2: Initialize or unseal Vault ────────────────────────────────────
INITIALIZED=$(curl -s "$VAULT_URL/v1/sys/init" | jq -r '.initialized')

if [ "$INITIALIZED" = "false" ]; then
    echo "[2/6] Initializing Vault for the first time..."
    INIT=$(curl -s -X POST "$VAULT_URL/v1/sys/init" \
        -H "Content-Type: application/json" \
        -d '{"secret_shares":1,"secret_threshold":1}')

    UNSEAL_KEY=$(echo "$INIT" | jq -r '.keys[0]')
    ROOT_TOKEN=$(echo "$INIT"  | jq -r '.root_token')

    echo "$INIT" | jq '.' > .vault-keys.json
    chmod 600 .vault-keys.json
    echo "      Vault keys saved to .vault-keys.json — back this file up somewhere safe!"
else
    echo "[2/6] Vault already initialized — unsealing..."
    if [ ! -f .vault-keys.json ]; then
        echo "ERROR: .vault-keys.json not found. Cannot unseal."
        exit 1
    fi
    UNSEAL_KEY=$(jq -r '.keys[0]' .vault-keys.json)
    ROOT_TOKEN=$(jq -r '.root_token' .vault-keys.json)
fi

curl -s -X POST "$VAULT_URL/v1/sys/unseal" \
    -H "Content-Type: application/json" \
    -d "{\"key\":\"$UNSEAL_KEY\"}" | jq -r '"      Sealed: \(.sealed)"'

# ── Step 3: Write .env ────────────────────────────────────────────────────
echo "[3/6] Writing .env..."
SECRET_KEY=$(openssl rand -hex 32)
cat > .env <<EOF
VAULT_TOKEN=$ROOT_TOKEN
SECRET_KEY=$SECRET_KEY
EOF
chmod 600 .env

# ── Step 4: Enable KV secrets engine ─────────────────────────────────────
echo "[4/6] Configuring Vault KV engine..."
KV=$(curl -s -H "X-Vault-Token: $ROOT_TOKEN" "$VAULT_URL/v1/sys/mounts" | jq -r '.["secret/"]')
if [ -z "$KV" ] || [ "$KV" = "null" ]; then
    curl -s -X POST "$VAULT_URL/v1/sys/mounts/secret" \
        -H "X-Vault-Token: $ROOT_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"type":"kv","options":{"version":"2"}}' > /dev/null
    echo "      KV v2 secrets engine enabled"
else
    echo "      KV secrets engine already enabled"
fi

# ── Step 5: Start all services ────────────────────────────────────────────
echo "[5/6] Starting all services..."
$COMPOSE up -d

echo "      Waiting for Keycloak (up to 2 minutes)..."
until curl -fs "$KEYCLOAK_URL/realms/master" > /dev/null 2>&1; do sleep 5; done

# ── Step 6: Run Keycloak + Vault setup ───────────────────────────────────
echo "[6/6] Configuring Keycloak and Vault..."
export VAULT_TOKEN="$ROOT_TOKEN"
export KEYCLOAK_URL="$KEYCLOAK_URL"
export VAULT_URL="$VAULT_URL"
bash ./scripts/setup-keycloak-vault.sh

echo ""
echo "✅ Deployment complete!"
echo "   Password manager: https://passwords.tinmoaung.com"
echo "   Keycloak admin:   http://$(hostname -I | awk '{print $1}'):8080  (admin/admin)"
echo ""
echo "⚠️  IMPORTANT: Back up .vault-keys.json — without it you cannot"
echo "   recover your passwords if the Pi is wiped."
