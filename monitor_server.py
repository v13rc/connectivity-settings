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
    """Convert a timestamp to a shorter, human-readable format in UTC+2."""
    dt = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).astimezone(timezone(timedelta(hours=2)))
    return dt.strftime('%b %d %H:%M')


def time_ago_from_minutes_seconds(timestamp):
    """Convert a timestamp to a format showing time elapsed since the timestamp in minutes and seconds."""
    now = datetime.now(timezone.utc)
    elapsed = now - datetime.fromtimestamp(timestamp, tz=timezone.utc)
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    minutes = int(minutes)
    seconds = int(seconds)
    return f"{minutes}m {seconds}s", minutes > 30


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
    epoch_start_time = 0

    # Find the Evonode with the highest platform block height to fetch validatorsInQuorum
    highest_platform_block_height = 0
    validators_in_quorum = []
    latest_block_validator = None

    # Initialize alerts dictionary
    alerts = {}

    for server, data in heartbeat_data.items():
        platform_block_height = data.get('platformBlockHeight', 0)
        if platform_block_height > highest_platform_block_height:
            highest_platform_block_height = platform_block_height
            validators_in_quorum = data.get('validatorsInQuorum', [])
            latest_block_validator = data.get('latestBlockValidator', None)

        # Check for conditions that trigger alerts
        alert_code = f"ALERT_{server.upper()}"
        alert_messages = []

        if data.get('poSePenalty', 0) != 0:
            alert_messages.append(f"{alert_code}_PENALTY")
        if data.get('poSeBanHeight', -1) != -1:
            alert_messages.append(alert_code)
        if data.get('p2pPortState', 'OPEN') != 'OPEN':
            alert_messages.append(alert_code)
        if data.get('httpPortState', 'OPEN') != 'OPEN':
            alert_messages.append(alert_code)
        if data.get('produceBlockStatus', '') == 'ERROR':
            alert_messages.append(alert_code)
        _, is_over_30_min = time_ago_from_minutes_seconds(data.get('lastReportTime', 0))
        if is_over_30_min:
            alert_messages.append(alert_code)

        # Store the alert code with its conditions
        alerts[server] = ' '.join(alert_messages)

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
            epoch_start_time = int(server.get('epochStartTime', epoch_start_time))

    total_balance_dash = convert_to_dash(total_balance_credits)
    blocks_in_epoch = latest_block_height - epoch_first_block_height
    share_proposed_blocks = (total_proposed_blocks / blocks_in_epoch) * 100 if blocks_in_epoch else 0
    epoch_start_human = format_timestamp(epoch_start_time)
    epoch_end_time = datetime.fromtimestamp(epoch_start_time / 1000, tz=timezone.utc) + timedelta(days=9.125)
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
            .red-bold {
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
            <tr>
                <td class="bold">lastReportTime</td>
                {% for server in server_names %}
                {% set last_report, is_over_30 = time_ago_from_minutes_seconds(heartbeat_data[server].get('lastReportTime', 0)) %}
                <td class="{{ 'red-bold' if is_over_30 else '' }}">{{ last_report }} {{ alerts[server] }}</td>
                {% endfor %}
            </tr>
            <tr class="bold">
                <td class="bold">Core</td>
                {% for server in server_names %}
                <td>Core</td>
                {% endfor %}
            </tr>
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
                <td>{{ heartbeat_data[server].get('poSePenalty', 'N/A') }} {{ alerts[server] }}</td>
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
                <td>{{ heartbeat_data[server].get('poSeBanHeight', 'N/A') }} {{ alerts[server] }}</td>
                {% endfor %}
            </tr>
            <tr class="bold">
                <td class="bold">Platform</td>
                {% for server in server_names %}
                <td>Platform</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">blockHeight</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('platformBlockHeight', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">p2pPortState</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('p2pPortState', 'N/A') }} {{ alerts[server] }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">httpPortState</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('httpPortState', 'N/A') }} {{ alerts[server] }}</td>
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
                <td class="{{ 'green' if heartbeat_data[server].get('produceBlockStatus', '') == 'OK' else 'red' if heartbeat_data[server].get('produceBlockStatus', '') == 'ERROR' else '' }}">{{ heartbeat_data[server].get('produceBlockStatus', 'N/A') }} {{ alerts[server] }}</td>
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

        <!-- Validators in Quorum Table -->
        <table style="width: 50%;">
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
        epoch_start_human=epoch_start_human,
        epoch_end_human=epoch_end_human,
        server_names=server_names,
        heartbeat_data=heartbeat_data,
        validators_in_quorum=validators_in_quorum,
        format_protx=format_protx,
        get_node_type=get_node_type,
        convert_to_dash=convert_to_dash,
        time_ago_from_minutes_seconds=time_ago_from_minutes_seconds,
        latest_block_validator=latest_block_validator,
        alerts=alerts,
        protx_in_second_table=protx_in_second_table
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
