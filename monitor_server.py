import os
from flask import Flask, request, render_template_string, jsonify
from datetime import datetime
import logging
import json

# Logger configuration - logging debug information for detailed logs
logging.basicConfig(
    level=logging.DEBUG,  # Ustawiono na DEBUG, aby uzyskać szczegółowe logi
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Loguj na konsolę
    ]
)

# Ścieżki do plików
HEARTBEAT_FILE = 'app_data/heartbeat_data.json'

app = Flask(__name__)

heartbeat_data = {}

# Upewnij się, że katalog 'app_data' istnieje
if not os.path.exists('app_data'):
    logging.debug("Creating directory 'app_data'.")
    os.makedirs('app_data')
else:
    logging.debug("Directory 'app_data' already exists.")

def ensure_directory_exists(path):
    """Ensure the directory for the given path exists."""
    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        try:
            logging.debug(f"Creating directory {directory}.")
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            logging.critical(f"Could not create directory {directory}: {e}")
            return False
    return True

def save_to_file(data, filename):
    """Save data to a file and return JSON with the result status."""
    if not ensure_directory_exists(filename):
        error_msg = f"Directory does not exist and could not be created for {filename}."
        logging.critical(error_msg)
        return {"status": "error", "message": error_msg}

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

def load_from_file(filename):
    """Load data from a file, returning an empty dictionary if the file does not exist."""
    if not os.path.exists(filename):
        logging.critical(f"File {filename} does not exist. Returning empty data.")
        return {}  # Zwróć pusty słownik, jeśli plik nie istnieje

    try:
        with open(filename, 'r') as f:
            logging.debug(f"Loading data from file {filename}.")
            return json.load(f)
    except json.JSONDecodeError as e:
        logging.critical(f"JSON decode error for file {filename}: {e}")
        return {}  # Jeśli JSON jest nieprawidłowy, zwróć pusty słownik
    except Exception as e:
        logging.critical(f"Error loading data from {filename}: {e}")
        return {}  # Jeśli inny błąd, zwróć pusty słownik

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    global heartbeat_data
    data = request.get_json()
    logging.debug(f"Received heartbeat data: {data}")

    server_name = data.get('serverName')
    if server_name:
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

@app.route('/old')
def display_validators():
    try:
        global heartbeat_data
        logging.debug("Loading heartbeat data from file.")
        heartbeat_data = load_from_file(HEARTBEAT_FILE)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
            
            <!-- Display Heartbeat Data -->
            <h2>Heartbeat Data</h2>
            <table>
                <tr>
                    <th>Server Name</th>
                    <th>Uptime</th>
                    <th>Uptime in Seconds</th>
                    <th>ProTx Hash</th>
                    <th>Core Block Height</th>
                    <th>Platform Block Height</th>
                    <th>P2P Port State</th>
                    <th>HTTP Port State</th>
                    <th>PoSe Penalty</th>
                    <th>PoSe Revived Height</th>
                    <th>PoSe Ban Height</th>
                    <th>Last Paid Height</th>
                    <th>Last Paid Time</th>
                    <th>Payment Queue Position</th>
                    <th>Next Payment Time</th>
                    <th>Proposed Block in Current Epoch</th>
                    <th>Epoch Number</th>
                    <th>Epoch First Block Height</th>
                    <th>Epoch Start Time</th>
                    <th>Epoch End Time</th>
                    <th>In Quorum</th>
                </tr>
                {% for server, data in heartbeat_data.items() %}
                <tr>
                    <td>{{ server }}</td>
                    <td>{{ data['uptime'] }}</td>
                    <td>{{ data['uptimeInSeconds'] }}</td>
                    <td>{{ data['proTxHash'] }}</td>
                    <td>{{ data['coreBlockHeight'] }}</td>
                    <td>{{ data['platformBlockHeight'] }}</td>
                    <td>{{ data['p2pPortState'] }}</td>
                    <td>{{ data['httpPortState'] }}</td>
                    <td>{{ data['poSePenalty'] }}</td>
                    <td>{{ data['poSeRevivedHeight'] }}</td>
                    <td>{{ data['poSeBanHeight'] }}</td>
                    <td>{{ data['lastPaidHeight'] }}</td>
                    <td>{{ data['lastPaidTime'] }}</td>
                    <td>{{ data['paymentQueuePosition'] }}</td>
                    <td>{{ data['nextPaymentTime'] }}</td>
                    <td>{{ data['proposedBlockInCurrentEpoch'] }}</td>
                    <td>{{ data['epochNumber'] }}</td>
                    <td>{{ data['epochFirstBlockHeight'] }}</td>
                    <td>{{ data['epochStartTime'] }}</td>
                    <td>{{ data['epochEndTime'] }}</td>
                    <td>{{ data['inQuorum'] }}</td>
                </tr>
                {% endfor %}
            </table>
        </body>
        </html>
        """
        
        return render_template_string(html_template, current_time=current_time, heartbeat_data=heartbeat_data)
    except Exception as e:
        logging.debug(f"Exception occurred in display_validators: {e}")
        return "An error occurred while processing your request.", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
