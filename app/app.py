from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from keycloak import KeycloakOpenID
import hvac
import os
from datetime import datetime
from dotenv import load_dotenv
from functools import wraps
import requests
import subprocess

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Keycloak settings
keycloak_settings = {
    "server_url": "http://keycloak:8080/",
    "realm_name": "demo-realm",
    "client_id": None,  # Will be determined from the session or environment
    "client_secret_key": None  # Will be fetched from Vault
}

# Vault settings
vault_settings = {
    "url": "http://vault:8200",
    "token": "root"
}

def get_vault_client():
    client = hvac.Client(
        url=vault_settings["url"],
        token=vault_settings["token"],
        verify=False  # Allow insecure connection in development
    )
    print(f"Created Vault client with URL: {vault_settings['url']}")
    return client

def get_client_secret_from_vault(client_id=None):
    client = get_vault_client()
    try:
        # Use provided client_id or get from session
        if client_id is None:
            token_info = session.get('token', {})
            client_id = token_info.get('client_id')
            
            # If still None, try to get from environment variable
            if client_id is None:
                client_id = os.environ.get('DEFAULT_CLIENT_ID')
                
            # If still None, use a fallback
            if client_id is None:
                client_id = "demo-client"
                
        print(f"Attempting to read secret from Vault at path: keycloak/clients/{client_id}")
        
        # First, check if the secret exists
        try:
            secret = client.secrets.kv.v2.read_secret_version(
                path=f'keycloak/clients/{client_id}',
                mount_point='secret'
            )
            print(f"Successfully retrieved secret from Vault for client: {client_id}")
            return secret['data']['data']['client_secret']
        except Exception as e:
            print(f"Secret not found for client {client_id}: {str(e)}")
            # Return None 
            return None
    except Exception as e:
        print(f"Error fetching secret from Vault for client {client_id}: {str(e)}")
        print(f"Vault URL: {vault_settings['url']}")
        print(f"Vault token: {vault_settings['token'][:5]}...")  # Only print first 5 chars for security
        return None

def get_keycloak_client(client_id):
    if not client_id:
        raise Exception("Client ID is required")
            
    client_secret = get_client_secret_from_vault(client_id)
    if not client_secret:
        # Log a clear error message
        print(f"ERROR: Client secret not found in Vault for client: {client_id}")
        # You could either raise an exception or handle it differently
        raise Exception(f"Client secret not found in Vault for client: {client_id}")
    
    return KeycloakOpenID(
        server_url=keycloak_settings["server_url"],
        client_id=client_id,
        realm_name=keycloak_settings["realm_name"],
        client_secret_key=client_secret
    )

def get_keycloak_admin_client():
    """Get a Keycloak admin client to access the admin API"""
    try:
        # Get admin token
        admin_token = requests.post(
            f"{keycloak_settings['server_url']}realms/master/protocol/openid-connect/token",
            data={
                "username": "admin",
                "password": "admin",
                "grant_type": "password",
                "client_id": "admin-cli"
            }
        ).json()
        
        return admin_token.get('access_token')
    except Exception as e:
        print(f"Error getting admin token: {str(e)}")
        return None

