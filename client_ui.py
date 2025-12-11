import threading
import time
import sys
import argparse
from datetime import datetime
import rpyc
from constCS import *

class ChatClientUI:
    def __init__(self, username, node_host, node_port):
        self.username = username
        self.node_host = node_host
        self.node_port = node_port
        self.rpc = None
        self.running = False
        self.history = []
        self.confirmations = {}
        self.rpc_lock = threading.Lock()
        
    def connect(self):
        """Estabelece conexão RPC com nó"""
        try:
            self.rpc = rpyc.connect(self.node_host, self.node_port)
            
            with self.rpc_lock:
                if not self.rpc.root.exposed_join_user(self.username):
                    print("Erro: usuario ja conectado ou nome indisponivel")
                    return False
            
            self.running = True
            
            t = threading.Thread(target=self.receive_messages)
            t.daemon = True
            t.start()
            
            print(f"\nConectado como '{self.username}' ao nó {self.node_host}:{self.node_port}")
            print("Comandos: /history, /confirmations, /quit\n")
            
            return True
            
        except Exception as e:
            print(f"Erro ao conectar: {e}")
            return False
            
    def receive_messages(self):
        """Thread que obtém mensagens do nó via polling"""
        while self.running:
            try:
                msg = None
                with self.rpc_lock:
                    msg = self.rpc.root.exposed_get_messages(self.username)
                
                if msg:
                    self.process_received_message(msg)
                
            except EOFError:
                print("\nConexao com nó perdida.")
                self.running = False
                sys.exit(0)
            except Exception as e:
                if self.running:
                    time.sleep(1)
                
    def process_received_message(self, msg):
        """Processa mensagem recebida"""
        tipo = msg.get('type')
        
        if tipo == 'HISTORY':
            self.history = msg['messages']
            print(f"Historico sincronizado ({len(self.history)} mensagens)\n")
            
        elif tipo == 'CHAT':
            msg_id = msg.get('msg_id')
            if not any(m.get('msg_id') == msg_id for m in self.history):
                self.history.append(msg)
            
            ts = datetime.fromtimestamp(msg['timestamp']).strftime('%H:%M:%S')
            print(f"[{ts}] {msg['sender']}: {msg['message']} (ID:{msg['msg_id']})")
            
            if msg['sender'] != self.username:
                self.send_read_confirmation(msg['msg_id'])
            
        elif tipo == 'SYSTEM':
            msg_id = msg.get('msg_id')
            if not any(m.get('msg_id') == msg_id for m in self.history):
                self.history.append(msg)
            ts = datetime.fromtimestamp(msg['timestamp']).strftime('%H:%M:%S')
            print(f"[{ts}] [SISTEMA] {msg['message']}")
            
            if 'desligado' in msg['message'].lower() or 'saiu' in msg['message'].lower():
                # Não encerra, apenas informa
                pass
            
        elif tipo == 'READ_CONFIRM':
            mid = msg['msg_id']
            reader = msg.get('reader')
            if mid and reader:
                if mid not in self.confirmations:
                    self.confirmations[mid] = []
                if reader not in self.confirmations[mid]:
                    self.confirmations[mid].append(reader)
            
    def send_message(self, text):
        """Envia mensagem para nó local via RPC"""
        try:
            with self.rpc_lock:
                self.rpc.root.exposed_send_message(self.username, text)
        except Exception as e:
            print(f"Erro ao enviar: {e}")
            self.running = False
            
    def send_read_confirmation(self, msg_id):
        """Envia confirmação de leitura"""
        try:
            with self.rpc_lock:
                self.rpc.root.exposed_read_confirm(self.username, msg_id)
        except:
            pass
            
    def show_history(self):
        """Exibe histórico obtido do nó"""
        print("\n--- HISTORICO ---")
        if not self.history:
            print("Nenhuma mensagem.")
        else:
            for msg in self.history:
                ts = datetime.fromtimestamp(msg['timestamp']).strftime('%H:%M:%S')
                mid = msg.get('msg_id', '?')
                
                if msg['type'] == 'CHAT':
                    readers = self.confirmations.get(mid, [])
                    lido = f" [lido: {','.join(readers)}]" if readers else ""
                    print(f"[{ts}] ID:{mid} | {msg['sender']}: {msg['message']}{lido}")
                elif msg['type'] == 'SYSTEM':
                    print(f"[{ts}] ID:{mid} | [SISTEMA] {msg['message']}")
        print()
        
    def show_confirmations(self):
        """Exibe confirmações de leitura"""
        print("\n--- CONFIRMACOES DE LEITURA ---")
        if not self.confirmations:
            print("Nenhuma confirmacao.")
        else:
            for mid, readers in sorted(self.confirmations.items()):
                print(f"Msg ID:{mid} - Lida por: {', '.join(readers)}")
        print()
        
    def run(self):
        """Loop principal de interface (input de comandos)"""
        if not self.connect():
            return
            
        try:
            while self.running:
                try:
                    msg = input()
                except EOFError:
                    break
                
                if not self.running: break 
                
                if not msg: continue
                    
                if msg == '/quit':
                    break
                elif msg == '/history':
                    self.show_history()
                elif msg == '/confirmations':
                    self.show_confirmations()
                else:
                    self.send_message(msg)
                    
        except KeyboardInterrupt:
            print("\nSaindo...")
        finally:
            self.running = False
            if self.rpc:
                try:
                    with self.rpc_lock:
                        self.rpc.root.exposed_leave_user(self.username)
                    self.rpc.close()
                except:
                    pass
            print("Encerrado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Cliente UI P2P')
    parser.add_argument('--username', default=None, help='Nome de usuário')
    parser.add_argument('--node-host', default='localhost', help='Host do nó')
    parser.add_argument('--node-port', type=int, default=None, help='Porta do nó')
    
    args = parser.parse_args()
    
    # Solicita parâmetros interativamente se não fornecidos
    username = args.username
    if not username:
        username = input("Nome de usuario: ").strip()
        if not username:
            print("Nome de usuario invalido!")
            sys.exit(1)
    
    node_port = args.node_port
    if node_port is None:
        try:
            node_port = int(input("Porta do no: ").strip())
        except (ValueError, EOFError):
            print("Porta invalida!")
            sys.exit(1)
    
    client = ChatClientUI(username, args.node_host, node_port)
    client.run()

