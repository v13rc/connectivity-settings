# monitor_server_routes.py

from flask import Blueprint

monitor_routes_bp = Blueprint('monitor_routes', __name__)

@monitor_routes_bp.route('/ovh')
def ovh():
    return "Hello World"
