import json
import os
import subprocess
import sys
import base64

# Funkcje pomocnicze

def print_verbose(message, verbose):
    """Print message only in verbose mode."""
    if verbose:
        print(message)

def run_command(command, verbose=False):
    """Run a shell command and return its output."""
    print_verbose(f"Running command: {command}", verbose)
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print_verbose(f"Command output: {result.stdout.strip()}", verbose)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command {command}: {e}")
        return None

def post_json_data(url, data, verbose=False):
    """Post JSON data to a URL using curl."""
    json_data = json.dumps(data)
    curl_command = f"curl -X POST {url} -H 'Content-Type: application/json' -d '{json_data}'"
    print_verbose(f"Posting data to URL: {url} with payload: {json.dumps(data, indent=2)}", verbose)
    run_command(curl_command, verbose)

def hex_to_base64(hex_value):
    """Convert a hex string to Base64."""
    bytes_value = bytes.fromhex(hex_value)
    return base64.b64encode(bytes_value).decode('utf-8')

def load_bashrc_variables():
    """Load environment variables from ~/.bashrc."""
    bashrc_path = os.path.expanduser("~/.bashrc")
    if os.path.exists(bashrc_path):
        with open(bashrc_path, "r") as file:
            lines = file.readlines()
        for line in lines:
            if line.startswith("export"):
                try:
                    key, value = line.replace("export ", "").strip().split("=")
                    os.environ[key] = value
                except ValueError:
                    continue

def get_env_variable(name):
    """Get an environment variable and convert it to an integer if possible."""
    value = os.environ.get(name)
    return int(value) if value and value.isdigit() else None

def set_env_variable(name, value):
    """Set an environment variable and ensure it persists in .bashrc."""
    os.environ[name] = str(value)
    bashrc_path = os.path.expanduser("~/.bashrc")
    try:
        with open(bashrc_path, "r") as file:
            lines = file.readlines()
        if any(f"export {name}=" in line for line in lines):
            with open(bashrc_path, "w") as file:
                for line in lines:
                    if f"export {name}=" in line:
                        file.write(f"export {name}={value}\n")
                    else:
                        file.write(line)
        else:
            with open(bashrc_path, "a") as file:
                file.write(f"\nexport {name}={value}\n")
        print(f"Variable {name} saved to .bashrc: {value}")
    except Exception as e:
        print(f"Error saving variable {name} to .bashrc: {e}")

