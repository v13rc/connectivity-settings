import json
import os
import subprocess
import sys
import base64

def run_command(command, verbose=False):
    """Run a shell command and return its output."""
    if verbose:
        print(f"Running command: {command}")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        if verbose:
            print(f"Command output: {result.stdout.strip()}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command {command}: {e}")
        return None

def post_json_data(url, data, verbose=False):
    """Post JSON data to a URL using curl."""
    json_data = json.dumps(data)
    curl_command = f"curl -X POST {url} -H 'Content-Type: application/json' -d '{json_data}'"
    if verbose:
        print(f"Posting data to URL: {url} with payload: {json.dumps(data, indent=2)}")
    run_command(curl_command, verbose)

def hex_to_base64(hex_value):
    """Convert a hex string to Base64."""
    bytes_value = bytes.fromhex(hex_value)
    return base64.b64encode(bytes_value).decode('utf-8')

def main(report_url, verbose=False):
    # Step 1: Run the dashmate status command and parse JSON output
    dashmate_status = run_command("dashmate status --format=json", verbose)
    if not dashmate_status:
        return

    try:
        status_data = json.loads(dashmate_status)
        if verbose:
            print(f"Dashmate status JSON: {json.dumps(status_data, indent=2)}")
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

    # Convert pro_tx_hash from hex to Base64 to get platform_protx_hash
    platform_protx_hash = hex_to_base64(pro_tx_hash)

    # Read additional required fields
    core_block_height = status_data.get("core", {}).get("blockHeight")
    latest_block_height = status_data.get("platform", {}).get("tenderdash", {}).get("latestBlockHeight")
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

    # Step 3: Fetch current and previous epoch data
    epoch_info = run_command(
        f"grpcurl -proto platform.proto -d '{{\"v0\": {{\"count\":2}} }}' {platform_service_address} org.dash.platform.dapi.v0.Platform/getEpochsInfo",
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
        f"grpcurl -proto platform.proto -d '{{\"v0\": {{\"ids\": [\"{platform_protx_hash}\"], \"epoch\": {previous_epoch_number}}} }}' {platform_service_address} org.dash.platform.dapi.v0.Platform/getEvonodesProposedEpochBlocksByIds",
        verbose
    )
    if previous_proposed_blocks:
        try:
            previous_blocks_json = json.loads(previous_proposed_blocks)
            count_info = previous_blocks_json.get("v0", {}).get("evonodesProposedBlockCountsInfo", {}).get(
                "evonodesProposedBlockCounts", [])
            proposed_block_in_previous_epoch = count_info[0].get("count", 0) if count_info else 0
        except (json.JSONDecodeError, IndexError, KeyError):
            proposed_block_in_previous_epoch = 0

    # Step 5: Fetch proposed blocks in the current epoch
    current_proposed_blocks = run_command(
        f"grpcurl -proto platform.proto -d '{{\"v0\": {{\"ids\": [\"{platform_protx_hash}\"], \"epoch\": {epoch_number}}} }}' {platform_service_address} org.dash.platform.dapi.v0.Platform/getEvonodesProposedEpochBlocksByIds",
        verbose
    )
    if current_proposed_blocks:
        try:
            current_blocks_json = json.loads(current_proposed_blocks)
            count_info = current_blocks_json.get("v0", {}).get("evonodesProposedBlockCountsInfo", {}).get(
                "evonodesProposedBlockCounts", [])
            proposed_block_in_current_epoch = count_info[0].get("count", 0) if count_info else 0
        except (json.JSONDecodeError, IndexError, KeyError):
            proposed_block_in_current_epoch = 0

    # Step 6: Fetch balance for the node
    balance_response = run_command(
        f"grpcurl -proto platform.proto -d '{{\"v0\": {{\"id\": \"{platform_protx_hash}\"}} }}' {platform_service_address} org.dash.platform.dapi.v0.Platform/getIdentityBalance",
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
        f"curl -s http://127.0.0.1:26657/block?height={latest_block_height} | jq -r '.block.header.proposer_pro_tx_hash'",
        verbose
    )

    # Step 8: Collect server and system information
    server_name = run_command("whoami", verbose)
    uptime = run_command(
        "awk '{up=$1; print int(up/86400)\"d \"int((up%86400)/3600)\"h \"int((up%3600)/60)\"m \"int(up%60)\"s\"}' /proc/uptime",
        verbose)
    uptime_in_seconds = run_command("awk '{print $1}' /proc/uptime", verbose)

    # Step 9: Check if proTxHash is in active validators
    active_validators = run_command(
        "curl -s http://127.0.0.1:26657/dump_consensus_state | jq '.round_state.validators.validators[].pro_tx_hash'",
        verbose)
    if not active_validators or len(active_validators.splitlines()) < 67:
        print("Insufficient active validators or error fetching them.")
        in_quorum = None
        validators_in_quorum = []
    else:
        active_validators_list = [validator.strip('"') for validator in active_validators.splitlines()]
        validators_in_quorum = active_validators_list
        in_quorum = pro_tx_hash.upper() in active_validators_list

    # Prepare the payload with available data
    payload = {
        "serverName": server_name,
        "uptime": uptime,
        "uptimeInSeconds": int(float(uptime_in_seconds)),
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
        "balance": balance
    }

    # Filter out None values from the payload
    payload = {k: v for k, v in payload.items() if v is not None}

    # Step 10: Send the report
    post_json_data(report_url, payload, verbose)

    # Step 11: Restart server if uptime is greater than 31 days and not in quorum
    if in_quorum is False and float(uptime_in_seconds) > 31 * 86400:
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
