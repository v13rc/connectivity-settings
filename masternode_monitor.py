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
    """Run a shell command more safely and return its output."""
    print_verbose(f"Running command: {' '.join(command)}", verbose)
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print_verbose(f"Command output: {result.stdout.strip()}", verbose)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command {' '.join(command)}: {e}")
        return None

def post_json_data(url, data, verbose=False):
    """Post JSON data to a URL using curl."""
    json_data = json.dumps(data)
    curl_command = ["curl", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", json_data]
    print_verbose(f"Posting data to URL: {url} with payload: {json.dumps(data, indent=2)}", verbose)
    run_command(curl_command, verbose)

def hex_to_base64(hex_value):
    """Convert a hex string to Base64 with error handling."""
    try:
        bytes_value = bytes.fromhex(hex_value)
        return base64.b64encode(bytes_value).decode('utf-8')
    except ValueError as e:
        print(f"Error converting hex to base64: {e}")
        return None

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
    dashmate_status = run_command(["dashmate", "status", "--format=json"], verbose)
    if not dashmate_status:
        return

    try:
        status_data = json.loads(dashmate_status)
        print_verbose(f"Dashmate status JSON: {json.dumps(status_data, indent=2)}", verbose)
    except json.JSONDecodeError as e:
        print(f"Error parsing dashmate status JSON: {e}")
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

    p2p_port_state = status_data.get("platform", {}).get("tenderdash", {}).get("p2pPortState")
    http_port_state = status_data.get("platform", {}).get("tenderdash", {}).get("httpPortState")
    po_se_penalty = masternode_data.get("nodeState", {}).get("dmnState", {}).get("PoSePenalty")
    po_se_revived_height = masternode_data.get("nodeState", {}).get("dmnState", {}).get("PoSeRevivedHeight")
    po_se_ban_height = masternode_data.get("nodeState", {}).get("dmnState", {}).get("PoSeBanHeight")
    last_paid_height = masternode_data.get("nodeState", {}).get("lastPaidHeight")
    last_paid_time = masternode_data.get("nodeState", {}).get("lastPaidTime")
    payment_queue_position = masternode_data.get("nodeState", {}).get("paymentQueuePosition")
    next_payment_time = masternode_data.get("nodeState", {}).get("nextPaymentTime")
    latest_block_hash = status_data.get("platform", {}).get("tenderdash", {}).get("latestBlockHash")

    # Extract service data and build platform_service_address
    service = masternode_data.get("nodeState", {}).get("dmnState", {}).get("service", "")
    node_address = service.split(":")[0]
    platform_http_port = masternode_data.get("nodeState", {}).get("dmnState", {}).get("platformHTTPPort", "")
    platform_service_address = f"{node_address}:{platform_http_port}"

    # Initialize variables with default values to avoid unbound errors
    epoch_number = None
    epoch_first_block_height = None
    epoch_start_time = None
    previous_epoch_number = None
    previous_epoch_first_block_height = None
    previous_epoch_start_time = None
    proposed_block_in_previous_epoch = None
    proposed_block_in_current_epoch = None
    balance = None

    # Get or initialize environment variables for block heights
    last_produce_block_height = get_env_variable("LAST_PRODUCED_BLOCK_HEIGHT")
    last_should_produce_block_height = get_env_variable("LAST_SHOULD_PRODUCE_BLOCK_HEIGHT")

    # Step 3: Fetch current and previous epoch data
    epoch_info = run_command(
        ["grpcurl", "-proto", "platform.proto", "-d", '{"v0": {"count": 2}}', platform_service_address, "org.dash.platform.dapi.v0.Platform/getEpochsInfo"],
        verbose
    )
    if epoch_info:
        try:
            epoch_info_json = json.loads(epoch_info)
            epoch_infos = epoch_info_json.get("v0", {}).get("epochs", {}).get("epochInfos", [])
            if len(epoch_infos) == 2:
                previous_epoch = epoch_infos[0]
                current_epoch = epoch_infos[1]
                epoch_number = current_epoch.get("number", 0)
                epoch_first_block_height = current_epoch.get("firstBlockHeight", "")
                epoch_start_time = current_epoch.get("startTime", "")
                previous_epoch_number = previous_epoch.get("number", 0)
                previous_epoch_first_block_height = previous_epoch.get("firstBlockHeight", "")
                previous_epoch_start_time = previous_epoch.get("startTime", "")
        except json.JSONDecodeError as e:
            print(f"Error parsing epoch info JSON: {e}")

    # Step 4: Fetch proposed blocks in the previous epoch
    previous_proposed_blocks = run_command(
        ["grpcurl", "-proto", "platform.proto", "-d", f'{{"v0": {{"ids": ["{platform_protx_hash}"], "epoch": {previous_epoch_number}}}}}', platform_service_address, "org.dash.platform.dapi.v0.Platform/getEvonodesProposedEpochBlocksByIds"],
        verbose
    )
    if previous_proposed_blocks:
        try:
            previous_blocks_json = json.loads(previous_proposed_blocks)
            count_info = previous_blocks_json.get("v0", {}).get("evonodesProposedBlockCountsInfo", {}).get("evonodesProposedBlockCounts", [])
            proposed_block_in_previous_epoch = count_info[0].get("count", 0) if count_info else 0
        except (json.JSONDecodeError, IndexError, KeyError):
            proposed_block_in_previous_epoch = 0

    # Step 5: Fetch proposed blocks in the current epoch
    current_proposed_blocks = run_command(
        ["grpcurl", "-proto", "platform.proto", "-d", f'{{"v0": {{"ids": ["{platform_protx_hash}"], "epoch": {epoch_number}}}}}', platform_service_address, "org.dash.platform.dapi.v0.Platform/getEvonodesProposedEpochBlocksByIds"],
        verbose
    )
    if current_proposed_blocks:
        try:
            current_blocks_json = json.loads(current_proposed_blocks)
            count_info = current_blocks_json.get("v0", {}).get("evonodesProposedBlockCountsInfo", {}).get("evonodesProposedBlockCounts", [])
            proposed_block_in_current_epoch = count_info[0].get("count", 0) if count_info else 0
        except (json.JSONDecodeError, IndexError, KeyError):
            proposed_block_in_current_epoch = 0

    # Step 6: Fetch balance for the node
    balance_response = run_command(
        ["grpcurl", "-proto", "platform.proto", "-d", f'{{"v0": {{"id": "{platform_protx_hash}"}}}}', platform_service_address, "org.dash.platform.dapi.v0.Platform/getIdentityBalance"],
        verbose
    )
    if balance_response:
        try:
            balance_json = json.loads(balance_response)
            balance = balance_json.get("v0", {}).get("balance", "0")
        except json.JSONDecodeError:
            balance = "0"
    balance = int(balance) if balance.isdigit() else 0

    # Step 7: Get latest block validator using the updated command
    latest_block_validator = run_command(
        ["curl", "-s", f"http://127.0.0.1:26657/block?height={latest_block_height}"]
    )
    try:
        block_data = json.loads(latest_block_validator)
        latest_block_validator = block_data['block']['header']['proposer_pro_tx_hash'].upper()
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing block data: {e}")
        latest_block_validator = None

    print_verbose(f"Latest block {latest_block_height} proposed by {latest_block_validator}.", verbose)

    # Step 8: Determine block production status
    print_verbose("Determining block production status.", verbose)
    if last_produce_block_height is not None:
        print_verbose(f"Last produced block height: {last_produce_block_height}", verbose)
        print_verbose(f"Last should produce block height: {last_should_produce_block_height}", verbose)
        if last_produce_block_height == last_should_produce_block_height:
            produce_block_status = "OK"
            print_verbose("Produce block status: OK", verbose)
        else:
            produce_block_status = "ERROR"
            print_verbose("Produce block status: ERROR", verbose)
    else:
        produce_block_status = "NO_DATA"
        print_verbose("Produce block status: NO_DATA", verbose)

    # Step 9: Check if proTxHash is in active validators
    print_verbose("Checking if validator is in quorum.", verbose)
    active_validators = run_command(
        ["curl", "-s", "http://127.0.0.1:26657/dump_consensus_state"]
    )
    try:
        consensus_data = json.loads(active_validators)
        active_validators_list = [validator['pro_tx_hash'].upper() for validator in consensus_data['result']['round_state']['validators']['validators']]
        validators_in_quorum = active_validators_list
        in_quorum = pro_tx_hash in active_validators_list
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing active validators: {e}")
        in_quorum = None
        validators_in_quorum = []

    # Step 10: Fetch blocks from blockchain and extract height and proposer_pro_tx_hash
    blocks_response = run_command(
        ["curl", "-s", "http://127.0.0.1:26657/blockchain"]
    )
    
    try:
        blockchain_data = json.loads(blocks_response)
        blocks = []
        for block_meta in blockchain_data.get("result", {}).get("block_metas", []):
            block = {
                "height": block_meta["header"]["height"],
                "proposer_pro_tx_hash": block_meta["header"]["proposer_pro_tx_hash"].upper()
            }
            blocks.append(block)
        print_verbose(f"Parsed blocks with height and proposer_pro_tx_hash: {blocks}", verbose)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing blocks JSON: {e}")
        blocks = []

    # Step 11: Prepare the payload with available data
    payload = {
        "serverName": run_command(["whoami"], verbose),
        "uptime": run_command(["awk", '{up=$1; print int(up/86400)"d "int((up%86400)/3600)"h "int((up%3600)/60)"m "int(up%60)"s"}', "/proc/uptime"], verbose),
        "uptimeInSeconds": int(float(run_command(["awk", "{print $1}", "/proc/uptime"], verbose))),
        "proTxHash": pro_tx_hash,
        "coreBlockHeight": core_block_height,
        "platformBlockHeight": latest_block_height,
        "p2pPortState": p2p_port_state,
        "httpPortState": http_port_state,
        "poSePenalty": po_se_penalty,
        "poSeRevivedHeight": po_se_revived_height,
        "poSeBanHeight": po_se_ban_height,
        "lastPaidHeight": last_paid_height,
        "lastPaidTime": last_paid_time,
        "paymentQueuePosition": payment_queue_position,
        "nextPaymentTime": next_payment_time,
        "proposedBlockInCurrentEpoch": proposed_block_in_current_epoch,
        "proposedBlockInPreviousEpoch": proposed_block_in_previous_epoch,
        "epochNumber": epoch_number,
        "epochFirstBlockHeight": epoch_first_block_height,
        "epochStartTime": epoch_start_time,
        "previousEpochNumber": previous_epoch_number,
        "previousEpochFirstBlockHeight": previous_epoch_first_block_height,
        "previousEpochStartTime": previous_epoch_start_time,
        "inQuorum": in_quorum,
        "validatorsInQuorum": validators_in_quorum,
        "latestBlockHash": latest_block_hash,
        "latestBlockHeight": latest_block_height,
        "latestBlockValidator": latest_block_validator,
        "balance": balance,
        "lastProduceBlockHeight": last_produce_block_height,
        "lastShouldProduceBlockHeight": last_should_produce_block_height,
        "produceBlockStatus": produce_block_status,
        "blocks": blocks
    }

    # Filter out None values from the payload
    payload = {k: v for k, v in payload.items() if v is not None}

    # Step 12: Send the report
    post_json_data(report_url, payload, verbose)

    # Step 13: Restart server if uptime is greater than 31 days and not in quorum
    if in_quorum is False and float(run_command(["awk", "{print $1}", "/proc/uptime"], verbose)) > 31 * 86400:
        print("Restarting server...")
        run_command(["sudo", "reboot"], verbose)

if __name__ == "__main__":
    verbose_mode = '-v' in sys.argv
    if verbose_mode:
        sys.argv.remove('-v')

    if len(sys.argv) != 2:
        print("Usage: python3 masternode_monitor.py <report_url> [-v]")
        sys.exit(1)

    report_url = sys.argv[1]
    main(report_url, verbose_mode)
