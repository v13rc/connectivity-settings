import requests
from flask import Flask, render_template_string
from datetime import datetime

VALIDATORS_FILE = 'validators.txt'
API_URL = "https://platform-explorer.pshenmic.dev/validators"
STATUS_API_URL = "https://platform-explorer.pshenmic.dev/status"

app = Flask(__name__)

def load_validators_from_file():
    validators = []
    with open(VALIDATORS_FILE, 'r') as file:
        for line in file:
            name, protx = line.strip().split(',')
            validators.append({"name": name, "protx": protx})
    return validators

def fetch_validators():
    validators = []
    page = 1
    limit = 100
    while True:
        response = requests.get(f"{API_URL}?limit={limit}&page={page}")
        data = response.json()
        validators.extend(data["resultSet"])
        if len(validators) >= data["pagination"]["total"]:
            break
        page += 1
    return validators

def fetch_epoch_info():
    response = requests.get(STATUS_API_URL)
    data = response.json()
    epoch_number = data["epoch"]["number"]
    first_block_height = data["epoch"]["firstBlockHeight"]
    epoch_start_time = datetime.fromtimestamp(data["epoch"]["startTime"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
    epoch_end_time = datetime.fromtimestamp(data["epoch"]["endTime"] / 1000).strftime("%Y-%m-%d %H:%M:%S")
    return epoch_number, first_block_height, epoch_start_time, epoch_end_time

def fetch_validator_blocks(protx, first_block_height):
    blocks = []
    page = 1
    limit = 100
    while True:
        response = requests.get(f"https://platform-explorer.pshenmic.dev/validator/{protx}/blocks?limit={limit}&page={page}")
        data = response.json()
        blocks += [block for block in data["resultSet"] if block["header"]["height"] >= first_block_height]
        if len(blocks) >= data["pagination"]["total"]:
            break
        page += 1
    return len(blocks)

@app.route('/')
def display_validators():
    hard_coded_validators = load_validators_from_file()
    fetched_validators = fetch_validators()
    fetched_dict = {v["proTxHash"]: v for v in fetched_validators}
    total_proposed_blocks = 0
    total_blocks_current_epoch = 0
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    epoch_number, first_block_height, epoch_start_time, epoch_end_time = fetch_epoch_info()
    rows = []

    for validator in hard_coded_validators:
        protx = validator["protx"]
        if protx in fetched_dict:
            fetched_data = fetched_dict[protx]
            blocks_count = fetch_validator_blocks(protx, first_block_height)
            total_blocks_current_epoch += blocks_count
            row = {
                "name": validator["name"],
                "protx": protx,
                "pose_penalty": fetched_data["proTxInfo"]["state"]["PoSePenalty"],
                "pose_revived_height": fetched_data["proTxInfo"]["state"]["PoSeRevivedHeight"],
                "pose_ban_height": fetched_data["proTxInfo"]["state"]["PoSeBanHeight"],
                "last_proposed_block_timestamp": fetched_data["lastProposedBlockHeader"]["timestamp"] if fetched_data["lastProposedBlockHeader"] else "N/A",
                "proposed_blocks_amount": fetched_data["proposedBlocksAmount"],
                "blocks_count": blocks_count
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
                "blocks_count": "VALIDATOR NOT FOUND"
            }
        rows.append(row)

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
                <td>{{ row.name }}</td>
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
    </body>
    </html>
    """
    
    return render_template
