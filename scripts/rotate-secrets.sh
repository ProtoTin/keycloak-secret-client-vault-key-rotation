#!/bin/bash

# Set environment variables
# Use environment variables if set, otherwise use defaults
# Check if running inside Docker container
if [ -f /.dockerenv ]; then
    # Running inside Docker
    export VAULT_ADDR=${VAULT_ADDR:-"http://vault:8200"}
    export KEYCLOAK_URL=${KEYCLOAK_URL:-"http://keycloak:8080"}
else
    # Running on host machine
    export VAULT_ADDR=${VAULT_ADDR:-"http://localhost:8200"}
    export KEYCLOAK_URL=${KEYCLOAK_URL:-"http://localhost:8080"}
fi

export VAULT_TOKEN=${VAULT_TOKEN:-"root"}
export KEYCLOAK_REALM=${KEYCLOAK_REALM:-"demo-realm"}

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
    
    # Create JSON with client_secret and timestamp
    local json_data=$(jq -n \
        --arg secret "$client_secret" \
        --arg time "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
        '{"data":{"client_secret":$secret, "timestamp":$time}}')
    
    # Store the data and redirect output to /dev/null
    curl -s -X POST \
        -H "X-Vault-Token: $VAULT_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$json_data" \
        "$VAULT_ADDR/v1/secret/data/keycloak/clients/$client_id" > /dev/null
    
    # Check if the command was successful
    if [ $? -ne 0 ]; then
        log "Failed to store secret in Vault for client: $client_id"
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
    
    # First get the current client configuration
    local client_config=$(curl -s "$KEYCLOAK_URL/admin/realms/$KEYCLOAK_REALM/clients/$client_uuid" \
        -H "Authorization: Bearer $admin_token")
    
    # Update only the secret in the client configuration
    local updated_config=$(echo "$client_config" | jq --arg secret "$new_secret" '.secret = $secret')
    
    # Update client with the new configuration
    local response=$(curl -s -X PUT "$KEYCLOAK_URL/admin/realms/$KEYCLOAK_REALM/clients/$client_uuid" \
        -H "Authorization: Bearer $admin_token" \
        -H "Content-Type: application/json" \
        -d "$updated_config")
    
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
    echo "✅ Secret key successfully rotated for client: $client_id"
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