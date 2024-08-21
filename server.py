from http.server import SimpleHTTPRequestHandler, HTTPServer
from threading import Thread
import requests
import os

def get_public_ip():
    try:
        response = requests.get('https://api.ipify.org?format=text')
        return response.text
    except requests.RequestException:
        return "Unable to get public IP"

def get_username():
    return os.getlogin()

class HelloWorldHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        # Uzyskanie publicznego IP i nazwy użytkownika
        public_ip = get_public_ip()
        username = get_username()

        # Przygotowanie odpowiedzi
        response = (
            b"Hello, World!\n"
            b"Public IP: " + public_ip.encode() + b"\n"
            b"Username: " + username.encode() + b"\n"
        )

        # Wysłanie odpowiedzi HTTP
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(response)

def run_server(port):
    with HTTPServer(("", port), HelloWorldHandler) as httpd:
        print(f"Server running on port {port}")
        httpd.serve_forever()

if __name__ == "__main__":
    ports = [443, 9999, 26656]
    threads = []

    for port in ports:
        thread = Thread(target=run_server, args=(port,))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()
