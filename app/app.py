from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from keycloak import KeycloakOpenID
import hvac
import os
import uuid
import string
import secrets as crypto_secrets
import re
from datetime import datetime
from dotenv import load_dotenv
from functools import wraps
import requests
import subprocess

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production')

rotation_history = []

# Keycloak settings
keycloak_settings = {
    "server_url": "http://keycloak:8080/",
    "realm_name": "demo-realm",
    "client_id": None,  # Will be determined from the session or environment
    "client_secret_key": None  # Will be fetched from Vault
}

# Vault settings
vault_settings = {
    "url": os.environ.get('VAULT_ADDR', 'http://vault:8200'),
    "token": os.environ.get('VAULT_TOKEN', 'root')
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

        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', client_id):
            return jsonify({
                'success': False,
                'message': 'Invalid client_id format'
            }), 400

        # Execute the rotation script with the specified client_id
        result = subprocess.run(['/app/scripts/rotate-secrets.sh', client_id],
                              capture_output=True, 
                              text=True)
        
        if result.returncode == 0:
            rotation_history.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'client_id': client_id,
                'rotated_by': session.get('username', 'unknown'),
                'status': 'success'
            })
            return jsonify({
                'success': True,
                'message': f'Secret rotation completed successfully for client {client_id}',
                'details': result.stdout
            })
        else:
            rotation_history.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'client_id': client_id,
                'rotated_by': session.get('username', 'unknown'),
                'status': 'failed'
            })
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

@app.route('/rotation-history')
@login_required
def get_rotation_history():
    return jsonify(list(reversed(rotation_history[-50:])))


# ── Password Manager ──────────────────────────────────────────────────────────

def _pw_path(username, entry_id=''):
    path = f'passwords/{username}'
    return f'{path}/{entry_id}' if entry_id else path

def _list_pw_keys(username, vault_client):
    try:
        result = vault_client.secrets.kv.v2.list_secrets(
            path=_pw_path(username), mount_point='secret'
        )
        return result['data']['keys']
    except Exception:
        return []

def _validate_entry_id(entry_id):
    return bool(re.match(r'^[a-f0-9-]{36}$', entry_id))

@app.route('/passwords')
@login_required
def passwords_page():
    username = session.get('username')
    vault_client = get_vault_client()
    entries = []
    for key in _list_pw_keys(username, vault_client):
        try:
            data = vault_client.secrets.kv.v2.read_secret_version(
                path=_pw_path(username, key), mount_point='secret'
            )['data']['data']
            entries.append({
                'id': key,
                'site_name': data.get('site_name', ''),
                'url': data.get('url', ''),
                'username': data.get('username', ''),
                'notes': data.get('notes', ''),
                'updated_at': data.get('updated_at', data.get('created_at', '')),
            })
        except Exception:
            pass
    entries.sort(key=lambda x: x['site_name'].lower())
    return render_template('passwords.html', entries=entries, user=session.get('username'))

@app.route('/api/passwords', methods=['POST'])
@login_required
def api_create_password():
    data = request.get_json()
    if not data or not data.get('site_name') or not data.get('password'):
        return jsonify({'success': False, 'message': 'site_name and password are required'}), 400
    username = session.get('username')
    entry_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    get_vault_client().secrets.kv.v2.create_or_update_secret(
        path=_pw_path(username, entry_id),
        secret={
            'site_name': data.get('site_name', ''),
            'url': data.get('url', ''),
            'username': data.get('username', ''),
            'password': data['password'],
            'notes': data.get('notes', ''),
            'created_at': now,
            'updated_at': now,
        },
        mount_point='secret'
    )
    return jsonify({'success': True, 'id': entry_id})

@app.route('/api/passwords/<entry_id>', methods=['GET'])
@login_required
def api_get_password(entry_id):
    if not _validate_entry_id(entry_id):
        return jsonify({'success': False, 'message': 'Invalid entry ID'}), 400
    username = session.get('username')
    try:
        data = get_vault_client().secrets.kv.v2.read_secret_version(
            path=_pw_path(username, entry_id), mount_point='secret'
        )['data']['data']
        return jsonify(data)
    except Exception:
        return jsonify({'success': False, 'message': 'Not found'}), 404

@app.route('/api/passwords/<entry_id>', methods=['PUT'])
@login_required
def api_update_password(entry_id):
    if not _validate_entry_id(entry_id):
        return jsonify({'success': False, 'message': 'Invalid entry ID'}), 400
    data = request.get_json()
    if not data or not data.get('site_name') or not data.get('password'):
        return jsonify({'success': False, 'message': 'site_name and password are required'}), 400
    username = session.get('username')
    vault_client = get_vault_client()
    try:
        existing = vault_client.secrets.kv.v2.read_secret_version(
            path=_pw_path(username, entry_id), mount_point='secret'
        )['data']['data']
        created_at = existing.get('created_at', datetime.now().isoformat())
    except Exception:
        return jsonify({'success': False, 'message': 'Not found'}), 404
    vault_client.secrets.kv.v2.create_or_update_secret(
        path=_pw_path(username, entry_id),
        secret={
            'site_name': data.get('site_name', ''),
            'url': data.get('url', ''),
            'username': data.get('username', ''),
            'password': data['password'],
            'notes': data.get('notes', ''),
            'created_at': created_at,
            'updated_at': datetime.now().isoformat(),
        },
        mount_point='secret'
    )
    return jsonify({'success': True})

@app.route('/api/passwords/<entry_id>', methods=['DELETE'])
@login_required
def api_delete_password(entry_id):
    if not _validate_entry_id(entry_id):
        return jsonify({'success': False, 'message': 'Invalid entry ID'}), 400
    username = session.get('username')
    try:
        get_vault_client().secrets.kv.v2.delete_metadata_and_all_versions(
            path=_pw_path(username, entry_id), mount_point='secret'
        )
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/passwords/generate')
@login_required
def api_generate_password():
    length = min(max(int(request.args.get('length', 20)), 8), 64)
    chars = ''
    if request.args.get('upper', 'true') == 'true':   chars += string.ascii_uppercase
    if request.args.get('lower', 'true') == 'true':   chars += string.ascii_lowercase
    if request.args.get('digits', 'true') == 'true':  chars += string.digits
    if request.args.get('symbols', 'true') == 'true': chars += '!@#$%^&*()_+-=[]{}|;:,.<>?'
    if not chars:
        chars = string.ascii_letters + string.digits
    return jsonify({'password': ''.join(crypto_secrets.choice(chars) for _ in range(length))})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 