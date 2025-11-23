import threading
import time
import queue
import rpyc
from rpyc.utils.server import ThreadedServer
from constCS import *

class MessageQueue:
    def __init__(self):
        self.queues = {}
        self.lock = threading.Lock()
        
    def create_queue(self, client_id):
        with self.lock:
            if client_id not in self.queues:
                self.queues[client_id] = queue.Queue()
                
    def remove_queue(self, client_id):
        with self.lock:
            if client_id in self.queues:
                del self.queues[client_id]
                
    def publish(self, msg, exclude=None):
        with self.lock:
            items = list(self.queues.items())
            
        for cid, q in items:
            if cid != exclude:
                try:
                    q.put(msg)
                except:
                    pass
                    
    def consume(self, client_id, timeout=0.1):
        target_q = None
        with self.lock:
            if client_id in self.queues:
                target_q = self.queues[client_id]
        
        if target_q:
            try:
                return target_q.get(timeout=timeout)
            except queue.Empty:
                return None
        return None

class ChatServer(rpyc.Service):
    clients = {}
    history = []
    msg_counter = 0
    lock = threading.Lock()
    msg_queue = MessageQueue()
    
    def on_connect(self, conn):
        pass

    def on_disconnect(self, conn):
        pass

    def exposed_join(self, client_id):
        with ChatServer.lock:
            if client_id in ChatServer.clients:
                return False
            ChatServer.clients[client_id] = time.time()
            ChatServer.msg_queue.create_queue(client_id)
        
        print(f"{client_id} entrou no chat")
        
        ChatServer.msg_queue.publish({
            'type': 'HISTORY',
            'messages': ChatServer.history
        }, exclude=None)
        
        with ChatServer.lock:
            for msg in ChatServer.history:
                if msg.get('type') == 'CHAT':
                    ChatServer.msg_queue.publish({
                        'type': 'READ_CONFIRM',
                        'reader': client_id,
                        'msg_id': msg['msg_id'],
                        'timestamp': time.time()
                    }, exclude=client_id)
        
        ChatServer.msg_queue.publish({
            'type': 'SYSTEM',
            'message': f'{client_id} entrou no chat',
            'timestamp': time.time(),
            'msg_id': ChatServer.get_next_msg_id()
        }, exclude=None)
        
        return True
        
    def exposed_leave(self, client_id):
        with ChatServer.lock:
            if client_id in ChatServer.clients:
                del ChatServer.clients[client_id]
            ChatServer.msg_queue.remove_queue(client_id)
        
        print(f"{client_id} saiu do chat")
        
        ChatServer.msg_queue.publish({
            'type': 'SYSTEM',
            'message': f'{client_id} saiu do chat',
            'timestamp': time.time(),
            'msg_id': ChatServer.get_next_msg_id()
        }, exclude=None)
        return True
        
    def exposed_send_message(self, client_id, text):
        exists = False
        with ChatServer.lock:
            exists = client_id in ChatServer.clients
        
        if not exists: return False
            
        chat_msg = {
            'type': 'CHAT',
            'sender': client_id,
            'message': text,
            'timestamp': time.time(),
            'msg_id': ChatServer.get_next_msg_id()
        }
        
        with ChatServer.lock:
            ChatServer.history.append(chat_msg)
        
        ChatServer.msg_queue.publish(chat_msg, exclude=None)
        return True
        
    def exposed_read_confirm(self, client_id, msg_id):
        ChatServer.msg_queue.publish({
            'type': 'READ_CONFIRM',
            'reader': client_id,
            'msg_id': msg_id,
            'timestamp': time.time()
        }, exclude=client_id)
        return True
        
    def exposed_get_messages(self, client_id):
        return ChatServer.msg_queue.consume(client_id, timeout=0.2)
    
    @staticmethod
    def get_next_msg_id():
        with ChatServer.lock:
            ChatServer.msg_counter += 1
            return ChatServer.msg_counter
            
    @staticmethod
    def shutdown():
        ChatServer.msg_queue.publish({
            'type': 'SYSTEM',
            'message': 'Servidor sendo desligado',
            'timestamp': time.time(),
            'msg_id': ChatServer.get_next_msg_id()
        }, exclude=None)
        print(f"Servidor encerrado. {len(ChatServer.history)} mensagens no histórico.\n")

if __name__ == "__main__":
    server = ThreadedServer(
        ChatServer, 
        port=SERVER_PORT,
        protocol_config={'allow_public_attrs': True}
    )
    
    print(f"Servidor RPC iniciado em {SERVER_HOST}:{SERVER_PORT}")
    print("Aguardando clientes... (Ctrl+C para encerrar)\n")
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nEncerrando servidor...")
        ChatServer.shutdown()
        server.close()