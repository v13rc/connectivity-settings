import json
import os
import subprocess
import sys
import base64
import hashlib
import time
import random

# Checking VPN functions

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

def check_dns_connectivity(verbose=False):
    """Check if there is connectivity to DNS 8.8.8.8."""
    if verbose:
        print("Checking DNS connectivity...")
    result = run_command("ping -c 1 8.8.8.8", verbose)
    if result and "1 received" in result:
        if verbose:
            print("DNS connectivity is OK.")
        return True
    else:
        if verbose:
            print("DNS connectivity failed.")
        return False

def restart_openvpn_service(verbose=False):
    """Restart the OpenVPN client service."""
    if verbose:
        print("Restarting OpenVPN service...")
    result = run_command("sudo systemctl restart openvpn@client", verbose)
    if verbose:
        print(f"OpenVPN service restart result: {result}")

def ensure_vpn_connectivity(verbose=False):
    """Ensure VPN is connected by checking DNS and restarting if necessary."""
    if not check_dns_connectivity(verbose):
        print("No connectivity to DNS. Restarting OpenVPN service.")
        restart_openvpn_service(verbose)
        time.sleep(10)  # Give some time for the service to restart
        if not check_dns_connectivity(verbose):
            print("DNS connectivity is still not restored after restart.")
        else:
            print("DNS connectivity restored after restarting OpenVPN.")

# Helpers

def compute_hash(value):
    """Compute the hash of a given string or list."""
    return hashlib.sha256(str(value).encode()).hexdigest()

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
        
def fetch_blockchain_data(verbose=False):
    """Fetch blockchain data and extract blocks with height and proposer_pro_tx_hash."""
    blockchain_data = run_command("curl -s http://127.0.0.1:26657/blockchain", verbose)
    
    if not blockchain_data:
        return []

    try:
        blockchain_json = json.loads(blockchain_data)
        block_metas = blockchain_json.get("block_metas", [])
        blocks = [
            {
                "height": int(block_meta["header"]["height"]),
                "proposer_pro_tx_hash": block_meta["header"]["proposer_pro_tx_hash"]
            }
            for block_meta in block_metas
        ]
        return blocks
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error processing blockchain data: {e}")
        return []

