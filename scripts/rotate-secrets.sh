#!/bin/bash

# Set environment variables
export VAULT_ADDR="http://localhost:8200"
export VAULT_TOKEN="root"
export KEYCLOAK_URL="http://localhost:8080"
export KEYCLOAK_REALM="demo-realm"

# Set to false to disable debug output
DEBUG=false

# Default rotation interval in seconds
DEFAULT_INTERVAL=300  # 5 minutes

# Function to log messages with timestamp (only for errors)
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >&2
}

# Function to log debug messages (disabled)
log_debug() {
    if [ "$DEBUG" = true ]; then
        echo "$1" >&2
    fi
}

# Function to get admin token
get_admin_token() {
    local token=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=admin" \
        -d "password=admin" \
        -d "grant_type=password" \
        -d "client_id=admin-cli" | jq -r '.access_token')
    
    if [ -z "$token" ]; then
        log "Failed to get admin token"
        exit 1
    fi
    
    echo "$token"
}

# Function to generate a client secret
generate_client_secret() {
    openssl rand -base64 32
}

# Function to store client secret in Vault
store_client_secret() {
    local client_id=$1
    local client_secret=$2
    
    # Create properly escaped JSON with just the secret value
    local json_data=$(jq -n --arg value "$client_secret" '{"data":{"client_secret":$value}}')
    
    # Store only the secret value
    local response=$(curl -s -X POST \
        -H "X-Vault-Token: $VAULT_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$json_data" \
        "$VAULT_ADDR/v1/secret/data/keycloak/clients/$client_id")
    
    # Check if the response contains "version" which indicates success
    if ! echo "$response" | grep -q "version"; then
        log "Failed to store secret in Vault: $response"
        exit 1
    fi
}

# Function to update client secret in Keycloak
update_keycloak_client_secret() {
    local client_id=$1
    local new_secret=$2
    local admin_token=$3
    
    # Get client UUID silently
    local clients_json=$(curl -s "$KEYCLOAK_URL/admin/realms/$KEYCLOAK_REALM/clients" \
        -H "Authorization: Bearer $admin_token")
    
    local client_uuid=$(echo "$clients_json" | jq -r ".[] | select(.clientId==\"$client_id\") | .id")
    
    if [ -z "$client_uuid" ]; then
        log "Failed to get client UUID for client ID: $client_id"
        exit 1
    fi
    
    # Update client secret silently
    local response=$(curl -s -X PUT "$KEYCLOAK_URL/admin/realms/$KEYCLOAK_REALM/clients/$client_uuid" \
        -H "Authorization: Bearer $admin_token" \
        -H "Content-Type: application/json" \
        -d "{\"secret\":\"$new_secret\"}")
    
    # Check if the response is empty which indicates success
    if [ -z "$response" ]; then
        echo "$new_secret"
    else
        log "Failed to update client secret in Keycloak: $response"
        exit 1
    fi
}

# Function to rotate client secret
rotate_client_secret() {
    local client_id=$1
    local new_secret=$(generate_client_secret)
    local admin_token=$(get_admin_token)
    
    # Update in Keycloak and get the actual secret
    local actual_secret=$(update_keycloak_client_secret "$client_id" "$new_secret" "$admin_token")
    
    # Store only the secret in Vault
    store_client_secret "$client_id" "$actual_secret"
    
    # Display success message
    echo "✅ Secret key successfully rotated"
}

# Function to auto-rotate secrets at specified interval
auto_rotate_secret() {
    local client_id=$1
    local interval=${2:-$DEFAULT_INTERVAL}
    
    echo "Starting auto-rotation for client '$client_id' every $interval seconds"
    echo "Press Ctrl+C to stop"
    
    while true; do
        rotate_client_secret "$client_id"
        sleep "$interval"
    done
}

# Main execution
if [ -z "$1" ]; then
    log "Usage: $0 <client_id> [auto-rotate] [interval_seconds]"
    log "  auto-rotate: Optional. If specified, will continuously rotate secrets"
    log "  interval_seconds: Optional. Interval between rotations (default: 300 seconds)"
    exit 1
fi

# Check if auto-rotation is requested
if [ "$2" = "auto-rotate" ]; then
    auto_rotate_secret "$1" "${3:-$DEFAULT_INTERVAL}"
else
    # Single rotation
    rotate_client_secret "$1"
fi 