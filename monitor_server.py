import os
import requests
from flask import Flask, request, render_template_string, jsonify
from datetime import datetime, timedelta 
import logging
import json

# Logger configuration - logging only critical errors
logging.basicConfig(
    level=logging.CRITICAL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Log only to console
    ]
)

VALIDATORS_FILE = 'validators.txt'
HEARTBEAT_FILE = 'app_data/heartbeat_data.json'
QUORUMINFO_FILE = 'app_data/quoruminfo_data.json'

API_URL = "https://platform-explorer.pshenmic.dev/validators"
STATUS_API_URL = "https://platform-explorer.pshenmic.dev/status"
OVH_API_URL = "https://ca.api.ovh.com/v1/dedicated/server/datacenter/availabilities?planCode=24ska01"

CACHE_TTL = timedelta(minutes=5)  # Cache Time-To-Live
app = Flask(__name__)

# Simple in-memory cache
cache = {
    "validators": {"data": None, "last_fetched": None},
    "epoch_info": {"data": None, "last_fetched": None},
    "validator_blocks": {},
    "ovh_availability": {"data": None, "last_fetched": None}
}

heartbeat_data = {}
quorum_info_data = {}

error_message = None  # Global variable to store error message

def ensure_directory_exists(path):
    """Ensure the directory for the given path exists."""
    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            logging.critical(f"Could not create directory {directory}: {e}")
            return False
    return True