def get_keycloak_clients():
    """Get list of clients from Keycloak"""
    admin_token = get_keycloak_admin_client()
    if not admin_token:
        return []
    
    try:
        # Get clients from Keycloak
        response = requests.get(
            f"{keycloak_settings['server_url']}admin/realms/{keycloak_settings['realm_name']}/clients",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting clients: {response.text}")
            return []
    except Exception as e:
        print(f"Error getting clients: {str(e)}")
        return []

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'token' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            # Get list of available clients from Keycloak
            clients = get_keycloak_clients()
            
            # Try to authenticate with each client
            for client_info in clients:
                client_id = client_info.get('clientId')
                if not client_id:
                    continue
                    
                try:
                    # Get the client secret from Vault first
                    client_secret = get_client_secret_from_vault(client_id)
                    if not client_secret:
                        print(f"No secret found in Vault for client {client_id}")
                        continue
                        
                    # Try to authenticate with this client
                    keycloak_client = KeycloakOpenID(
                        server_url=keycloak_settings["server_url"],
                        client_id=client_id,
                        realm_name=keycloak_settings["realm_name"],
                        client_secret_key=client_secret
                    )
                    
                    token = keycloak_client.token(username=username, password=password)
                    
                    # If we get here, authentication was successful
                    print(f"Authentication successful for user: {username} with client: {client_id}")
                    
                    # Store token and user info in session with client_id in token info
                    token['client_id'] = client_id  # Add client_id to token info
                    session['token'] = token
                    session['username'] = username
                    session['client_id'] = client_id
                    
                    return redirect(url_for('index'))
                except Exception as e:
                    # Authentication failed with this client, try the next one
                    print(f"Authentication failed with client {client_id}: {str(e)}")
                    continue
            
            # If we get here, authentication failed with all clients
            return render_template('login.html', error="Login failed: Invalid username or password")
        except Exception as e:
            print(f"Error during login: {str(e)}")
            return render_template('login.html', error=f"Login failed: {str(e)}")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('token', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    try:
        # Get user info from token
        token_info = session.get('token', {})
        access_token = token_info.get('access_token')
        
        # Get client_id from token info first, then session, then environment
        current_client_id = token_info.get('client_id')
        if not current_client_id:
            current_client_id = session.get('client_id')
        if not current_client_id:
            current_client_id = os.environ.get('DEFAULT_CLIENT_ID', 'demo-client')
            
        # Store the client_id in the session for future use
        session['client_id'] = current_client_id
        
        # Get Keycloak client for the current client
        keycloak_client = get_keycloak_client(current_client_id)
        
        # Get user info from token
        user_info = keycloak_client.userinfo(token=access_token)
        
        # Get list of clients from Keycloak
        clients = get_keycloak_clients()
        
        # Get current secret from Vault with no caching
        client = get_vault_client()
        
        # Get secrets for all clients
        client_secrets = {}
        for client_info in clients:
            client_id = client_info.get('clientId')
            if client_id:
                try:
                    secret_info = client.secrets.kv.v2.read_secret_version(
                        path=f'keycloak/clients/{client_id}',
                        mount_point='secret',
                        version=None  # This ensures we get the latest version
                    )
                    
                    # Get secret metadata with no caching
                    secret_metadata = client.secrets.kv.v2.read_secret_metadata(
                        path=f'keycloak/clients/{client_id}',
                        mount_point='secret'
                    )
                    
                    client_secrets[client_id] = {
                        'version': secret_metadata.get('data', {}).get('current_version', 'Unknown'),
                        'created': secret_metadata.get('data', {}).get('created_time', 'Unknown'),
                        'secret': secret_info.get('data', {}).get('data', {}).get('client_secret', 'Unknown'),
                        'is_current': client_id == current_client_id
                    }
                except Exception as e:
                    print(f"Error getting secret for client {client_id}: {str(e)}")
                    client_secrets[client_id] = {
                        'version': 'Unknown',
                        'created': 'Unknown',
                        'secret': 'Unknown',
                        'is_current': client_id == current_client_id
                    }
        
        status = {
            'vault_connected': True,
            'keycloak_connected': True,
            'secret_last_fetched': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'token_works': True,
            'user_info': {
                'username': user_info.get('preferred_username', 'Unknown'),
                'email': user_info.get('email', 'Not provided'),
                'name': user_info.get('name', 'Not provided'),
                'roles': user_info.get('realm_access', {}).get('roles', []),
                'client_id': current_client_id
            },
            'system_info': {
                'vault_status': 'Healthy',
                'keycloak_status': 'Connected',
                'current_client': {
                    'id': current_client_id,
                    'secret_version': client_secrets.get(current_client_id, {}).get('version', 'Unknown'),
                    'secret_created': client_secrets.get(current_client_id, {}).get('created', 'Unknown')
                }
            },
            'clients': client_secrets
        }
    except Exception as e:
        status = {
            'vault_connected': False,
            'keycloak_connected': False,
            'error': str(e),
            'user_info': {
                'username': session.get('username', 'Unknown'),
                'email': 'Not available',
                'name': 'Not available',
                'roles': [],
                'client_id': current_client_id
            },
            'system_info': {
                'vault_status': 'Unhealthy',
                'keycloak_status': 'Disconnected',
                'current_client': {
                    'id': current_client_id,
                    'secret_version': 'Unknown',
                    'secret_created': 'Unknown'
                }
            },
            'clients': {}
        }
    
    return render_template('index.html', status=status)

@app.route('/health')
def health():
    try:
        # Get client_id from query parameters or use default
        client_id = request.args.get('client_id', keycloak_settings['client_id'])
        client_secret = get_client_secret_from_vault(client_id)
        keycloak_client = get_keycloak_client(client_id)
        
        return jsonify({
            'status': 'healthy',
            'vault_connected': True,
            'keycloak_connected': True,
            'secret_rotation_working': True if client_secret else False,
            'client_id': client_id
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/rotate-secret', methods=['POST'])
@login_required
def rotate_secret():
    try:
        # Get client_id from request
        data = request.get_json()
        if not data or 'client_id' not in data:
            return jsonify({
                'success': False,
                'message': 'client_id is required in the request body'
            }), 400
        
        client_id = data['client_id']
        
        # Execute the rotation script with the specified client_id
        result = subprocess.run(['/app/scripts/rotate-secrets.sh', client_id], 
                              capture_output=True, 
                              text=True)
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'message': f'Secret rotation completed successfully for client {client_id}',
                'details': result.stdout
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Secret rotation failed for client {client_id}',
                'details': result.stderr
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 