def main(report_url, verbose=False):
    # Load environment variables from ~/.bashrc to ensure they are available
    load_bashrc_variables()

    # Step 1: Run the dashmate status command and parse JSON output
    dashmate_status = run_command("dashmate status --format=json", verbose)
    if not dashmate_status:
        return

    try:
        status_data = json.loads(dashmate_status)
        print_verbose(f"Dashmate status JSON: {json.dumps(status_data, indent=2)}", verbose)
    except json.JSONDecodeError:
        print("Error parsing dashmate status JSON.")
        return

    # Fetch proTxHash and other data directly from the correct location
    masternode_data = status_data.get("masternode", {})
    if not masternode_data:
        print("Masternode data is missing.")
        return

    pro_tx_hash = masternode_data.get("proTxHash")
    if not pro_tx_hash:
        print("Invalid or missing proTxHash.")
        return

    # Ensure proTxHash is uppercase
    pro_tx_hash = pro_tx_hash.upper()

    # Convert pro_tx_hash from hex to Base64 to get platform_protx_hash
    platform_protx_hash = hex_to_base64(pro_tx_hash)

    # Read additional required fields
    core_block_height = status_data.get("core", {}).get("blockHeight")
    latest_block_height = status_data.get("platform", {}).get("tenderdash", {}).get("latestBlockHeight")

    # Convert latest_block_height to int to avoid TypeError
    try:
        latest_block_height = int(latest_block_height)
        print_verbose(f"Converted latest_block_height to int: {latest_block_height}", verbose)
    except ValueError:
        print("Error: latest_block_height is not a valid integer.")
        return

    # Step 2: Fetch the blockchain data and extract the blocks array
    blockchain_data = run_command("curl -s http://127.0.0.1:26657/blockchain", verbose)
    blocks = []
    if blockchain_data:
        try:
            blockchain_json = json.loads(blockchain_data)
            block_metas = blockchain_json.get("block_metas", [])
            for block_meta in block_metas:
                block = {
                    "height": block_meta.get("header", {}).get("height"),
                    "proposer_pro_tx_hash": block_meta.get("header", {}).get("proposer_pro_tx_hash")
                }
                blocks.append(block)
        except json.JSONDecodeError:
            print("Error parsing blockchain JSON.")
    
    # Step 3: Continue with the rest of your existing logic (fetching more data, producing payload)

    # Step 10: Prepare the payload with available data
    payload = {
        "serverName": run_command("whoami", verbose),
        "uptime": run_command("awk '{up=$1; print int(up/86400)\"d \"int((up%86400)/3600)\"h \"int((up%3600)/60)\"m \"int(up%60)\"s\"}' /proc/uptime", verbose),
        "uptimeInSeconds": int(float(run_command("awk '{print $1}' /proc/uptime", verbose))),
        "proTxHash": pro_tx_hash,
        "coreBlockHeight": core_block_height,
        "platformBlockHeight": latest_block_height,
        "p2pPortState": status_data.get("platform", {}).get("tenderdash", {}).get("p2pPortState"),
        "httpPortState": status_data.get("platform", {}).get("tenderdash", {}).get("httpPortState"),
        "poSePenalty": masternode_data.get("nodeState", {}).get("dmnState", {}).get("PoSePenalty"),
        "poSeRevivedHeight": masternode_data.get("nodeState", {}).get("dmnState", {}).get("PoSeRevivedHeight"),
        "poSeBanHeight": masternode_data.get("nodeState", {}).get("dmnState", {}).get("PoSeBanHeight"),
        "lastPaidHeight": masternode_data.get("nodeState", {}).get("lastPaidHeight"),
        "lastPaidTime": masternode_data.get("nodeState", {}).get("lastPaidTime"),
        "paymentQueuePosition": masternode_data.get("nodeState", {}).get("paymentQueuePosition"),
        "nextPaymentTime": masternode_data.get("nodeState", {}).get("nextPaymentTime"),
        "proposedBlockInCurrentEpoch": None,  # Add this when available
        "proposedBlockInPreviousEpoch": None,  # Add this when available
        "epochNumber": None,  # Add this when available
        "epochFirstBlockHeight": None,  # Add this when available
        "epochStartTime": None,  # Add this when available
        "previousEpochNumber": None,  # Add this when available
        "previousEpochFirstBlockHeight": None,  # Add this when available
        "previousEpochStartTime": None,  # Add this when available
        "inQuorum": None,  # Add this when available
        "validatorsInQuorum": [],  # Add this when available
        "latestBlockHash": status_data.get("platform", {}).get("tenderdash", {}).get("latestBlockHash"),
        "latestBlockHeight": latest_block_height,
        "latestBlockValidator": None,  # Add this when available
        "balance": 0,  # Add this when available
        "lastProduceBlockHeight": None,  # Add this when available
        "lastShouldProduceBlockHeight": None,  # Add this when available
        "produceBlockStatus": None,  # Add this when available
        "blocks": blocks  # Adding blocks data here
    }

    # Step 11: Send the report
    post_json_data(report_url, payload, verbose)

    # Step 12: Restart server if uptime is greater than 31 days and not in quorum
    if in_quorum is False and float(run_command("awk '{print $1}' /proc/uptime", verbose)) > 31 * 86400:
        print("Restarting server...")
        run_command("sudo reboot", verbose)

if __name__ == "__main__":
    verbose_mode = '-v' in sys.argv
    if verbose_mode:
        sys.argv.remove('-v')

    if len(sys.argv) != 2:
        print("Usage: python3 masternode_monitor.py <report_url> [-v]")
        sys.exit(1)

    report_url = sys.argv[1]
    main(report_url, verbose_mode)
