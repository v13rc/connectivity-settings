from flask import Flask, render_template_string, request, jsonify
from datetime import datetime, timedelta
import json
import logging
import os

# Konfiguracja loggera do logowania na standardowe wyjście
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Logowanie tylko na standardowe wyjście
    ]
)

# Ścieżki do plików z danymi
VALIDATORS_FILE = 'validators.txt'
HEARTBEAT_FILE = '/home/monitor/heartbeat.json'  # Upewnij się, że ścieżka jest dostępna dla zapisu
QUORUM_INFO_FILE = '/home/monitor/quorum_info.json'
API_URL = "https://platform-explorer.pshenmic.dev/validators"
STATUS_API_URL = "https://platform-explorer.pshenmic.dev/status"
OVH_API_URL = "https://ca.api.ovh.com/v1/dedicated/server/datacenter/availabilities?planCode=24ska01"

# TTL dla cache
CACHE_TTL = timedelta(minutes=5)
app = Flask(__name__)

# Inicjalizacja cache
cache = {
    "validators": {"data": None, "last_fetched": None},
    "epoch_info": {"data": None, "last_fetched": None},
    "validator_blocks": {},
    "ovh_availability": {"data": None, "last_fetched": None}
}

# Globalna zmienna do przechowywania komunikatów o błędach
error_message = None

def load_validators_from_file():
    # Funkcja wczytująca validatorów z pliku
    validators = []
    try:
        with open(VALIDATORS_FILE, 'r') as file:
            for line in file:
                try:
                    name, protx = line.strip().split(',')
                    validators.append({"name": name, "protx": protx})
                except ValueError as e:
                    logging.error(f"Error parsing line in {VALIDATORS_FILE}: {line.strip()} - {e}")
    except FileNotFoundError:
        logging.error(f"File {VALIDATORS_FILE} not found.")
    except Exception as e:
        logging.error(f"Unexpected error while reading {VALIDATORS_FILE}: {e}")
    return validators

def fetch_validators():
    global error_message
    now = datetime.now()
    if cache["validators"]["data"] and cache["validators"]["last_fetched"] and (now - cache["validators"]["last_fetched"]) < CACHE_TTL:
        logging.debug("Returning cached validators data.")
        return cache["validators"]["data"]
    
    validators = []
    page = 1
    limit = 100
    try:
        while True:
            response = requests.get(f"{API_URL}?limit={limit}&page={page}")
            data = response.json()
            validators.extend(data["resultSet"])
            if len(validators) >= data["pagination"]["total"]:
                break
            page += 1
        cache["validators"]["data"] = validators
        cache["validators"]["last_fetched"] = now
        error_message = None  # Reset error message after successful call
    except Exception as e:
        logging.error(f"Error fetching validators from API: {e}")
        error_message = "Error fetching validators from API. Displaying cached data."
        return cache["validators"]["data"]
    return validators

