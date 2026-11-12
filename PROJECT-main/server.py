import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask import make_response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import secrets
from datetime import datetime
import subprocess
import sys

app = Flask(__name__, static_folder='.', template_folder='.')

# Configure CORS: allow broad access in development, restrict in production
DEV_MODE = os.getenv('DEV', '1') == '1'
if DEV_MODE:
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type"]
        }
    })
else:
    # In production, set allowed origins explicitly (replace with your domain)
    CORS(app, resources={
        r"/api/*": {
            "origins": ["https://yourdomain.com"],
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type"]
        }
    })

# Get the absolute path to the directory containing this script.
# When the app is bundled by PyInstaller, resources are extracted to
# sys._MEIPASS; user-writable data should live in AppData (or home).
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'projector_app')
    os.makedirs(data_dir, exist_ok=True)
    USERS_FILE = os.path.join(data_dir, 'users_web.json')
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    USERS_FILE = os.path.join(BASE_DIR, 'users_web.json')


@app.before_request
def log_request_info():
    # Simple request logger to help debug preflight and incoming calls
    try:
        remote = request.remote_addr or 'unknown'
        print(f"[REQ] {request.method} {request.path} from {remote}")
    except Exception:
        pass

    # In development, handle OPTIONS preflight generically to avoid 405s
    if DEV_MODE and request.method == 'OPTIONS':
        resp = make_response(jsonify({'status': 'ok'}), 200)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Accept'
        return resp


@app.after_request
def add_cors_headers(response):
    # Ensure simple CORS headers in dev mode for non-/api routes
    if DEV_MODE:
        response.headers.setdefault('Access-Control-Allow-Origin', '*')
    return response

def load_users():
    """Load users from JSON file with error handling."""
    print(f"Attempting to load users from: {USERS_FILE}")
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
                print("File is empty")
                return {}
        except Exception as e:
            print(f"Error loading users: {e}")
            return {}
    else:
        print(f"File not found: {USERS_FILE}")
    return {}

def save_users(users):
    """Save users to JSON file with error handling."""
    print(f"Attempting to save users to: {USERS_FILE}")
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)

        # Write to a temporary file first, then atomically replace the target file.
        temp_file = f"{USERS_FILE}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)

        # Use os.replace for atomic replace semantics across platforms (works on Windows)
        os.replace(temp_file, USERS_FILE)

        print(f"Successfully saved {len(users)} users")
        return True
    except Exception as e:
        print(f"Error saving users: {e}")
        # Clean up temp file if it exists to avoid stale files
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass
        return False

@app.route('/')
def index():
    """Serve the main HTML page from the script directory (robust to cwd)."""
    return send_from_directory(BASE_DIR, 'haha.html')

@app.route('/api/register', methods=['POST', 'OPTIONS'])
def register():
    """Handle user registration with enhanced validation and error handling."""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'success'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        # Input validation
        username = data.get('username', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        # Detailed validation
        if not username:
            return jsonify({'error': 'Username is required'}), 400
        if not email or '@' not in email:
            return jsonify({'error': 'Valid email is required'}), 400
        if not password:
            return jsonify({'error': 'Password is required'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        # Load existing users
        users = load_users()
        print(f"Current users: {list(users.keys())}")
        
        # Check for existing user
        if username in users:
            return jsonify({'error': 'Username already exists'}), 409
        
        # Check if email is already registered
        if any(user.get('email') == email for user in users.values()):
            return jsonify({'error': 'Email already registered'}), 409

        # Create user data with additional metadata
        users[username] = {
            'email': email,
            'password_hash': generate_password_hash(password),
            'created_at': datetime.now().isoformat(),
            'last_login': None,
            'is_active': True
        }
        
        # Save with error handling
        if not save_users(users):
            return jsonify({'error': 'Failed to save user data'}), 500
        
        print(f"User registered successfully: {username}")
        return jsonify({
            'message': 'User registered successfully',
            'username': username
        }), 201

    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON data'}), 400
    except Exception as e:
        print(f"Registration error: {str(e)}")
        return jsonify({'error': 'An error occurred during registration'}), 500

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    """Handle user login."""
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'success'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        users = load_users()
        
        if username not in users:
            return jsonify({'error': 'Invalid username or password'}), 401
        
        user = users[username]
        if not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid username or password'}), 401
        
        # Update last login time
        user['last_login'] = datetime.now().isoformat()
        save_users(users)
        
        # Generate a token (in production, use JWT)
        token = secrets.token_hex(32)
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'username': username
        }), 200

    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'An error occurred during login'}), 500


