import os
from flask import Flask, render_template_string, jsonify, request
from datetime import datetime, timedelta
import logging
import json

# Logger configuration - logging debug information for detailed logs
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to get detailed logs
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Log to the console
    ]
)

# Paths to files
HEARTBEAT_FILE = 'app_data/heartbeat_data.json'

app = Flask(__name__)

heartbeat_data = {}

# Ensure the 'app_data' directory exists
if not os.path.exists('app_data'):
    logging.debug("Creating directory 'app_data'.")
    os.makedirs('app_data')
else:
    logging.debug("Directory 'app_data' already exists.")

def ensure_directory_exists(path):
    """Ensure the directory for the given path exists."""
    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        try:
            logging.debug(f"Creating directory {directory}.")
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
        logging.debug(f"Attempting to save to temporary file {temp_filename}.")

        with open(temp_filename, 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        os.replace(temp_filename, filename)
        logging.debug(f"Successfully saved data to {filename}.")
        return {"status": "success", "message": f"Data saved successfully to {filename}."}
        
    except Exception as e:
        logging.critical(f"Error saving data to {filename}: {e}")

        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return {"status": "error", "message": f"Error saving data to {filename}: {e}"}

def load_from_file(filename):
    """Load data from a file, returning an empty dictionary if the file does not exist."""
    if not os.path.exists(filename):
        logging.critical(f"File {filename} does not exist. Returning empty data.")
        return {}  # Return an empty dictionary if the file does not exist

    try:
        with open(filename, 'r') as f:
            logging.debug(f"Loading data from file {filename}.")
            data = json.load(f)
            logging.debug(f"Data loaded successfully: {data}")
            return data
    except json.JSONDecodeError as e:
        logging.critical(f"JSON decode error for file {filename}: {e}")
        return {}  # If JSON is invalid, return an empty dictionary
    except Exception as e:
        logging.critical(f"Error loading data from {filename}: {e}")
        return {}  # If another error occurs, return an empty dictionary

def convert_to_dash(credits):
    """Convert credits to Dash."""
    return credits / 100000000000

def format_timestamp(timestamp):
    """Convert a timestamp to a shorter, human-readable format without the year."""
    return datetime.fromtimestamp(int(timestamp) / 1000).strftime('%b %d %H:%M')

@app.route('/', methods=['GET'])
def display_validators():
    global heartbeat_data
    logging.debug("Loading heartbeat data from file.")
    heartbeat_data = load_from_file(HEARTBEAT_FILE)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    server_names = sorted(heartbeat_data.keys())

    # Aggregate data calculations
    masternodes = 0
    evonodes = 0
    ok_evonodes = 0
    in_quorum_evonodes = 0
    total_balance_credits = 0
    total_proposed_blocks = 0

    epoch_number = 0
    epoch_first_block_height = 0
    latest_block_height = 0
    epoch_start_time = 0

    for server in heartbeat_data.values():
        is_evonode = server.get('platformBlockHeight', 0) > 0
        masternodes += not is_evonode
        evonodes += is_evonode
        total_balance_credits += server.get('balance', 0)
        total_proposed_blocks += int(server.get('proposedBlockInCurrentEpoch', 0))

        if is_evonode:
            if server.get('produceBlockStatus') == 'OK':
                ok_evonodes += 1
            if server.get('inQuorum'):
                in_quorum_evonodes += 1

            epoch_number = server.get('epochNumber', epoch_number)
            epoch_first_block_height = int(server.get('epochFirstBlockHeight', epoch_first_block_height))
            latest_block_height = int(server.get('latestBlockHeight', latest_block_height))
            epoch_start_time = server.get('epochStartTime', epoch_start_time)

    total_balance_dash = convert_to_dash(total_balance_credits)
    blocks_in_epoch = latest_block_height - epoch_first_block_height
    share_proposed_blocks = (total_proposed_blocks / blocks_in_epoch) * 100 if blocks_in_epoch else 0
    epoch_start_human = format_timestamp(epoch_start_time)
    epoch_end_time = datetime.fromtimestamp(int(epoch_start_time) / 1000) + timedelta(days=9.125)
    epoch_end_human = epoch_end_time.strftime('%b %d %H:%M')

    # Helper function to format ProTxHash to wrap into four lines
    def format_protx(protx):
        return '<br>'.join([protx[i:i+16] for i in range(0, len(protx), 16)])

    # Determine the type (Evonode or Masternode)
    def get_node_type(server):
        platform_height = heartbeat_data[server].get('platformBlockHeight', 0)
        return 'Evonode' if platform_height > 0 else 'Masternode'

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Masternodes and Evonodes Monitor</title>
        <style>
            body {
                background-color: #ffffff;
                color: #333;
                font-family: 'Courier New', monospace;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
                margin-bottom: 20px; /* Adds space between tables */
            }
            th, td {
                padding: 8px 12px;
                border: 1px solid #ddd;
                text-align: center;
                overflow: hidden;
                white-space: nowrap;
            }
            td.wrap {
                white-space: pre-wrap;
                word-wrap: break-word;
            }
            th {
                background-color: #f2f2f2;
                font-weight: bold;
            }
            .header-row td {
                font-weight: bold;
            }
            .bold {
                font-weight: bold;
            }
            .green {
                color: green;
                font-weight: bold;
            }
            .red {
                color: red;
                font-weight: bold;
            }
            meta[name="format-detection"] {
                format-detection: none;
            }
        </style>
        <meta name="format-detection" content="telephone=no">
    </head>
    <body>
        <h1>Masternodes and Evonodes Monitor</h1>
        <p>Data fetched on: {{ current_time }}</p>

        <!-- Aggregate Data Table -->
        <table>
            <tr>
                <th>MN/eMN</th>
                <th>ok/eMN</th>
                <th>inQuorum/eMN</th>
                <th>credits</th>
                <th>Dash</th>
                <th>totalBlocks</th>
                <th>share</th>
                <th>epochNumber</th>
                <th>firstBlock</th>
                <th>latestBlock</th>
                <th>blocksInEpoch</th>
                <th>epochStartTime</th>
                <th>epochEndTime</th>
            </tr>
            <tr>
                <td>{{ masternodes }}/{{ evonodes }}</td>
                <td>{{ ok_evonodes }}/{{ evonodes }}</td>
                <td>{{ in_quorum_evonodes }}/{{ evonodes }}</td>
                <td>{{ total_balance_credits }}</td>
                <td>{{ '{:.8f}'.format(total_balance_dash) }}</td>
                <td>{{ total_proposed_blocks }}</td>
                <td>{{ '{:.2f}'.format(share_proposed_blocks) }}%</td>
                <td>{{ epoch_number }}</td>
                <td>{{ epoch_first_block_height }}</td>
                <td>{{ latest_block_height }}</td>
                <td>{{ blocks_in_epoch }}</td>
                <td>{{ epoch_start_human }}</td>
                <td>{{ epoch_end_human }}</td>
            </tr>
        </table>

        <!-- Detailed Node Table -->
        <table>
            <tr class="header-row">
                <td class="bold">Server Name</td>
                {% for server in server_names %}
                <td>{{ server }}</td>
                {% endfor %}
            </tr>
            <!-- Type Row -->
            <tr class="bold">
                <td class="bold">Type</td>
                {% for server in server_names %}
                <td>{{ get_node_type(server) }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">uptime</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('uptime', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">uptimeInSeconds</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('uptimeInSeconds', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <!-- Core Row -->
            <tr class="bold">
                <td class="bold">Core</td>
                {% for server in server_names %}
                <td>Core</td>
                {% endfor %}
            </tr>
            <!-- Reordered Rows -->
            <tr>
                <td class="bold">proTxHash</td>
                {% for server in server_names %}
                <td class="wrap">{{ format_protx(heartbeat_data[server].get('proTxHash', 'N/A')) | safe }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">blockHeight</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('coreBlockHeight', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">paymentPosition</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('paymentQueuePosition', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">nextPaymentTime</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('nextPaymentTime', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">lastPaidTime</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('lastPaidTime', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">poSePenalty</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('poSePenalty', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">poSeRevivedHeight</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('poSeRevivedHeight', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">poSeBanHeight</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('poSeBanHeight', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <!-- Platform Row -->
            <tr class="bold">
                <td class="bold">Platform</td>
                {% for server in server_names %}
                <td>Platform</td>
                {% endfor %}
            </tr>
            <!-- Remaining Rows -->
            <tr>
                <td class="bold">blockHeight</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('platformBlockHeight', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">p2pPortState</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('p2pPortState', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">httpPortState</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('httpPortState', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">proposedBlocks</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('proposedBlockInCurrentEpoch', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">inQuorum</td>
                {% for server in server_names %}
                <td class="{{ 'green' if heartbeat_data[server].get('inQuorum', False) else '' }}">{{ heartbeat_data[server].get('inQuorum', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <!-- Additional Rows -->
            <tr>
                <td class="bold">balanceInCredits</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('balance', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">balanceInDash</td>
                {% for server in server_names %}
                <td>{{ '{:.8f}'.format(convert_to_dash(heartbeat_data[server].get('balance', 0))) }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">produceBlockStatus</td>
                {% for server in server_names %}
                <td class="{{ 'green' if heartbeat_data[server].get('produceBlockStatus', '') == 'OK' else 'red' if heartbeat_data[server].get('produceBlockStatus', '') == 'ERROR' else '' }}">{{ heartbeat_data[server].get('produceBlockStatus', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">lastProdHeight</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('lastProduceBlockHeight', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">shouldProdHeight</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('lastShouldProduceBlockHeight', 'N/A') }}</td>
                {% endfor %}
            </tr>
        </table>
    </body>
    </html>
    """
    
    return render_template_string(
        html_template,
        current_time=current_time,
        masternodes=masternodes,
        evonodes=evonodes,
        ok_evonodes=ok_evonodes,
        in_quorum_evonodes=in_quorum_evonodes,
        total_balance_credits=total_balance_credits,
        total_balance_dash=total_balance_dash,
        total_proposed_blocks=total_proposed_blocks,
        share_proposed_blocks=share_proposed_blocks,
        epoch_number=epoch_number,
        epoch_first_block_height=epoch_first_block_height,
        latest_block_height=latest_block_height,
        blocks_in_epoch=blocks_in_epoch,
        epoch_start_human=epoch_start_human,
        epoch_end_human=epoch_end_human,
        server_names=server_names,
        heartbeat_data=heartbeat_data,
        format_protx=format_protx,
        get_node_type=get_node_type,
        convert_to_dash=convert_to_dash  # Ensure this function is passed correctly
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
