import socket
import threading
import json
import time
import sys
from datetime import datetime
from constCS import *

class ChatClient:
    def __init__(self, username):
        self.username = username
        self.sock = None
        self.running = False
        self.history = []
        self.confirmations = {}
        
    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('', MULTICAST_PORT))
            
            mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton('0.0.0.0')
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            
            self.running = True
            
            t = threading.Thread(target=self.receive_messages)
            t.daemon = True
            t.start()
            
            join = {
                'type': 'JOIN',
                'client_id': self.username
            }
            self.sock.sendto(json.dumps(join).encode('utf-8'), (MULTICAST_GROUP, MULTICAST_PORT))
            
            print(f"\nConectado como '{self.username}'")
            print("Comandos: /history, /confirmations, /quit\n")
            
            return True
            
        except Exception as e:
            print(f"Erro ao conectar: {e}")
            return False
            
    def receive_messages(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
                if not data:
                    break
                msg = json.loads(data.decode('utf-8'))
                self.process_received_message(msg)
            except Exception as e:
                if self.running:
                    continue
                break
                
    def process_received_message(self, msg):
        tipo = msg.get('type')
        
        if tipo == 'HISTORY':
            self.history = msg['messages']
            print(f"Historico sincronizado ({len(self.history)} mensagens)\n")
            
        elif tipo == 'CHAT':
            if msg.get('sender') == self.username and 'msg_id' not in msg:
                return
            
            msg_id = msg.get('msg_id')
            if msg_id and not any(m.get('msg_id') == msg_id for m in self.history):
                self.history.append(msg)
                ts = datetime.fromtimestamp(msg['timestamp']).strftime('%H:%M:%S')
                print(f"[{ts}] {msg['sender']}: {msg['message']} (ID:{msg['msg_id']})")
                self.send_read_confirmation(msg['msg_id'])
            
        elif tipo == 'SYSTEM':
            msg_id = msg.get('msg_id')
            if msg_id and not any(m.get('msg_id') == msg_id for m in self.history):
                self.history.append(msg)
                ts = datetime.fromtimestamp(msg['timestamp']).strftime('%H:%M:%S')
                print(f"[{ts}] [SISTEMA] {msg['message']}")
                
                if 'desligado' in msg['message'].lower():
                    print("\nConexao sera encerrada.\n")
                    self.running = False
            
        elif tipo == 'READ_CONFIRM':
            mid = msg.get('msg_id')
            reader = msg.get('reader')
            if mid and reader:
                if mid not in self.confirmations:
                    self.confirmations[mid] = []
                if reader not in self.confirmations[mid]:
                    self.confirmations[mid].append(reader)
            
    def send_message(self, text):
        msg = {
            'type': 'CHAT',
            'sender': self.username,
            'message': text
        }
        try:
            self.sock.sendto(json.dumps(msg).encode('utf-8'), (MULTICAST_GROUP, MULTICAST_PORT))
        except Exception as e:
            print(f"Erro ao enviar mensagem: {e}")
            
    def send_read_confirmation(self, msg_id):
        try:
            confirm = {
                'type': 'READ_CONFIRM',
                'reader': self.username,
                'msg_id': msg_id
            }
            self.sock.sendto(json.dumps(confirm).encode('utf-8'), (MULTICAST_GROUP, MULTICAST_PORT))
        except Exception as e:
            pass
            
    def show_history(self):
        print("\n--- HISTORICO ---")
        if not self.history:
            print("Nenhuma mensagem.")
        else:
            for msg in self.history:
                ts = datetime.fromtimestamp(msg['timestamp']).strftime('%H:%M:%S')
                mid = msg['msg_id']
                
                if msg['type'] == 'CHAT':
                    readers = self.confirmations.get(mid, [])
                    lido = f" [lido: {','.join(readers)}]" if readers else ""
                    print(f"[{ts}] ID:{mid} | {msg['sender']}: {msg['message']}{lido}")
                elif msg['type'] == 'SYSTEM':
                    print(f"[{ts}] ID:{mid} | [SISTEMA] {msg['message']}")
        print()
        
    def show_confirmations(self):
        print("\n--- CONFIRMACOES DE LEITURA ---")
        if not self.confirmations:
            print("Nenhuma confirmacao.")
        else:
            for mid, readers in sorted(self.confirmations.items()):
                print(f"Msg ID:{mid} - Lida por: {', '.join(readers)}")
        print()
        
    def run(self):
        if not self.connect():
            return
            
        try:
            while self.running:
                msg = input()
                
                if not msg:
                    continue
                    
                if msg == '/quit':
                    print("Saindo...")
                    break
                elif msg == '/history':
                    self.show_history()
                elif msg == '/confirmations':
                    self.show_confirmations()
                elif msg.startswith('/'):
                    print("Comando desconhecido")
                else:
                    self.send_message(msg)
                    
        except KeyboardInterrupt:
            print("\nSaindo...")
        finally:
            self.running = False
            if self.sock:
                self.sock.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        nome = sys.argv[1]
    else:
        nome = input("Nome de usuario: ").strip()
        
    if not nome:
        print("Nome invalido!")
        sys.exit(1)
        
    client = ChatClient(nome)
    client.run()