def fetch_epoch_info():
    global error_message
    now = datetime.now()
    if cache["epoch_info"]["data"] and cache["epoch_info"]["last_fetched"] and (now - cache["epoch_info"]["last_fetched"]) < CACHE_TTL:
        logging.debug("Returning cached epoch info.")
        return cache["epoch_info"]["data"]
    
    try:
        response = requests.get(STATUS_API_URL)
        data = response.json()
        epoch_number = data["epoch"]["number"]
        first_block_height = data["epoch"]["firstBlockHeight"]
        epoch_start_time = datetime.fromtimestamp(data["epoch"]["startTime"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
        epoch_end_time = datetime.fromtimestamp(data["epoch"]["endTime"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
        epoch_info = (epoch_number, first_block_height, epoch_start_time, epoch_end_time)
        cache["epoch_info"]["data"] = epoch_info
        cache["epoch_info"]["last_fetched"] = now
        error_message = None  # Reset error message after successful call
        return epoch_info
    except Exception as e:
        logging.error(f"Error fetching epoch info from API: {e}")
        error_message = "Error fetching epoch info from API. Displaying cached data."
        return cache["epoch_info"]["data"]

def fetch_validator_blocks(protx, first_block_height):
    global error_message
    now = datetime.now()
    if protx in cache["validator_blocks"]:
        cached_data = cache["validator_blocks"][protx]
        if cached_data["last_fetched"] and (now - cached_data["last_fetched"]) < CACHE_TTL:
            logging.debug(f"Returning cached block data for validator {protx}.")
            return cached_data["data"]

    blocks = []
    page = 1
    limit = 100
    try:
        while True:
            response = requests.get(f"https://platform-explorer.pshenmic.dev/validator/{protx}/blocks?limit={limit}&page={page}")
            data = response.json()
            
            filtered_blocks = [block for block in data["resultSet"] if block["header"]["height"] >= first_block_height]
            blocks += filtered_blocks

            if len(filtered_blocks) < len(data["resultSet"]):
                break

            if len(data["resultSet"]) < limit or len(blocks) >= data["pagination"]["total"]:
                break

            page += 1
        cache["validator_blocks"][protx] = {"data": len(blocks), "last_fetched": now}
        error_message = None  # Reset error message after successful call
    except Exception as e:
        logging.error(f"Error fetching blocks for validator {protx}: {e}")
        error_message = f"Error fetching blocks for validator {protx}. Displaying cached data."
        return cache["validator_blocks"][protx]["data"] if protx in cache["validator_blocks"] else 0
    return len(blocks)

def check_server_availability():
    global error_message
    now = datetime.now()
    if cache["ovh_availability"]["data"] and cache["ovh_availability"]["last_fetched"] and (now - cache["ovh_availability"]["last_fetched"]) < CACHE_TTL:
        logging.debug("Returning cached OVH server availability data.")
        return cache["ovh_availability"]["data"]

    try:
        response = requests.get(OVH_API_URL, headers={"accept": "application/json"})
        data = response.json()
        available = any(dc["availability"] != "unavailable" for dc in data[0]["datacenters"])
        status_message = "Server KS-A is available" if available else "Server KS-A is not available"
        cache["ovh_availability"]["data"] = status_message
        cache["ovh_availability"]["last_fetched"] = now
        error_message = None  # Reset error message after successful call
        return status_message
    except Exception as e:
        logging.error(f"Error checking server availability from OVH API: {e}")
        error_message = "Error checking server availability from OVH API. Displaying cached data."
        return cache["ovh_availability"]["data"]


def save_heartbeat_data(server_name, last_reboot_timestamp):
    # Zapisuje dane heartbeat dla każdego serwera osobno
    try:
        data = {}
        try:
            if os.path.exists(HEARTBEAT_FILE):
                with open(HEARTBEAT_FILE, 'r') as f:
                    data = json.load(f)
        except json.JSONDecodeError:
            data = {}

        # Aktualizuje lub dodaje nowe dane dla serwera
        data[server_name] = {"lastRebootTimestamp": last_reboot_timestamp}

        with open(HEARTBEAT_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Error saving heartbeat data: {e}")

def save_quorum_info(data):
    # Zapisuje dane quorum do pliku JSON
    try:
        with open(QUORUM_INFO_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Error saving quorum info: {e}")

def load_heartbeat_data():
    # Wczytuje dane heartbeat z pliku JSON
    try:
        with open(HEARTBEAT_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Error loading heartbeat data: {e}")
        return {}

def load_quorum_info():
    # Wczytuje dane quorum z pliku JSON
    try:
        with open(QUORUM_INFO_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logging.error(f"Error loading quorum info: {e}")
        return {}

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    # Obsługa zapytań POST dla heartbeat
    data = request.json
    server_name = data.get('serverName')
    last_reboot_timestamp = data.get('lastRebootTimestamp')
    if server_name and last_reboot_timestamp:
        save_heartbeat_data(server_name, last_reboot_timestamp)
        return jsonify({"status": "success", "message": "Heartbeat data saved successfully"}), 200
    else:
        return jsonify({"status": "error", "message": "Invalid data provided"}), 400

@app.route('/quorumInfo', methods=['POST'])
def quorum_info():
    # Obsługa zapytań POST dla quorumInfo
    data = request.json
    if data:
        save_quorum_info(data)
        return jsonify({"status": "success", "message": "Quorum info saved successfully"}), 200
    else:
        return jsonify({"status": "error", "message": "Invalid data provided"}), 400

@app.route('/')
def display_validators():
    # Funkcja wyświetlająca stronę główną z informacjami
    hard_coded_validators = load_validators_from_file()
    if not hard_coded_validators:
        logging.error("No validators loaded from file.")
        return "Error loading validators from file."

    fetched_validators = fetch_validators()
    if not fetched_validators:
        logging.error("No validators fetched from API.")
        return "Error fetching validators from API."

    # Twoja istniejąca implementacja...

    heartbeat_data = load_heartbeat_data()
    quorum_info_data = load_quorum_info()

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dash Validators</title>
        <style>
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 8px 12px; border: 1px solid #ddd; text-align: center; }
            tr:nth-child(even) { background-color: #f2f2f2; }
            .not-found { color: red; }
        </style>
    </head>
    <body>
        <h1>Dash Validators Information</h1>
        <!-- Istniejąca zawartość HTML... -->

        <h2>Server Heartbeat Data</h2>
        <table>
            <tr>
                <th>Server Name</th>
                <th>Last Reboot Timestamp</th>
            </tr>
            {% for server, info in heartbeat_data.items() %}
            <tr>
                <td>{{ server }}</td>
                <td>{{ info.lastRebootTimestamp }}</td>
            </tr>
            {% endfor %}
        </table>

        <h2>Quorum Info</h2>
        <pre>{{ quorum_info_data | tojson(indent=2) }}</pre>
    </body>
    </html>
    """
    
    return render_template_string(html_template, rows=rows, total_proposed_blocks=total_proposed_blocks, total_blocks_current_epoch=total_blocks_current_epoch, current_time=current_time, epoch_number=epoch_number, epoch_start_time=epoch_start_time, epoch_end_time=epoch_end_time, first_block_height=first_block_height, server_availability=server_availability, error_message=error_message, heartbeat_data=heartbeat_data, quorum_info_data=quorum_info_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
