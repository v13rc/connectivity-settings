import os
from flask import Flask, request, render_template_string, jsonify
from datetime import datetime, timedelta, timezone
import logging
import json
import fcntl

# Import blueprint from monitor_server_routes.py
from monitor_server_routes import monitor_routes_bp

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

# Register blueprint
app.register_blueprint(monitor_routes_bp)

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
            fcntl.flock(f, fcntl.LOCK_SH)  # Zakładanie blokady współdzielonej dla odczytu
            logging.debug(f"Loading data from file {filename}.")
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)  # Zwolnienie blokady
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
            fcntl.flock(f, fcntl.LOCK_EX)  # Zakładanie wyłącznej blokady dla zapisu
            json.dump(data, f, indent=4, ensure_ascii=False)
            fcntl.flock(f, fcntl.LOCK_UN)  # Zwolnienie blokady

        os.replace(temp_filename, filename)  # Atomowa operacja zamiany plików
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
    dt = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).astimezone(timezone(timedelta(hours=2)))
    return dt.strftime('%b %d %H:%M')


def time_ago_from_minutes_seconds(timestamp):
    """Convert a timestamp to a format showing minutes and seconds elapsed since the timestamp."""
    now = datetime.now(timezone.utc)
    elapsed = now - datetime.fromtimestamp(timestamp, tz=timezone.utc)
    minutes, seconds = divmod(elapsed.total_seconds(), 60)
    is_alert = minutes > 30
    return f"{int(minutes)}m {int(seconds)}s", is_alert

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    global heartbeat_data
    data = request.get_json()
    logging.debug(f"Received heartbeat data: {data}")

    server_name = data.get('serverName')
    if server_name:
        # Zapisz czas raportowania jako znacznik czasu UTC
        data['lastReportTime'] = datetime.now(timezone.utc).timestamp()

        # Pobierz istniejące dane serwera, jeśli istnieją
        existing_data = heartbeat_data.get(server_name, {})
        
        # Obsługa bloków
        new_blocks = data.get('blocks', [])
        existing_blocks = existing_data.get('blocks', [])
        
        # Dodaj nowe bloki do istniejących bloków
        combined_blocks = existing_blocks + new_blocks

        # Usuń duplikaty bloków na podstawie `height` i posortuj malejąco
        unique_blocks = {block['height']: block for block in combined_blocks}.values()
        sorted_blocks = sorted(unique_blocks, key=lambda b: b['height'], reverse=True)

        # Przechowuj maksymalnie 1000 bloków
        data['blocks'] = sorted_blocks[:1000]

        # Sprawdź, czy otrzymaliśmy nowe wartości validatorsInQuorum i czy są one niepuste
        new_validators_in_quorum = data.get('validatorsInQuorum', [])
        existing_validators_in_quorum = existing_data.get('validatorsInQuorum', [])

        if new_validators_in_quorum and new_validators_in_quorum != existing_validators_in_quorum:
            data['prevValidatorsInQuorum'] = existing_validators_in_quorum
        
        # Zapisz nowe wartości w validatorsInQuorum tylko, jeśli są niepuste
        if new_validators_in_quorum:
            data['validatorsInQuorum'] = new_validators_in_quorum

        # Zapisz dane serwera
        heartbeat_data[server_name] = data

        # Zapisz dane do pliku i zwróć wynik
        result = save_to_file(heartbeat_data, HEARTBEAT_FILE)

        # Zwróć odpowiedni kod statusu HTTP na podstawie wyniku zapisu
        status_code = 200 if result["status"] == "success" else 500

        # Zwróć odpowiedź JSON z wynikiem operacji zapisu
        logging.debug(f"Heartbeat data processed with status: {result['status']}.")
        return jsonify(result), status_code
    else:
        logging.debug("Invalid data format for heartbeat.")
        # Zwróć komunikat błędu, jeśli format danych wejściowych jest nieprawidłowy
        return jsonify({"status": "error", "message": "Invalid data format."}), 400