def main(report_url, verbose=False):

    # Check VPN
    ensure_vpn_connectivity(verbose)
    
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
    #previous_proposed_blocks = run_command(
    #    f"grpcurl -proto platform.proto -d '{{\"v0\": {{\"ids\": [\"{platform_protx_hash}\"], \"epoch\": {previous_epoch_number}}} }}' {platform_service_address} org.dash.platform.dapi.v0.Platform/getEvonodesProposedEpochBlocksByIds",
    #    verbose
    #)
    #if previous_proposed_blocks:
    #    try:
    #        previous_blocks_json = json.loads(previous_proposed_blocks)
    #        count_info = previous_blocks_json.get("v0", {}).get("evonodesProposedBlockCountsInfo", {}).get(
    #            "evonodesProposedBlockCounts", [])
    #        proposed_block_in_previous_epoch = count_info[0].get("count", 0) if count_info else 0
    #    except (json.JSONDecodeError, IndexError, KeyError):
    #        proposed_block_in_previous_epoch = 0
    
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
    latest_block_validator = latest_block_validator.upper()
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
        "curl -s http://127.0.0.1:26657/dump_consensus_state | jq '.round_state.validators.validators[].pro_tx_hash'",
        verbose)
    if not active_validators:
        print_verbose("Failed to retrieve active validators.", verbose)
        in_quorum = None
        validators_in_quorum = []
    elif len(active_validators.splitlines()) < 67:
        print_verbose("Insufficient number of active validators.", verbose)
        in_quorum = None
        validators_in_quorum = []
    else:
        active_validators_list = [validator.strip('"').upper() for validator in active_validators.splitlines()]
        validators_in_quorum = active_validators_list
        in_quorum = pro_tx_hash in active_validators_list
        print_verbose(f"Validator {pro_tx_hash} {'is' if in_quorum else 'is not'} in quorum.", verbose)

    # Get or initialize VALIDATOR_QUORUM_HASH
    previous_quorum_hash = get_env_variable("VALIDATOR_QUORUM_HASH")
    current_quorum_hash = compute_hash(validators_in_quorum)
    changed_quorum = False
    
    if previous_quorum_hash and previous_quorum_hash != current_quorum_hash:
        # Quorum hash has changed
        changed_quorum = True
        print_verbose("Validator quorum hash has changed.", verbose)
        
    # Save the current quorum hash to environment variables
    set_env_variable("VALIDATOR_QUORUM_HASH", current_quorum_hash)
    print_verbose("Validator quorum hash saved to environment variables.", verbose)

    # Set changing_quorum to True if the latest_block_validator is the last validator in the list,
    # or if latest_block_validator is not in the validators_in_quorum, indicating a possible quorum change.
    changing_quorum = False
    
    try:
        latest_block_validator_index = validators_in_quorum.index(latest_block_validator)
        
        # Check if the latest_block_validator is the last in the list of validators
        if latest_block_validator_index == len(validators_in_quorum) - 1:
            changing_quorum = True
    except ValueError:
        # Set changing_quorum to True if latest_block_validator is not found in the validators_in_quorum list
        changing_quorum = True

    if in_quorum:
        print_verbose(f"Validator {pro_tx_hash} is in quorum.", verbose)
        if latest_block_validator == pro_tx_hash:
            # Validator produced the block as expected
            print_verbose(f"Validator {pro_tx_hash} produced block at height {latest_block_height}.", verbose)
            set_env_variable("LAST_PRODUCED_BLOCK_HEIGHT", latest_block_height)
            set_env_variable("LAST_SHOULD_PRODUCE_BLOCK_HEIGHT", latest_block_height)
            last_produce_block_height = get_env_variable("LAST_PRODUCED_BLOCK_HEIGHT")
            last_should_produce_block_height = get_env_variable("LAST_SHOULD_PRODUCE_BLOCK_HEIGHT")
            produce_block_status = "OK"  # Set status to OK after setting block heights
            print_verbose("Produce block status set to OK after producing expected block.", verbose)
        elif not changed_quorum and not changing_quorum:
            # Determine if validator should have produced the block
            print_verbose("Checking if validator should have produced the block.", verbose)
            if latest_block_validator > pro_tx_hash:
                print_verbose(f"Validator {latest_block_validator} is greater than {pro_tx_hash}.", verbose)
                latest_block_validator_index = validators_in_quorum.index(latest_block_validator)
                pro_tx_hash_index = validators_in_quorum.index(pro_tx_hash)
                print_verbose(f"Validator {latest_block_validator} index: {latest_block_validator_index}, {pro_tx_hash} index: {pro_tx_hash_index}.", verbose)

                search_start = (latest_block_height - latest_block_validator_index) + pro_tx_hash_index
                search_end = latest_block_height - 1

                # Refresh the last should produce block height before checking
                last_should_produce_block_height = get_env_variable("LAST_SHOULD_PRODUCE_BLOCK_HEIGHT")

                # Display the variables being checked
                print_verbose(f"Checking if search is necessary with LAST_SHOULD_PRODUCE_BLOCK_HEIGHT: {last_should_produce_block_height}, "
                              f"search_start: {search_start}.", verbose)

                # Check if searching is necessary based on last should produce block height
                if last_should_produce_block_height and last_should_produce_block_height > search_start:
                    print_verbose(
                        f"LAST_SHOULD_PRODUCE_BLOCK_HEIGHT ({last_should_produce_block_height}) > search_start ({search_start}). "
                        "Using existing values without further search.", verbose
                    )
                    # Skip searching and use current environment variables
                    produce_block_status = "ERROR" if last_produce_block_height != last_should_produce_block_height else "OK"
                    print_verbose(f"Produce block status set to {produce_block_status} based on existing values.", verbose)
                else:
                    print_verbose(f"Searching blocks from {search_start} to {search_end} to find {pro_tx_hash}.", verbose)

                    # Binary search to find the block produced by the validator
                    found_block = False
                    left, right = search_start, search_end

                    while left <= right:
                        mid = (left + right) // 2
                        result_validator = run_command(
                            f"curl -s http://127.0.0.1:26657/block?height={mid} | jq -r '.block.header.proposer_pro_tx_hash'",
                            verbose
                        )
                        result_validator = result_validator.upper()
                        print_verbose(f"Block {mid} proposed by {result_validator}.", verbose)

                        # Update LAST_SHOULD_PRODUCE_BLOCK_HEIGHT at each step
                        set_env_variable("LAST_SHOULD_PRODUCE_BLOCK_HEIGHT", mid)
                        last_should_produce_block_height = mid

                        if result_validator == pro_tx_hash:
                            # Block found, update LAST_PRODUCED_BLOCK_HEIGHT
                            set_env_variable("LAST_PRODUCED_BLOCK_HEIGHT", mid)
                            last_produce_block_height = mid
                            found_block = True
                            produce_block_status = "OK"  # Set status to OK after finding block
                            print_verbose(f"Validator {pro_tx_hash} found producing block at height {mid}.", verbose)
                            print_verbose("Produce block status set to OK after finding block.", verbose)
                            break
                        elif result_validator < pro_tx_hash:
                            left = mid + 1
                            print_verbose(f"Validator {result_validator} is less than {pro_tx_hash}, searching right half.", verbose)
                        else:
                            right = mid - 1
                            print_verbose(f"Validator {result_validator} is greater than {pro_tx_hash}, searching left half.", verbose)

                    # If block was not found, set the status to ERROR
                    if not found_block:
                        produce_block_status = "ERROR"
                        print_verbose("Block not found, produce block status set to ERROR.", verbose)

            else:
                # Log when latest_block_validator is less than pro_tx_hash
                print_verbose(f"Validator {latest_block_validator} is less than {pro_tx_hash}.", verbose)
        else:
            print_verbose("Skipping block production check due to quorum change.", verbose)

    # Step 9.5: Fetch blockchain data and extract blocks information
    blocks = fetch_blockchain_data(verbose)

    # Step 10: Prepare the payload with available data
    payload = {
        "serverName": run_command("whoami", verbose),
        "uptime": run_command("awk '{up=$1; print int(up/86400)\"d \"int((up%86400)/3600)\"h \"int((up%3600)/60)\"m \"int(up%60)\"s\"}' /proc/uptime", verbose),
        "uptimeInSeconds": int(float(run_command("awk '{print $1}' /proc/uptime", verbose))),
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

    # Step 11: Send the report
    post_json_data(report_url, payload, verbose)

    # Step 12: Restart server if uptime is greater than 7 days and not in quorum
    # if in_quorum is False and po_se_penalty == 0 and float(run_command("awk '{print $1}' /proc/uptime", verbose)) > 7 * 86400:
    #    print("Restarting server...")
    #    run_command("sudo reboot", verbose)

if __name__ == "__main__":
    verbose_mode = '-v' in sys.argv
    if verbose_mode:
        sys.argv.remove('-v')

    if len(sys.argv) != 2:
        print("Usage: python3 masternode_monitor.py <report_url> [-v]")
        sys.exit(1)

    report_url = sys.argv[1]
    delay = random.randint(5, 60)
    time.sleep(delay)
    main(report_url, verbose_mode)
