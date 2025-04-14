#!/bin/bash

# Set environment variables
KEYCLOAK_URL="http://localhost:8080"
VAULT_URL="http://localhost:8200"
VAULT_TOKEN="root"

# Wait for Vault to be ready
echo "Waiting for Vault to be ready..."
until curl -fs "$VAULT_URL/v1/sys/health" > /dev/null; do
    echo "Waiting for Vault..."
    sleep 5
done

# Check if KV secrets engine is enabled
echo "Checking KV secrets engine..."
KV_ENABLED=$(curl -s "$VAULT_URL/v1/sys/mounts" \
    -H "X-Vault-Token: $VAULT_TOKEN" | jq -r '.["secret/"]')

if [ -z "$KV_ENABLED" ]; then
    echo "Enabling KV secrets engine..."
    curl -s -X POST "$VAULT_URL/v1/sys/mounts/secret" \
        -H "X-Vault-Token: $VAULT_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"type": "kv", "options": {"version": "2"}}'
    
    if [ $? -eq 0 ]; then
        echo "KV secrets engine enabled successfully"
    else
        echo "Failed to enable KV secrets engine"
        exit 1
    fi
else
    echo "KV secrets engine already enabled"
fi

# Wait for Keycloak to be ready
echo "Waiting for Keycloak to be ready..."
until curl -fs "$KEYCLOAK_URL/realms/master" > /dev/null; do
    echo "Waiting for Keycloak..."
    sleep 5
done

# Get admin token
echo "Getting admin token..."
ADMIN_TOKEN=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=admin" \
    -d "password=admin" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" | jq -r '.access_token')

if [ -z "$ADMIN_TOKEN" ]; then
    echo "Failed to get admin token"
    exit 1
fi

# Check if realm exists
echo "Checking if realm exists..."
REALM_EXISTS=$(curl -s "$KEYCLOAK_URL/admin/realms" \
    -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.[] | select(.realm=="demo-realm") | .realm')

if [ -z "$REALM_EXISTS" ]; then
    # Create new realm
    echo "Creating new realm..."
    REALM_RESPONSE=$(curl -s -X POST "$KEYCLOAK_URL/admin/realms" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
            "realm": "demo-realm",
            "enabled": true,
            "displayName": "Demo Realm"
        }')

    if [ ! -z "$REALM_RESPONSE" ]; then
        echo "Failed to create realm: $REALM_RESPONSE"
        exit 1
    fi
    echo "Realm created successfully"
else
    echo "Realm 'demo-realm' already exists, skipping creation"
fi

# Check if client exists
echo "Checking if client exists..."
CLIENT_EXISTS=$(curl -s "$KEYCLOAK_URL/admin/realms/demo-realm/clients" \
    -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.[] | select(.clientId=="demo-client") | .clientId')

if [ -z "$CLIENT_EXISTS" ]; then
    # Create client
    echo "Creating client..."
    CLIENT_RESPONSE=$(curl -s -X POST "$KEYCLOAK_URL/admin/realms/demo-realm/clients" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
            "clientId": "demo-client",
            "enabled": true,
            "publicClient": false,
            "redirectUris": ["http://localhost:3000/*"],
            "webOrigins": ["http://localhost:3000"]
        }')

    if [ ! -z "$CLIENT_RESPONSE" ]; then
        echo "Failed to create client: $CLIENT_RESPONSE"
        exit 1
    fi
    echo "Client created successfully"
else
    echo "Client 'demo-client' already exists, skipping creation"
fi

# Get client ID
CLIENT_ID=$(curl -s "$KEYCLOAK_URL/admin/realms/demo-realm/clients" \
    -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.[] | select(.clientId=="demo-client") | .id')

if [ -z "$CLIENT_ID" ]; then
    echo "Failed to get client ID"
    exit 1
fi

# Get client secret
CLIENT_SECRET=$(curl -s "$KEYCLOAK_URL/admin/realms/demo-realm/clients/$CLIENT_ID/client-secret" \
    -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.value')

if [ -z "$CLIENT_SECRET" ]; then
    echo "Failed to get client secret"
    exit 1
fi

# Store initial client secret in Vault
echo "Storing initial client secret in Vault..."
# Redirect the output to /dev/null to suppress the verbose JSON response
curl -s -X POST "$VAULT_URL/v1/secret/data/keycloak/clients/demo-client" \
    -H "X-Vault-Token: $VAULT_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"data\": {
            \"client_secret\": \"$CLIENT_SECRET\",
            \"timestamp\": \"$(date -u +"%Y-%m-%dT%H:%M:%SZ")\"
        }
    }" > /dev/null

if [ $? -eq 0 ]; then
    echo "Initial client secret stored in Vault successfully"
else
    echo "Failed to store initial client secret in Vault"
    exit 1
fi

echo "Setup completed!"
echo "Realm: demo-realm"
echo "Client ID: demo-client"
echo "Client Secret initialized in Keycloak" 