@app.route('/', methods=['GET'])
def display_validators():
    global heartbeat_data
    logging.debug("Loading heartbeat data from file.")
    heartbeat_data = load_from_file(HEARTBEAT_FILE)

    current_time = datetime.now().astimezone(timezone(timedelta(hours=1))).strftime("%Y-%m-%d %H:%M:%S")
    server_names = sorted(heartbeat_data.keys())

    # Pobierz pierwszy serwer z heartbeat_data
    if heartbeat_data:
        selected_server_name = next(iter(heartbeat_data))  # Pobiera pierwszy klucz (nazwę serwera)
        selected_server_data = heartbeat_data.get(selected_server_name, {})
    else:
        selected_server_name = None
        selected_server_data = {}

    blocks = selected_server_data.get('blocks', [])
    
    # Posortuj bloki malejąco po wysokości
    sorted_blocks = sorted(blocks, key=lambda x: x['height'], reverse=True)
    
    # Wyświetl maksymalnie 1000 bloków
    displayed_blocks = sorted_blocks[:1000]

    # Przygotowanie validatorsInQuorum i prevValidatorsInQuorum dla wszystkich serwerów
    validators_in_quorum = []
    prev_validators_in_quorum = []

    for server in heartbeat_data.values():
        # Odwrócenie list validatorsInQuorum i prevValidatorsInQuorum przed przekazaniem
        validators_in_quorum = list(reversed(server.get('validatorsInQuorum', [])))
        prev_validators_in_quorum = list(reversed(server.get('prevValidatorsInQuorum', [])))

    # Other existing aggregate data calculations
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

    highest_platform_block_height = 0
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
            latest_block_height = max(latest_block_height, int(server.get('platformBlockHeight', latest_block_height)))
            epoch_start_time = int(server.get('epochStartTime', epoch_start_time))

    total_balance_dash = convert_to_dash(total_balance_credits)
    blocks_in_epoch = latest_block_height - epoch_first_block_height
    share_proposed_blocks = (total_proposed_blocks / blocks_in_epoch) * 100 if blocks_in_epoch else 0
    epoch_start_human = format_timestamp(epoch_start_time)
    epoch_end_time = datetime.fromtimestamp(epoch_start_time / 1000, tz=timezone.utc) + timedelta(days=9.125)
    epoch_end_human = epoch_end_time.astimezone(timezone(timedelta(hours=2))).strftime('%b %d %H:%M')
    
    # Poprawiona logika obliczania max_length: suma validatorów oraz porównanie z liczbą bloków
    max_length = max(len(validators_in_quorum) + len(prev_validators_in_quorum), len(displayed_blocks))

    num_unique_validators = len({block["proposer_pro_tx_hash"] for block in blocks})
    t_share = (evonodes / num_unique_validators) * 100 if num_unique_validators > 0 else 0

    # Helper function to format ProTxHash to wrap into four lines
    def format_protx(protx):
        return '<br>'.join([protx[i:i+16] for i in range(0, len(protx), 16)])

    # Determine the type (Evonode or Masternode)
    def get_node_type(server):
        platform_height = heartbeat_data[server].get('platformBlockHeight', 0)
        return 'Evonode' if platform_height > 0 else 'Masternode'

    # Get the set of ProTxHashes in the second table to compare with validators in quorum
    protx_in_second_table = {heartbeat_data[server].get('proTxHash') for server in server_names}

    # Generate alerts for each node
    alerts = {}
    for server in server_names:
        alerts[server] = []
        data = heartbeat_data[server]

        # Check conditions for alerts
        if data.get('poSePenalty', 0) != 0:
            alerts[server].append(f"ALERT_PENALTY_{server.upper()}")
        if data.get('poSeBanHeight', -1) != -1:
            alerts[server].append(f"ALERT_{server.upper()}_POSEBAN")
        if data.get('produceBlockStatus', '') == 'ERROR':
            alerts[server].append(f"ALERT_{server.upper()}_BLOCKSTATUS")
        last_report_time, is_alert = time_ago_from_minutes_seconds(data.get('lastReportTime', 0))
        if is_alert:
            alerts[server].append(f"ALERT_{server.upper()}_LASTREPORT")

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
            .red-bold {
                color: red;
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
            .hidden {
                display: none;
            }
            .light-grey {
                background-color: #f0f0f0;  /* Jasnoszare tło */
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
                <th>t.share</th>
                <th>allNodes</th> 
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
                <td>{{ '{:.2f}'.format(t_share) }}%</td>
                <td>{{ num_unique_validators }}</td>
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
                {% set last_report_time, is_alert = time_ago_from_minutes_seconds(heartbeat_data[server].get('lastReportTime', 0)) %}
                <td class="{{ 'red-bold' if is_alert else '' }}">{{ last_report_time }}{% if is_alert %}<span class="hidden">ALERT_{{ server.upper() }}_LASTREPORT</span>{% endif %}</td>
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
                <td class="{{ 'red-bold' if heartbeat_data[server].get('poSePenalty', 0) != 0 else '' }}">{{ heartbeat_data[server].get('poSePenalty', 'N/A') }}{% if heartbeat_data[server].get('poSePenalty', 0) != 0 %}<span class="hidden">ALERT_PENALTY_{{ server.upper() }}</span>{% endif %}</td>
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
                <td class="{{ 'red-bold' if heartbeat_data[server].get('poSeBanHeight', -1) != -1 else '' }}">{{ heartbeat_data[server].get('poSeBanHeight', 'N/A') }}{% if heartbeat_data[server].get('poSeBanHeight', -1) != -1 %}<span class="hidden">ALERT_{{ server.upper() }}_POSEBAN</span>{% endif %}</td>
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
                <td class="bold">producedBlocks</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('proposedBlockInCurrentEpoch', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">Credits</td>
                {% for server in server_names %}
                <td>{{ heartbeat_data[server].get('balance', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">Dash</td>
                {% for server in server_names %}
                <td>{{ '{:.8f}'.format(heartbeat_data[server].get('balance', 0) / 100000000000) }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">inQuorum</td>
                {% for server in server_names %}
                <td class="{{ 'green' if heartbeat_data[server].get('inQuorum', False) else '' }}">{{ heartbeat_data[server].get('inQuorum', 'N/A') }}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">p2pPortState</td>
                {% for server in server_names %}
                <td class="{{ 'red-bold' if heartbeat_data[server].get('p2pPortState', 'OPEN') != 'OPEN' else '' }}">{{ heartbeat_data[server].get('p2pPortState', 'N/A') }}{% if heartbeat_data[server].get('p2pPortState', 'OPEN') != 'OPEN' %}<span class="hidden">ALERT_{{ server.upper() }}_P2P</span>{% endif %}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">httpPortState</td>
                {% for server in server_names %}
                <td class="{{ 'red-bold' if heartbeat_data[server].get('httpPortState', 'OPEN') != 'OPEN' else '' }}">{{ heartbeat_data[server].get('httpPortState', 'N/A') }}{% if heartbeat_data[server].get('httpPortState', 'OPEN') != 'OPEN' %}<span class="hidden">ALERT_{{ server.upper() }}_HTTP</span>{% endif %}</td>
                {% endfor %}
            </tr>
            <tr>
                <td class="bold">produceBlockStatus</td>
                {% for server in server_names %}
                <td class="{{ 'green' if heartbeat_data[server].get('produceBlockStatus', '') == 'OK' else 'red-bold' if heartbeat_data[server].get('produceBlockStatus', '') == 'ERROR' else '' }}">{{ heartbeat_data[server].get('produceBlockStatus', 'N/A') }}{% if heartbeat_data[server].get('produceBlockStatus', '') == 'ERROR' %}<span class="hidden">ALERT_{{ server.upper() }}_BLOCKSTATUS</span>{% endif %}</td>
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
        
        <!-- Połączona tabela z walidatorami i blokami -->
        <table>
        <tr>
    <th style="width: 10%;">#</th>
    <th style="width: 40%;">Validators in Quorum</th>
    <th style="width: 10%;">Block Height</th>
    <th style="width: 40%;">Proposer</th>
</tr>
{% for i in range(max_length) %}
<tr>
    <td>{{ i + 1 }}</td>

    <!-- Kolumna z walidatorami -->
    {% if i < validators_in_quorum|length %}
        <td>
            <span class="{{ 'validator-in-quorum' if validators_in_quorum[i] in protx_in_second_table else '' }} {{ 'highlight-latest' if validators_in_quorum[i] == latest_block_validator else '' }}">
                {{ validators_in_quorum[i] }}
            </span>
        </td>
    {% elif i - validators_in_quorum|length < prev_validators_in_quorum|length %}
        <!-- Dodanie klasy light-grey do całej komórki (td) -->
        <td class="light-grey">
            <span class="{{ 'validator-in-quorum' if prev_validators_in_quorum[i - validators_in_quorum|length] in protx_in_second_table else '' }}">
                {{ prev_validators_in_quorum[i - validators_in_quorum|length] }}
            </span>
        </td>
    {% else %}
        <td>&nbsp;</td>
    {% endif %}

    <!-- Kolumna z wysokościami bloków -->
    <td>
        {% if i < displayed_blocks|length %}
            {{ displayed_blocks[i].height }}
        {% else %}
            &nbsp;
        {% endif %}
    </td>

    <!-- Kolumna z proposerami bloków -->
    <td>
        {% if i < displayed_blocks|length %}
            <span class="{{ 'validator-in-quorum' if displayed_blocks[i].proposer_pro_tx_hash in protx_in_second_table else '' }} {{ 'green bold' if displayed_blocks[i].proposer_pro_tx_hash in protx_in_second_table else '' }}">
                {{ displayed_blocks[i].proposer_pro_tx_hash }}
            </span>
        {% else %}
            &nbsp;
        {% endif %}
    </td>
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
        prev_validators_in_quorum = prev_validators_in_quorum,
        format_protx=format_protx,
        get_node_type=get_node_type,
        convert_to_dash=convert_to_dash,
        time_ago_from_minutes_seconds=time_ago_from_minutes_seconds,
        latest_block_validator=latest_block_validator,
        protx_in_second_table=protx_in_second_table,
        alerts=alerts,
        displayed_blocks=displayed_blocks,
        max_length=max_length,
        t_share=t_share,
        num_unique_validators=num_unique_validators 
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
