import requests
from flask import Flask, render_template_string
from datetime import datetime

#HERE

app = Flask(__name__)

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

@app.route('/')
def display_validators():
    fetched_validators = fetch_validators()
    fetched_dict = {v["proTxHash"]: v for v in fetched_validators}
    total_proposed_blocks = 0
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for validator in HARD_CODED_VALIDATORS:
        protx = validator["protx"]
        if protx in fetched_dict:
            fetched_data = fetched_dict[protx]
            row = {
                "name": validator["name"],
                "protx": protx,
                "pose_penalty": fetched_data["proTxInfo"]["state"]["PoSePenalty"],
                "pose_revived_height": fetched_data["proTxInfo"]["state"]["PoSeRevivedHeight"],
                "pose_ban_height": fetched_data["proTxInfo"]["state"]["PoSeBanHeight"],
                "last_proposed_block_timestamp": fetched_data["lastProposedBlockHeader"]["timestamp"] if fetched_data["lastProposedBlockHeader"] else "N/A",
                "proposed_blocks_amount": fetched_data["proposedBlocksAmount"]
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
                "proposed_blocks_amount": "VALIDATOR NOT FOUND"
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
        <table>
            <tr>
                <th>Name</th>
                <th>ProTx</th>
                <th>PoSe Penalty</th>
                <th>PoSe Revived Height</th>
                <th>PoSe Ban Height</th>
                <th>Last Proposed Block Timestamp</th>
                <th>Proposed Blocks Amount</th>
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
            </tr>
            {% endfor %}
        </table>
        <h2>Total Proposed Blocks: {{ total_proposed_blocks }}</h2>
    </body>
    </html>
    """
    
    return render_template_string(html_template, rows=rows, total_proposed_blocks=total_proposed_blocks, current_time=current_time)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
