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
        self.sock = None
        
    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', MULTICAST_PORT))
        
        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton('0.0.0.0')
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        
        print(f"Servidor multicast iniciado em {MULTICAST_GROUP}:{MULTICAST_PORT}")
        print("Aguardando mensagens... (Ctrl+C para encerrar)\n")
        
        try:
            while True:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                try:
                    msg = json.loads(data.decode('utf-8'))
                    self.process_message(msg, addr)
                except json.JSONDecodeError:
                    continue
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
            self.clients.clear()
        
        if self.sock:
            self.sock.close()
        print(f"Servidor encerrado. {len(self.history)} mensagens no histórico.\n")
                
    def process_message(self, msg, addr):
        msg_type = msg.get('type')
        
        if msg_type == 'JOIN':
            client_id = msg.get('client_id')
            if not client_id:
                return
                
            with self.lock:
                if client_id in self.clients:
                    return
                self.clients[client_id] = addr
            
            print(f"{client_id} entrou no chat")
            
            hist_msg = {
                'type': 'HISTORY',
                'messages': self.history
            }
            self.broadcast_message(hist_msg, exclude=None)
            
            self.broadcast_message({
                'type': 'SYSTEM',
                'message': f'{client_id} entrou no chat',
                'timestamp': time.time(),
                'msg_id': self.get_next_msg_id()
            }, exclude=None)
            
        elif msg_type == 'CHAT':
            if 'msg_id' in msg:
                return
            
            sender = msg.get('sender')
            if not sender or sender not in self.clients:
                return
                
            chat_msg = {
                'type': 'CHAT',
                'sender': sender,
                'message': msg.get('message', ''),
                'timestamp': time.time(),
                'msg_id': self.get_next_msg_id()
            }
            
            with self.lock:
                self.history.append(chat_msg)
            
            self.broadcast_message(chat_msg, exclude=None)
            
        elif msg_type == 'READ_CONFIRM':
            if 'timestamp' in msg:
                return
                
            reader = msg.get('reader')
            if not reader or reader not in self.clients:
                return
                
            confirm = {
                'type': 'READ_CONFIRM',
                'reader': reader,
                'msg_id': msg.get('msg_id'),
                'timestamp': time.time()
            }
            self.broadcast_message(confirm, exclude=reader)
            
    def broadcast_message(self, msg, exclude=None):
        data = json.dumps(msg).encode('utf-8')
        try:
            self.sock.sendto(data, (MULTICAST_GROUP, MULTICAST_PORT))
        except Exception as e:
            print(f"Erro ao enviar mensagem multicast: {e}")
                
    def get_next_msg_id(self):
        with self.lock:
            self.msg_counter += 1
            return self.msg_counter

if __name__ == "__main__":
    server = ChatServer()
    server.start()
