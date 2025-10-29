import socket
import threading
import json
import time
from constCS import *

class ChatServer:
    def __init__(self):
        self.clients = {}
        self.history = []
        self.msg_counter = 0
        self.lock = threading.Lock()
        
    def start(self):
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_socket.bind((SERVER_HOST, SERVER_PORT))
        self.tcp_socket.listen(5)
        
        print(f"Servidor iniciado em {SERVER_HOST}:{SERVER_PORT}")
        print("Aguardando clientes... (Ctrl+C para encerrar)\n")
        
        try:
            while True:
                client_socket, address = self.tcp_socket.accept()
                thread = threading.Thread(target=self.handle_client, args=(client_socket, address))
                thread.daemon = True
                thread.start()
        except KeyboardInterrupt:
            print("\nEncerrando servidor...")
            self.shutdown()
            
    def shutdown(self):
        msg = {
            'type': 'SYSTEM',
            'message': 'Servidor sendo desligado',
            'timestamp': time.time(),
            'msg_id': self.get_next_msg_id()
        }
        self.broadcast_message(msg, exclude=None)
        
        with self.lock:
            for client_id, (sock, _) in list(self.clients.items()):
                sock.close()
            self.clients.clear()
        
        self.tcp_socket.close()
        print(f"Servidor encerrado. {len(self.history)} mensagens no histórico.\n")
                
    def handle_client(self, sock, addr):
        client_id = None
        try:
            data = sock.recv(BUFFER_SIZE).decode('utf-8')
            msg = json.loads(data)
            
            if msg['type'] == 'JOIN':
                client_id = msg['client_id']
                
                with self.lock:
                    self.clients[client_id] = (sock, addr)
                
                print(f"{client_id} entrou no chat")
                
                hist_msg = {
                    'type': 'HISTORY',
                    'messages': self.history
                }
                sock.send(json.dumps(hist_msg).encode('utf-8'))
                
                self.broadcast_message({
                    'type': 'SYSTEM',
                    'message': f'{client_id} entrou no chat',
                    'timestamp': time.time(),
                    'msg_id': self.get_next_msg_id()
                }, exclude=None)
                
                while True:
                    data = sock.recv(BUFFER_SIZE)
                    if not data:
                        break
                    msg = json.loads(data.decode('utf-8'))
                    self.process_message(msg, client_id)
                    
        except Exception as e:
            if client_id:
                print(f"Erro com cliente {client_id}: {e}")
        finally:
            if client_id:
                with self.lock:
                    if client_id in self.clients:
                        del self.clients[client_id]
                        
                print(f"{client_id} saiu do chat")
                
                self.broadcast_message({
                    'type': 'SYSTEM',
                    'message': f'{client_id} saiu do chat',
                    'timestamp': time.time(),
                    'msg_id': self.get_next_msg_id()
                }, exclude=None)
                
            sock.close()
            
    def process_message(self, msg, sender):
        if msg.get('type') == 'CHAT':
            chat_msg = {
                'type': 'CHAT',
                'sender': sender,
                'message': msg['message'],
                'timestamp': time.time(),
                'msg_id': self.get_next_msg_id()
            }
            
            with self.lock:
                self.history.append(chat_msg)
            
            self.broadcast_message(chat_msg, exclude=None)
            
        elif msg.get('type') == 'READ_CONFIRM':
            confirm = {
                'type': 'READ_CONFIRM',
                'reader': sender,
                'msg_id': msg['msg_id'],
                'timestamp': time.time()
            }
            self.broadcast_message(confirm, exclude=sender)
            
    def broadcast_message(self, msg, exclude=None):
        data = json.dumps(msg).encode('utf-8')
        
        with self.lock:
            dead = []
            for cid, (sock, _) in self.clients.items():
                if cid == exclude:
                    continue
                try:
                    sock.send(data)
                except:
                    dead.append(cid)
            
            for cid in dead:
                del self.clients[cid]
                
    def get_next_msg_id(self):
        with self.lock:
            self.msg_counter += 1
            return self.msg_counter

if __name__ == "__main__":
    server = ChatServer()
    server.start()
