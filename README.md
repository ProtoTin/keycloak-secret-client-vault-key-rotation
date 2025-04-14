# Keycloak Client Secret Rotation with HashiCorp Vault

This project demonstrates automated secret rotation for Keycloak client secrets using HashiCorp Vault. It provides a simple and secure way to automatically rotate client secrets and store them in Vault.

## Prerequisites

- Docker and Docker Compose
- bash shell
- curl
- jq

## Project Components

- **Keycloak**: Identity and Access Management server (running on port 8080)
- **PostgreSQL**: Database backend for Keycloak
- **HashiCorp Vault**: Secret management (running in dev mode on port 8200)
- **Flask Application**: Demo application showing Vault integration (running on port 5001)
- **Rotation Scripts**:
  - `setup-keycloak-vault.sh`: Initial setup and configuration of both Keycloak and Vault
  - `rotate-secrets.sh`: Handles manual and automatic secret rotation

## Quick Start

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd keycloak-secret-client-vault-key-rotation
   ```

2. **Make scripts executable**

   ```bash
   chmod +x scripts/*.sh
   ```

3. **Start the services**

   ```bash
   docker-compose up -d
   ```

4. **Wait for services to be ready** (approximately 30 seconds)
   - Keycloak will be available at: <http://localhost:8080>
   - Vault will be available at: <http://localhost:8200>
   - Flask app will be available at: <http://localhost:5001>
   - Default credentials:
     - Keycloak: admin/admin
     - Vault: Token: root (dev mode)

5. **IMPORTANT: Run the setup script before accessing the Flask app**

   ```bash
   ./scripts/setup-keycloak-vault.sh
   ```

   This script is **required** and must be run before you can log into the Flask app. It will:
   - Create the "demo-realm" in Keycloak
   - Create a new client "demo-client" with:
     - Client Protocol: openid-connect
     - Access Type: confidential
     - Service Accounts Enabled
   - Store the initial client secret in Vault
   - Create a test user (if not already created) in Keycloak:
      - Log in to the Keycloak Admin Console at <http://localhost:8080>
      - Navigate to the "demo-realm"
      - Go to "Users" and click "Add user"
      - Create a user with a username and password
         - Username: testuser
         - Password: testpass
      - Set the password in the "Credentials" tab
      - Enable the "Email verified" option
      - Click "Save"

6. **Access the Flask app**
   - Open <http://localhost:5001> in your browser
   - Log in using the test user credentials created by the setup script:
     - Username: testuser
     - Password: testpass

   > **Note**: If you try to access the Flask app before running the setup script, you will not be able to log in as the required Keycloak configuration and user will not exist.

## Flask Application Integration

The project includes a Flask application that demonstrates how to integrate with Keycloak and Vault:

### Features

- Secure authentication using Keycloak
- Client secret retrieval from Vault
- Status dashboard showing:
  - Vault connection status
  - Keycloak connection status
  - Current secret version
  - User information
  - System status

### Configuration

The Flask app is configured with:

- Vault connection details (address and token)
- Keycloak realm and client settings
- Automatic secret retrieval from Vault

### Environment Variables

The Flask app uses the following environment variables:

```
FLASK_ENV=development
VAULT_ADDR=http://vault:8200
VAULT_TOKEN=root
```

These are set in the `docker-compose.yml` file.

### Usage

1. Access the Flask app at <http://localhost:5001>
2. Log in using your Keycloak credentials (the test user created by the setup script)
3. View the status dashboard showing the integration status

### Authentication Flow

When a user logs into the Flask application:

- The application retrieves the client secret from Vault
- It uses this secret along with the user's credentials to authenticate with Keycloak
- Keycloak verifies the client secret and user credentials
- If valid, Keycloak issues tokens to the application
- The application uses these tokens for subsequent API calls

This process ensures that only your legitimate application can obtain tokens on behalf of users, protecting against impersonation and unauthorized access.

## Secret Rotation

The project supports both manual and automatic secret rotation:

### Manual Rotation

To rotate a client's secret once:

```bash
./scripts/rotate-secrets.sh demo-client
```

### Automatic Rotation

To automatically rotate secrets at specified intervals:

```bash
./scripts/rotate-secrets.sh demo-client auto-rotate [interval_seconds]
```

Examples:

- Rotate every 5 minutes (default):

  ```bash
  ./scripts/rotate-secrets.sh demo-client auto-rotate
  ```

- Rotate every 60 seconds:

  ```bash
  ./scripts/rotate-secrets.sh demo-client auto-rotate 60
  ```

### How the Rotation Script Works

The `rotate-secrets.sh` script performs the following steps:

1. Generates a new random client secret using OpenSSL
2. Gets an admin token from Keycloak
3. Retrieves the client ID from Keycloak
4. Updates the client secret in Keycloak
5. Stores the new secret in Vault under the path `secret/keycloak/clients/<client_id>`

The script is designed to be idempotent, so it can be run multiple times without issues.

## Secret Storage

Secrets are stored in Vault under the following path:

```
secret/data/keycloak/clients/<client_id>
```

The secret is stored with the key `client_secret` in the data object.

To retrieve the current secret from Vault:

```bash
# Using curl
curl --silent \
     -H "X-Vault-Token: root" \
     "http://localhost:8200/v1/secret/data/keycloak/clients/demo-client" | jq -r '.data.data.client_secret'
```

## Architecture

The solution works as follows:

1. The rotation script generates a new secret
2. Updates the client secret in Keycloak using the Admin REST API
3. Stores the new secret in Vault's KV secrets engine
4. Applications can retrieve the current secret from Vault as needed

## Security Considerations

- This setup uses Vault in dev mode with a known root token for simplicity
- In production:
  - Use Vault in production mode with proper initialization
  - Use secure passwords and tokens
  - Enable TLS/SSL
  - Use proper Vault authentication methods
  - Implement proper access controls
  - Use secure network configurations

## Troubleshooting

1. **Services not starting**
   - Check if ports 8080, 8200, or 5432 are in use
   - View logs: `docker-compose logs -f`

2. **Rotation script errors**
   - Ensure all services are running
   - Check Keycloak and Vault are accessible
   - Verify client ID exists in Keycloak
   - Check Vault token is valid

3. **Permission issues**
   - Make sure scripts are executable: `chmod +x scripts/*.sh`

4. **Flask app authentication issues**
   - Ensure you've run the setup script first
   - Check if the client secret is properly stored in Vault
   - Verify Keycloak client configuration
   - Check Flask app logs: `docker-compose logs status-app`
   - Ensure you're using the test user credentials created by the setup script

## Clean Up

To stop and remove all containers:

```bash
docker-compose down
```

To also remove volumes:

```bash
docker-compose down -v
```
