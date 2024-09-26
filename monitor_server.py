import os
from flask import Flask, request, render_template_string, jsonify
from datetime import datetime, timedelta, timezone
import logging
import json

# Logger configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# File path
HEARTBEAT_FILE = 'app_data/heartbeat_data.json'

app = Flask(__name__)

heartbeat_data = {}

# Ensure 'app_data' directory exists
if not os.path.exists('app_data'):
    logging.debug("Creating directory 'app_data'.")
    os.makedirs('app_data')
else:
    logging.debug("Directory 'app_data' already exists.")

def load_from_file(filename):
    """Load data from a file, returning an empty dictionary if the file does not exist."""
    if not os.path.exists(filename):
        logging.critical(f"File {filename} does not exist. Returning empty data.")
        return {}

    try:
        with open(filename, 'r') as f:
            logging.debug(f"Loading data from file {filename}.")
            data = json.load(f)
            logging.debug(f"Data loaded successfully: {data}")
            return data
    except json.JSONDecodeError as e:
        logging.critical(f"JSON decode error for file {filename}: {e}")
        return {}
    except Exception as e:
        logging.critical(f"Error loading data from {filename}: {e}")
        return {}

def save_to_file(data, filename):
    """Save data to a file and return JSON with the result status."""
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

def convert_to_dash(credits):
    """Convert credits to Dash."""
    return credits / 100000000000

def format_timestamp(timestamp):
    """Convert a timestamp to a shorter, human-readable format in UTC+1."""
    dt = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).astimezone(timezone(timedelta(hours=1)))
    return dt.strftime('%b %d %H:%M')

def time_ago_from(timestamp):
    """Convert a timestamp to a format showing time elapsed since the timestamp."""
    now = datetime.now(timezone.utc)
    elapsed = now - datetime.fromtimestamp(timestamp, tz=timezone.utc)
    days = elapsed.days
    hours, remainder = divmod(elapsed.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    global heartbeat_data
    data = request.get_json()
    logging.debug(f"Received heartbeat data: {data}")

    server_name = data.get('serverName')
    if server_name:
        # Save the report time as a UTC timestamp
        data['lastReportTime'] = datetime.now(timezone.utc).timestamp()
        heartbeat_data[server_name] = data
        # Save data to file and get the result
        result = save_to_file(heartbeat_data, HEARTBEAT_FILE)

        # Determine the HTTP status code based on the result of file saving
        status_code = 200 if result["status"] == "success" else 500

        # Return JSON response with detailed message about the file saving result
        logging.debug(f"Heartbeat data processed with status: {result['status']}.")
        return jsonify(result), status_code
    else:
        logging.debug("Invalid data format for heartbeat.")
        # Return error message if the input data format is invalid
        return jsonify({"status": "error", "message": "Invalid data format."}), 400

@app.route('/', methods=['GET'])
def display_validators():
    global heartbeat_data
    logging.debug("Loading heartbeat data from file.")
    heartbeat_data = load_from_file(HEARTBEAT_FILE)

    current_time = datetime.now().astimezone(timezone(timedelta(hours=1))).strftime("%Y-%m-%d %H:%M:%S")
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
    epoch_start_time = None  # Ensure epoch_start_time is initialized

    # Find the Evonode with the highest platform block height to fetch validatorsInQuorum
    highest_platform_block_height = 0
    validators_in_quorum = []
    latest_block_validator = None

    for server, data in heartbeat_data.items():
        platform_block_height = data.get('platformBlockHeight', 0)
        if platform_block_height > highest_platform_block_height:
            highest_platform_block_height = platform_block_height
            validators_in_quorum = data.get('validatorsInQuorum', [])
            latest_block_validator = data.get('latestBlockValidator', None)

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

    # Ensure epoch_start_time has a default value if still None
    if epoch_start_time is None:
        epoch_start_time = 0

    total_balance_dash = convert_to_dash(total_balance_credits)
    blocks_in_epoch = latest_block_height - epoch_first_block_height
    share_proposed_blocks = (total_proposed_blocks / blocks_in_epoch) * 100 if blocks_in_epoch else 0
    epoch_start_human = format_timestamp(epoch_start_time)
    epoch_end_time = datetime.fromtimestamp(int(epoch_start_time) / 1000, tz=timezone.utc) + timedelta(days=9.125)
    epoch_end_human = epoch_end_time.astimezone(timezone(timedelta(hours=1))).strftime('%b %d %H:%M')

    # Helper function to format ProTxHash to wrap into four lines
    def format_protx(protx):
        return '<br>'.join([protx[i:i+16] for i in range(0, len(protx), 16)])

    # Determine the type (Evonode or Masternode)
    def get_node_type(server):
        platform_height = heartbeat_data[server].get('platformBlockHeight', 0)
        return 'Evonode' if platform_height > 0 else 'Masternode'

    # Get the set of ProTxHashes in the second table to compare with validators in quorum
    protx_in_second_table = {heartbeat_data[server].get('proTxHash') for server in server_names}

    # Render HTML template
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
                margin-bottom: 20px;
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
            .light-green {
                background-color: #d4f4d2;
                font-weight: bold;
            }
            .validator-in-quorum {
                font-weight: bold;
                color: green;
            }
            .highlight-latest {
                background-color: #d4f4d2;
            }
            meta[name="format-detection"] {
                format-detection: none;
            }
        </style>
        <meta name="format-detection" content="telephone=no">
    </head>
    <body>
        <h1>Masternodes and Evonodes Monitor</h1>
        <p>Data fetched on: <span id="current-time">{{ current_time }}</span></p>

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
                <td data-timestamp="{{ epoch_start_time }}"></td>
                <td data-timestamp="{{ (epoch_start_time + 9.125 * 86400000) }}"></td>
            </tr>
        </table>

        <!-- Detailed Node Table -->
        <table>
            <!-- The second table structure as it was before -->
        </table>

        <!-- Validators in Quorum Table -->
        <table style="width: auto;">
            <tr>
                <th style="width: calc(100% / 12);">#</th>
                <th style="width: calc((100% / 12) * 4);">Validators in Quorum</th>
            </tr>
            {% for validator in validators_in_quorum %}
            <tr>
                <td>{{ loop.index }}</td>
                <td class="{{ 'validator-in-quorum' if validator in protx_in_second_table else '' }} {{ 'highlight-latest' if validator == latest_block_validator else '' }}">{{ validator }}</td>
            </tr>
            {% endfor %}
        </table>

        <!-- JavaScript to handle time conversion based on the browser's timezone -->
        <script>
            document.querySelectorAll('[data-timestamp]').forEach(el => {
                const timestamp = parseInt(el.getAttribute('data-timestamp'));
                if (!isNaN(timestamp)) {
                    const date = new Date(timestamp);
                    el.textContent = date.toLocaleString();
                }
            });
        </script>
    </body>
    </html>
    """

    # Render the HTML template
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
        epoch_start_time=epoch_start_time,  # Ensuring this variable is passed correctly
        epoch_end_human=epoch_end_human,
        server_names=server_names,
        heartbeat_data=heartbeat_data,
        validators_in_quorum=validators_in_quorum,
        format_protx=format_protx,
        get_node_type=get_node_type,
        convert_to_dash=convert_to_dash,
        time_ago_from=time_ago_from,
        latest_block_validator=latest_block_validator
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
