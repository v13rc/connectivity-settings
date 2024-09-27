# monitor_server_routes.py

from flask import Blueprint, render_template_string
import requests
import logging

# OVH API URL
OVH_API_URL = "https://ca.api.ovh.com/v1/dedicated/server/datacenter/availabilities?planCode=24ska01"

# Create blueprint
monitor_routes_bp = Blueprint('monitor_routes', __name__)

# Function to check server availability
def check_server_availability():
    try:
        response = requests.get(OVH_API_URL, headers={"accept": "application/json"})
        response.raise_for_status()  # Raise exception if HTTP status is not OK
        data = response.json()

        # Check server availability in datacenters
        available = any(dc["availability"] != "unavailable" for dc in data[0]["datacenters"])
        status_message = "Server KS-A is available" if available else "Server KS-A is not available"
        
        # Generate hidden codes for UpTimeRobot based on availability
        hidden_code = "ALERT_OVH_AVAILABLE" if available else "ALERT_OVH_UNAVAILABLE"
        
        logging.info(f"OVH Server Availability: {status_message}")
        return status_message, hidden_code
    except Exception as e:
        logging.error(f"Error checking server availability from OVH API: {e}")
        return "Error checking server availability from OVH API.", "ALERT_OVH_ERROR"

# OVH route
@monitor_routes_bp.route('/ovh')
def ovh():
    status, hidden_code = check_server_availability()
    # Render status with hidden code for UpTimeRobot
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>OVH Server Availability</title>
    </head>
    <body>
        <h1>OVH Server Status</h1>
        <p>{{ status }}</p>
        <span style="display:none;">{{ hidden_code }}</span>
    </body>
    </html>
    """
    return render_template_string(html_template, status=status, hidden_code=hidden_code)