@app.route('/run-voicetext', methods=['GET', 'POST', 'OPTIONS'])
def run_voicetext():
    """Start the desktop `voicetotext.py` as a detached process on the server host.

    Note: this is intended for local/dev use. Do not expose this endpoint in production
    without authentication and proper safeguards.
    """
    # Handle CORS preflight for non-/api route in DEV mode
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Accept')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response

    script = os.path.join(BASE_DIR, 'voicetotext.py')
    if not os.path.exists(script):
        return jsonify({'error': 'voicetotext.py not found on server'}), 404

    try:
        # Cross-platform detached launch
        if os.name == 'nt':
            # Windows: use creationflags to detach
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            subprocess.Popen([sys.executable, script],
                             creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             close_fds=True)
        else:
            # POSIX: detach from parent by redirecting stdio and using setsid
            subprocess.Popen([sys.executable, script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, close_fds=True, preexec_fn=os.setsid)

        resp = jsonify({'status': 'started'})
        resp.headers.add('Access-Control-Allow-Origin', '*')
        return resp, 200
    except Exception as e:
        print(f"Failed to start voicetext: {e}")
        resp = jsonify({'error': str(e)})
        resp.headers.add('Access-Control-Allow-Origin', '*')
        return resp, 500


@app.route('/run-vnmforedit', methods=['GET', 'POST', 'OPTIONS'])
def run_vnmforedit():
    """Start the desktop `vnmforedit.py` as a detached process on the server host.

    Intended for local/dev use only.
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Accept')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response

    script = os.path.join(BASE_DIR, 'vnmforedit.py')
    if not os.path.exists(script):
        return jsonify({'error': 'vnmforedit.py not found on server'}), 404

    try:
        # include optional auto-start flag when launching from the web button
        args = [sys.executable, script, '--auto-start']
        # Cross-platform detached launch
        # create logs dir and log file for this run so we can inspect stdout/stderr
        logs_dir = os.path.join(BASE_DIR, 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(logs_dir, f'vnmforedit_run_{ts}.log')
        # open in binary append so subprocess can write bytes
        logf = open(log_path, 'ab')

        if os.name == 'nt':
            # Use the server's Python executable (likely the venv) to ensure
            # the spawned process has the same environment. Use a new console
            # instead of fully detaching so the GUI can attach to the desktop
            # session on Windows.
            CREATE_NEW_CONSOLE = 0x00000010
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            flags = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
            p = subprocess.Popen([sys.executable] + args[1:],
                                 creationflags=flags,
                                 stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
                                 close_fds=False)
        else:
            p = subprocess.Popen(args, stdout=logf, stderr=logf, stdin=subprocess.DEVNULL, close_fds=True, preexec_fn=os.setsid)

        resp = jsonify({'status': 'started', 'pid': p.pid, 'log': os.path.relpath(log_path, BASE_DIR)})
        resp.headers.add('Access-Control-Allow-Origin', '*')
        return resp, 200
    except Exception as e:
        print(f"Failed to start vnmforedit: {e}")
        resp = jsonify({'error': str(e)})
        resp.headers.add('Access-Control-Allow-Origin', '*')
        return resp, 500


@app.route('/api/run-vnmforedit', methods=['GET', 'POST', 'OPTIONS'])
def api_run_vnmforedit():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Accept')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response

    script = os.path.join(BASE_DIR, 'vnmforedit.py')
    if not os.path.exists(script):
        return jsonify({'error': 'vnmforedit.py not found on server'}), 404

    try:
        args = [sys.executable, script, '--auto-start']

        # Debug mode: if caller adds ?debug=1, run non-detached so stdout/stderr
        # appear in the server terminal (useful when debugging on local machine).
        debug = request.args.get('debug', '0') == '1'

        # create logs dir and log file for this run so we can inspect stdout/stderr
        logs_dir = os.path.join(BASE_DIR, 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(logs_dir, f'vnmforedit_run_api_{ts}.log')

        if debug:
            # Run in same console (do not redirect) for immediate visibility
            print(f"[DEBUG LAUNCH] Running: {args}")
            if os.name == 'nt':
                # On Windows, no special flags so child inherits console
                p = subprocess.Popen(args)
            else:
                p = subprocess.Popen(args)
            return jsonify({'status': 'started', 'pid': p.pid, 'log': os.path.relpath(log_path, BASE_DIR), 'debug': True}), 200

        # Normal (non-debug) behavior: append logs to file and detach appropriately
        logf = open(log_path, 'ab')

        if os.name == 'nt':
            CREATE_NEW_CONSOLE = 0x00000010
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            flags = CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP
            p = subprocess.Popen([sys.executable] + args[1:],
                                 creationflags=flags,
                                 stdout=logf, stderr=logf, stdin=subprocess.DEVNULL,
                                 close_fds=False)
        else:
            p = subprocess.Popen(args, stdout=logf, stderr=logf, stdin=subprocess.DEVNULL, close_fds=True, preexec_fn=os.setsid)

        return jsonify({'status': 'started', 'pid': p.pid, 'log': os.path.relpath(log_path, BASE_DIR)}), 200
    except Exception as e:
        print(f"Failed to start vnmforedit (api): {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/run-voicetext', methods=['GET', 'POST', 'OPTIONS'])
def api_run_voicetext():
    # same behavior as /run-voicetext but covered by CORS setup for /api/*
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Accept')
        response.headers.add('Access-Control-Allow-Methods', 'POST, OPTIONS')
        return response

    script = os.path.join(BASE_DIR, 'voicetotext.py')
    if not os.path.exists(script):
        return jsonify({'error': 'voicetotext.py not found on server'}), 404

    try:
        if os.name == 'nt':
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            subprocess.Popen([sys.executable, script],
                             creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             close_fds=True)
        else:
            subprocess.Popen([sys.executable, script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, close_fds=True, preexec_fn=os.setsid)

        return jsonify({'status': 'started'}), 200
    except Exception as e:
        print(f"Failed to start voicetext (api): {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/<path:path>')
def serve_static(path):
    """Serve static files (catch-all) from the script directory."""
    return send_from_directory(BASE_DIR, path)


# Debug helper: list files in BASE_DIR and check for newhaha.html
@app.route('/__debug_list', methods=['GET'])
def _debug_list():
    try:
        files = sorted(os.listdir(BASE_DIR))
        exists = 'newhaha.html' in files
        return jsonify({'files': files, 'newhaha_exists': exists}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create users file if it doesn't exist
    if not os.path.exists(USERS_FILE):
        print(f"Creating new users file at: {USERS_FILE}")
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

    port = int(os.getenv('PORT', '5000'))
    host = os.getenv('HOST', '0.0.0.0')

    print(f"Server starting. Users file location: {USERS_FILE}")
    print(f"File exists: {os.path.exists(USERS_FILE)}")
    print(f"File is writable: {os.access(USERS_FILE, os.W_OK)}")
    print('Dev mode:' if DEV_MODE else 'Production mode:', DEV_MODE)

    # To avoid multiple listener lines from the reloader, disable use_reloader by default.
    # If you want auto-reload while developing, set the env var FLASK_RELOAD=1.
    use_reloader = os.getenv('FLASK_RELOAD', '0') == '1'
    debug = DEV_MODE

    app.run(debug=debug, port=port, host=host, use_reloader=use_reloader)