def save_to_file(data, filename):
    """Save data to a file and return JSON with the result status."""
    if not ensure_directory_exists(filename):
        error_msg = f"Directory does not exist and could not be created for {filename}."
        logging.critical(error_msg)
        return {"status": "error", "message": error_msg}

    try:
        temp_filename = filename + ".tmp"
        
        with open(temp_filename, 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        os.replace(temp_filename, filename)
        return {"status": "success", "message": f"Data saved successfully to {filename}."}
        
    except Exception as e:
        logging.critical(f"Error saving data to {filename}: {e}")

        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return {"status": "error", "message": f"Error saving data to {filename}: {e}"}

def load_from_file(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.critical(f"Error loading data from {filename}: {e}")
        return {}

def fetch_validators():
    global error_message
    now = datetime.now()
    if cache["validators"]["data"] and cache["validators"]["last_fetched"] and (now - cache["validators"]["last_fetched"]) < CACHE_TTL:
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
        logging.critical(f"Error fetching validators from API: {e}")
        error_message = "Error fetching validators from API. Displaying cached data."
        return cache["validators"]["data"]
    return validators

def fetch_epoch_info():
    global error_message
    now = datetime.now()
    if cache["epoch_info"]["data"] and cache["epoch_info"]["last_fetched"] and (now - cache["epoch_info"]["last_fetched"]) < CACHE_TTL:
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
        logging.critical(f"Error fetching epoch info from API: {e}")
        error_message = "Error fetching epoch info from API. Displaying cached data."
        return cache["epoch_info"]["data"]

def fetch_validator_blocks(protx, first_block_height):
    global error_message
    now = datetime.now()
    if protx in cache["validator_blocks"]:
        cached_data = cache["validator_blocks"][protx]
        if cached_data["last_fetched"] and (now - cached_data["last_fetched"]) < CACHE_TTL:
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
        logging.critical(f"Error fetching blocks for validator {protx}: {e}")
        error_message = f"Error fetching blocks for validator {protx}. Displaying cached data."
        return cache["validator_blocks"][protx]["data"] if protx in cache["validator_blocks"] else 0
    return len(blocks)

def check_server_availability():
    global error_message
    now = datetime.now()
    if cache["ovh_availability"]["data"] and cache["ovh_availability"]["last_fetched"] and (now - cache["ovh_availability"]["last_fetched"]) < CACHE_TTL:
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
        logging.critical(f"Error checking server availability from OVH API: {e}")
        error_message = "Error checking server availability from OVH API. Displaying cached data."
        return cache["ovh_availability"]["data"]

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    global heartbeat_data
    data = request.get_json()

    server_name = data.get('serverName')
    uptime = data.get('uptime')
    uptime_in_seconds = data.get('uptimeInSeconds')
    pro_tx_hash = data.get('proTxHash')
    core_block_height = data.get('coreBlockHeight')
    platform_block_height = data.get('platformBlockHeight')
    p2p_port_state = data.get('p2pPortState')
    http_port_state = data.get('httpPortState')
    po_se_penalty = data.get('poSePenalty')
    po_se_revived_height = data.get('poSeRevivedHeight')
    po_se_ban_height = data.get('poSeBanHeight')
    last_paid_height = data.get('lastPaidHeight')
    last_paid_time = data.get('lastPaidTime')
    payment_queue_position = data.get('paymentQueuePosition')
    next_payment_time = data.get('nextPaymentTime')
    proposed_block_in_current_epoch = data.get('proposedBlockInCurrentEpoch')
    epoch_number = data.get('epochNumber')
    epoch_first_block_height = data.get('epochFirstBlockHeight')
    epoch_start_time = data.get('epochStartTime')
    epoch_end_time = data.get('epochEndTime')
    in_quorum = data.get('inQuorum')

    if server_name:
        heartbeat_data[server_name] = {
            "uptime": uptime,
            "uptime_in_seconds": uptime_in_seconds,
            "pro_tx_hash": pro_tx_hash,
            "core_block_height": core_block_height,
            "platform_block_height": platform_block_height,
            "p2p_port_state": p2p_port_state,
            "http_port_state": http_port_state,
            "po_se_penalty": po_se_penalty,
            "po_se_revived_height": po_se_revived_height,
            "po_se_ban_height": po_se_ban_height,
            "last_paid_height": last_paid_height,
            "last_paid_time": last_paid_time,
            "payment_queue_position": payment_queue_position,
            "next_payment_time": next_payment_time,
            "proposed_block_in_current_epoch": proposed_block_in_current_epoch,
            "epoch_number": epoch_number,
            "epoch_first_block_height": epoch_first_block_height,
            "epoch_start_time": epoch_start_time,
            "epoch_end_time": epoch_end_time,
            "in_quorum": in_quorum
        }
        # Save data to file and get the result
        result = save_to_file(heartbeat_data, HEARTBEAT_FILE)

        # Determine the HTTP status code based on the result of file saving
        status_code = 200 if result["status"] == "success" else 500

        # Return JSON response with detailed message about the file saving result
        return jsonify(result), status_code
    else:
        # Return error message if the input data format is invalid
        return jsonify({"status": "error", "message": "Invalid data format."}), 400

@app.route('/quorumInfo', methods=['POST'])
def quorum_info():
    global quorum_info_data
    data = request.get_json()
    quorum_info_data = data
    # Save data to file and get the result
    result = save_to_file(quorum_info_data, QUORUMINFO_FILE)

    # Determine the HTTP status code based on the result of file saving
    status_code = 200 if result["status"] == "success" else 500

    # Return JSON response with detailed message about the file saving result
    return jsonify(result), status_code

@app.route('/old')
def display_validators():
    # Load persisted heartbeat and quorum data from file
    global heartbeat_data, quorum_info_data
    heartbeat_data = load_from_file(HEARTBEAT_FILE)
    quorum_info_data = load_from_file(QUORUMINFO_FILE)

    hard_coded_validators = load_validators_from_file()
    if not hard_coded_validators:
        return "Error loading validators from file."

    fetched_validators = fetch_validators()
    if not fetched_validators:
        return "Error fetching validators from API."

    fetched_dict = {v["proTxHash"]: v for v in fetched_validators}
    total_proposed_blocks = 0
    total_blocks_current_epoch = 0
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    epoch_number, first_block_height, epoch_start_time, epoch_end_time = fetch_epoch_info()
    if epoch_number is None:
        return "Error fetching epoch information."

    rows = []

    for validator in hard_coded_validators:
        protx = validator["protx"]
        hidden_elements = ""
        if protx in fetched_dict:
            fetched_data = fetched_dict[protx]
            blocks_count = fetch_validator_blocks(protx, first_block_height)
            total_blocks_current_epoch += blocks_count

            if fetched_data["proTxInfo"]["state"]["PoSePenalty"] != 0:
                hidden_elements += f'<span style="display: none;">POSE_PENALTY_ALERT_{validator["name"]}</span>'
            if fetched_data["proTxInfo"]["state"]["PoSeBanHeight"] != -1:
                hidden_elements += f'<span style="display: none;">POSE_BAN_ALERT_{validator["name"]}</span>'

            row = {
                "name": validator["name"],
                "protx": protx,
                "pose_penalty": fetched_data["proTxInfo"]["state"]["PoSePenalty"],
                "pose_revived_height": fetched_data["proTxInfo"]["state"]["PoSeRevivedHeight"],
                "pose_ban_height": fetched_data["proTxInfo"]["state"]["PoSeBanHeight"],
                "last_proposed_block_timestamp": fetched_data["lastProposedBlockHeader"]["timestamp"] if fetched_data["lastProposedBlockHeader"] else "N/A",
                "proposed_blocks_amount": fetched_data["proposedBlocksAmount"],
                "blocks_count": blocks_count,
                "hidden_elements": hidden_elements
            }
            total_proposed_blocks += fetched_data["proposedBlocksAmount"]
        else:
            row = {
                "name": validator["name"],
                "protx": protx,
                "pose_penalty": "VALIDATOR NOT FOUND",
                "pose_revived_height": "VALIDATOR NOT FOUND",
                "pose_ban_height": "VALIDATOR NOT FOUND",
                "last_proposed_block_timestamp": "VALIDATOR NOT FOUND",
                "proposed_blocks_amount": "VALIDATOR NOT FOUND",
                "blocks_count": "VALIDATOR NOT FOUND",
                "hidden_elements": hidden_elements
            }
        rows.append(row)

    server_availability = check_server_availability()

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
        <p>Data fetched on: {{ current_time }}</p>
        <p>Current Epoch: {{ epoch_number }}</p>
        <p>Epoch Start Time: {{ epoch_start_time }}</p>
        <p>Epoch End Time: {{ epoch_end_time }}</p>
        <p>First Block Height: {{ first_block_height }}</p>
        <table>
            <tr>
                <th>Name</th>
                <th>ProTx</th>
                <th>PoSe Penalty</th>
                <th>PoSe Revived Height</th>
                <th>PoSe Ban Height</th>
                <th>Last Proposed Block Timestamp</th>
                <th>Proposed Blocks Amount</th>
                <th>Blocks in Current Epoch</th>
            </tr>
            {% for row in rows %}
            <tr>
                <td>{{ row.name }} {{ row.hidden_elements|safe }}</td>
                <td>{{ row.protx }}</td>
                <td class="{{ 'not-found' if row.pose_penalty == 'VALIDATOR NOT FOUND' else '' }}">{{ row.pose_penalty }}</td>
                <td class="{{ 'not-found' if row.pose_revived_height == 'VALIDATOR NOT FOUND' else '' }}">{{ row.pose_revived_height }}</td>
                <td class="{{ 'not-found' if row.pose_ban_height == 'VALIDATOR NOT FOUND' else '' }}">{{ row.pose_ban_height }}</td>
                <td class="{{ 'not-found' if row.last_proposed_block_timestamp == 'VALIDATOR NOT FOUND' else '' }}">{{ row.last_proposed_block_timestamp }}</td>
                <td class="{{ 'not-found' if row.proposed_blocks_amount == 'VALIDATOR NOT FOUND' else '' }}">{{ row.proposed_blocks_amount }}</td>
                <td class="{{ 'not-found' if row.blocks_count == 'VALIDATOR NOT FOUND' else '' }}">{{ row.blocks_count }}</td>
            </tr>
            {% endfor %}
        </table>
        <h2>Total Proposed Blocks: {{ total_proposed_blocks }}</h2>
        <h2>Total Blocks in Current Epoch: {{ total_blocks_current_epoch }}</h2>
        <h3>{{ server_availability }}</h3>
        {% if error_message %}
        <p style="color:red;">{{ error_message }}</p>
        {% endif %}
        
        <!-- Display Heartbeat Data -->
        <h2>Heartbeat Data</h2>
        <table>
            <tr>
                <th>Server Name</th>
                <th>Uptime</th>
                <th>Uptime in Seconds</th>
                <th>ProTx Hash</th>
                <th>Core Block Height</th>
                <th>Platform Block Height</th>
                <th>P2P Port State</th>
                <th>HTTP Port State</th>
                <th>PoSe Penalty</th>
                <th>PoSe Revived Height</th>
                <th>PoSe Ban Height</th>
                <th>Last Paid Height</th>
                <th>Last Paid Time</th>
                <th>Payment Queue Position</th>
                <th>Next Payment Time</th>
                <th>Proposed Block in Current Epoch</th>
                <th>Epoch Number</th>
                <th>Epoch First Block Height</th>
                <th>Epoch Start Time</th>
                <th>Epoch End Time</th>
                <th>In Quorum</th>
            </tr>
            {% for server, data in heartbeat_data.items() %}
            <tr>
                <td>{{ server }}</td>
                <td>{{ data.uptime }}</td>
                <td>{{ data.uptime_in_seconds }}</td>
                <td>{{ data.pro_tx_hash }}</td>
                <td>{{ data.core_block_height }}</td>
                <td>{{ data.platform_block_height }}</td>
                <td>{{ data.p2p_port_state }}</td>
                <td>{{ data.http_port_state }}</td>
                <td>{{ data.po_se_penalty }}</td>
                <td>{{ data.po_se_revived_height }}</td>
                <td>{{ data.po_se_ban_height }}</td>
                <td>{{ data.last_paid_height }}</td>
                <td>{{ data.last_paid_time }}</td>
                <td>{{ data.payment_queue_position }}</td>
                <td>{{ data.next_payment_time }}</td>
                <td>{{ data.proposed_block_in_current_epoch }}</td>
                <td>{{ data.epoch_number }}</td>
                <td>{{ data.epoch_first_block_height }}</td>
                <td>{{ data.epoch_start_time }}</td>
                <td>{{ data.epoch_end_time }}</td>
                <td>{{ data.in_quorum }}</td>
            </tr>
            {% endfor %}
        </table>

        <!-- Display Quorum Info Data -->
        <h2>Quorum Information</h2>
        <pre>{{ quorum_info_data | tojson(indent=2) }}</pre>
        
    </body>
    </html>
    """
    
    return render_template_string(html_template, rows=rows, total_proposed_blocks=total_proposed_blocks, total_blocks_current_epoch=total_blocks_current_epoch, current_time=current_time, epoch_number=epoch_number, epoch_start_time=epoch_start_time, epoch_end_time=epoch_end_time, first_block_height=first_block_height, server_availability=server_availability, error_message=error_message, heartbeat_data=heartbeat_data, quorum_info_data=quorum_info_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
