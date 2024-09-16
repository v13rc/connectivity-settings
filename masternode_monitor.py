import json
import os
import subprocess
import sys


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


def get_json_response(url, verbose=False):
    """Get JSON response from a URL using curl."""
    curl_command = f"curl -s {url}"
    if verbose:
        print(f"Fetching URL: {url}")
    response = run_command(curl_command, verbose)
    if response:
        try:
            json_response = json.loads(response)
            if verbose:
                print(f"Received JSON: {json.dumps(json_response, indent=2)}")
            return json_response
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response from {url}: {e}")
    return None


def post_json_data(url, data, verbose=False):
    """Post JSON data to a URL using curl."""
    json_data = json.dumps(data)
    curl_command = f"curl -X POST {url} -H 'Content-Type: application/json' -d '{json_data}'"
    if verbose:
        print(f"Posting data to URL: {url} with payload: {json.dumps(data, indent=2)}")
    run_command(curl_command, verbose)


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

    # Fetch proTxHash directly from the correct location
    masternode_data = status_data.get("masternode", {})
    if not masternode_data:
        print("Masternode data is missing.")
        return

    pro_tx_hash = masternode_data.get("proTxHash")
    if not pro_tx_hash:
        print("Invalid or missing proTxHash.")
        return

    # Read other required fields
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

    # Step 3: Fetch status from external service
    status_info = get_json_response("https://platform-explorer.pshenmic.dev/status", verbose)
    if not status_info:
        epoch_number = None
        epoch_first_block_height = None
        epoch_start_time = None
        epoch_end_time = None
        proposed_block_in_current_epoch = None
    else:
        epoch_number = status_info.get("epoch", {}).get("number")
        epoch_first_block_height = status_info.get("epoch", {}).get("firstBlockHeight")
        epoch_start_time = status_info.get("epoch", {}).get("startTime")
        epoch_end_time = status_info.get("epoch", {}).get("endTime")

        # Step 4: Fetch validator data
        proposed_block_in_current_epoch = 0
        page = 1
        while True:
            validator_info = get_json_response(
                f"https://platform-explorer.pshenmic.dev/validator/{pro_tx_hash.upper()}?limit=100&page={page}",
                verbose
            )
            if not validator_info or "resultSet" not in validator_info:
                break

            for result in validator_info["resultSet"]:
                if result["header"]["height"] > epoch_first_block_height:
                    proposed_block_in_current_epoch += 1

            # Check pagination
            if len(validator_info["resultSet"]) < 100:
                break
            page += 1

    # Step 5: Collect server and system information
    server_name = run_command("whoami", verbose)
    uptime = run_command("awk '{up=$1; print int(up/86400)\"d \"int((up%86400)/3600)\"h \"int((up%3600)/60)\"m \"int(up%60)\"s\"}' /proc/uptime", verbose)
    uptime_in_seconds = run_command("awk '{print $1}' /proc/uptime", verbose)

    # Step 6: Send report
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
        "epochNumber": epoch_number,
        "epochFirstBlockHeight": epoch_first_block_height,
        "epochStartTime": epoch_start_time,
        "epochEndTime": epoch_end_time
    }

    post_json_data(report_url, payload, verbose)

    # Step 7: Fetch active validators
    active_validators = run_command("curl -s http://127.0.0.1:26657/dump_consensus_state | jq '.round_state.validators.validators[].pro_tx_hash'", verbose)
    if not active_validators or len(active_validators.splitlines()) < 67:
        print("Insufficient active validators or error fetching them.")
        return

    # Step 8: Check if proTxHash is in active validators
    if pro_tx_hash.upper() in active_validators.upper().splitlines():
        print("proTxHash is in active validators list.")
        return

    # Step 9: Restart server if uptime is greater than 24 hours
    if float(uptime_in_seconds) > 86400:
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
