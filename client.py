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
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((SERVER_HOST, SERVER_PORT))
            
            join = {
                'type': 'JOIN',
                'client_id': self.username
            }
            self.sock.send(json.dumps(join).encode('utf-8'))
            
            self.running = True
            
            t = threading.Thread(target=self.receive_messages)
            t.daemon = True
            t.start()
            
            print(f"\nConectado como '{self.username}'")
            print("Comandos: /history, /confirmations, /quit\n")
            
            return True
            
        except Exception as e:
            print(f"Erro ao conectar: {e}")
            return False
            
    def receive_messages(self):
        while self.running:
            try:
                data = self.sock.recv(BUFFER_SIZE)
                if not data:
                    break
                msg = json.loads(data.decode('utf-8'))
                self.process_received_message(msg)
            except:
                break
                
    def process_received_message(self, msg):
        tipo = msg.get('type')
        
        if tipo == 'HISTORY':
            self.history = msg['messages']
            print(f"Historico sincronizado ({len(self.history)} mensagens)\n")
            
        elif tipo == 'CHAT':
            self.history.append(msg)
            ts = datetime.fromtimestamp(msg['timestamp']).strftime('%H:%M:%S')
            print(f"[{ts}] {msg['sender']}: {msg['message']} (ID:{msg['msg_id']})")
            self.send_read_confirmation(msg['msg_id'])
            
        elif tipo == 'SYSTEM':
            self.history.append(msg)
            ts = datetime.fromtimestamp(msg['timestamp']).strftime('%H:%M:%S')
            print(f"[{ts}] [SISTEMA] {msg['message']}")
            
            if 'desligado' in msg['message'].lower():
                print("\nConexao sera encerrada.\n")
                self.running = False
            
        elif tipo == 'READ_CONFIRM':
            mid = msg['msg_id']
            if mid not in self.confirmations:
                self.confirmations[mid] = []
            self.confirmations[mid].append(msg['reader'])
            
    def send_message(self, text):
        msg = {'type': 'CHAT', 'message': text}
        self.sock.send(json.dumps(msg).encode('utf-8'))
            
    def send_read_confirmation(self, msg_id):
        try:
            confirm = {'type': 'READ_CONFIRM', 'msg_id': msg_id}
            self.sock.send(json.dumps(confirm).encode('utf-8'))
        except:
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
