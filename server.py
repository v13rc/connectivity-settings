import socket
import threading
import sys

def handle_client(conn, addr):
    print(f'Connected by {addr}')
    with conn:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            print(f'Received from {addr}: {data.decode()}')
            conn.sendall(data)

def start_server(host='0.0.0.0', ports=[443, 9999, 26656]):
    for port in ports:
        threading.Thread(target=listen_on_port, args=(host, port)).start()

def listen_on_port(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, port))
        s.listen()
        print(f'Server is listening on {host}:{port}')
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr)).start()

def test_connection(host, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.sendall(b'Hello, Server')
            data = s.recv(1024)
            print(f'Received from {host}:{port}: {data.decode()}')
    except Exception as e:
        print(f'Failed to connect to {host}:{port}. Error: {e}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 app.py <mode> [host] [port1] [port2] [port3] ...")
        print("Modes: server, client")
        sys.exit(1)
    
    mode = sys.argv[1].lower()

    if mode == 'server':
        ports = list(map(int, sys.argv[2:])) if len(sys.argv) > 2 else [443, 9999, 26656]
        start_server(ports=ports)
    elif mode == 'client':
        if len(sys.argv) < 4:
            print("Usage for client: python3 app.py client <host> <port1> [port2] [port3] ...")
            sys.exit(1)
        host = sys.argv[2]
        ports = map(int, sys.argv[3:])
        for port in ports:
            print(f'Testing connection on port {port}...')
            test_connection(host, port)
    else:
        print("Unknown mode. Use 'server' or 'client'.")
        sys.exit(1)
