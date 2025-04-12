from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from keycloak import KeycloakOpenID
import hvac
import os
from datetime import datetime
from dotenv import load_dotenv
from functools import wraps

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Keycloak settings
keycloak_settings = {
    "server_url": "http://keycloak:8080/",
    "realm_name": "demo-realm",
    "client_id": "demo-client",
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

def get_client_secret_from_vault():
    client = get_vault_client()
    try:
        print(f"Attempting to read secret from Vault at path: keycloak/clients/demo-client")
        # First, check if the secret exists
        try:
            secret = client.secrets.kv.v2.read_secret_version(
                path='keycloak/clients/demo-client',
                mount_point='secret'
            )
            print("Successfully retrieved secret from Vault")
            return secret['data']['data']['client_secret']
        except Exception as e:
            print(f"Secret not found, creating a new one...")
            # If the secret doesn't exist, create it with a dummy value
            client.secrets.kv.v2.create_or_update_secret(
                path='keycloak/clients/demo-client',
                secret=dict(client_secret='dummy-secret'),
                mount_point='secret'
            )
            return 'dummy-secret'
    except Exception as e:
        print(f"Error fetching secret from Vault: {str(e)}")
        print(f"Vault URL: {vault_settings['url']}")
        print(f"Vault token: {vault_settings['token'][:5]}...")  # Only print first 5 chars for security
        return None

def get_keycloak_client():
    client_secret = get_client_secret_from_vault()
    if not client_secret:
        raise Exception("Could not fetch client secret from Vault")
    
    return KeycloakOpenID(
        server_url=keycloak_settings["server_url"],
        client_id=keycloak_settings["client_id"],
        realm_name=keycloak_settings["realm_name"],
        client_secret_key=client_secret
    )

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
            keycloak_client = get_keycloak_client()
            print(f"Attempting to authenticate user: {username}")
            token = keycloak_client.token(username=username, password=password)
            print("Authentication successful")
            session['token'] = token
            session['username'] = username
            return redirect(url_for('index'))
        except Exception as e:
            print(f"Authentication failed: {str(e)}")
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
        
        # Get Keycloak client
        keycloak_client = get_keycloak_client()
        
        # Get user info from token
        user_info = keycloak_client.userinfo(token=access_token)
        
        # Get current secret from Vault
        client = get_vault_client()
        secret_info = client.secrets.kv.v2.read_secret_version(
            path='keycloak/clients/demo-client',
            mount_point='secret'
        )
        
        # Get secret metadata
        secret_metadata = client.secrets.kv.v2.read_secret_metadata(
            path='keycloak/clients/demo-client',
            mount_point='secret'
        )
        
        status = {
            'vault_connected': True,
            'keycloak_connected': True,
            'secret_last_fetched': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'token_works': True,
            'user_info': {
                'username': user_info.get('preferred_username', 'Unknown'),
                'email': user_info.get('email', 'Not provided'),
                'name': user_info.get('name', 'Not provided'),
                'roles': user_info.get('realm_access', {}).get('roles', [])
            },
            'system_info': {
                'secret_version': secret_metadata.get('data', {}).get('current_version', 'Unknown'),
                'secret_created': secret_metadata.get('data', {}).get('created_time', 'Unknown'),
                'vault_status': 'Healthy',
                'keycloak_status': 'Connected'
            }
        }
    except Exception as e:
        status = {
            'vault_connected': False,
            'keycloak_connected': False,
            'error': str(e)
        }
    
    return render_template('index.html', status=status)

@app.route('/health')
def health():
    try:
        client_secret = get_client_secret_from_vault()
        keycloak_client = get_keycloak_client()
        
        return jsonify({
            'status': 'healthy',
            'vault_connected': True,
            'keycloak_connected': True,
            'secret_rotation_working': True if client_secret else False
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 