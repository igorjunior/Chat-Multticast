import threading
import time
import queue
import json
import random
import argparse
import sys
import rpyc
from rpyc.utils.server import ThreadedServer
from constCS import *

class ReplicaNode(rpyc.Service):
    def __init__(self, node_manager):
        self.node_manager = node_manager
    
    def exposed_get_initial_peers(self):
        """Bootstrap fornece lista inicial de peers"""
        if not self.node_manager.is_bootstrap:
            return {}
        peers_info = {}
        with self.node_manager.peers_lock:
            for node_id, peer_data in self.node_manager.peers.items():
                peers_info[str(node_id)] = {
                    'host': str(peer_data['host']),
                    'port': int(peer_data['port'])
                }
        return peers_info
    
    def exposed_receive_join(self, node_id, host, port, timestamp, msg_id):
        """Recebe JOIN"""
        if node_id == self.node_manager.node_id:
            return
        
        if msg_id in self.node_manager.processed_msg_ids:
            return
        
        self.node_manager.processed_msg_ids.add(msg_id)
        
        # Conecta ao novo peer
        try:
            conn = rpyc.connect(host, port)
            with self.node_manager.peers_lock:
                self.node_manager.peers[node_id] = {
                    'host': host,
                    'port': port,
                    'connection': conn,
                    'last_heartbeat': time.time(),
                    'status': 'ACTIVE',
                    'missed_heartbeats': 0
                }
            
            conn.root.exposed_join_ack(
                self.node_manager.node_id,
                self.node_manager.host,
                self.node_manager.port
            )
            
            print(f"Peer {node_id} conectado via JOIN")
            
            # Reidentifica líder (pode ter mudado)
            self.node_manager.identify_leader()
            
            # Propaga JOIN
            self.node_manager.propagate_join(node_id, host, port, timestamp, msg_id, exclude=node_id)
        except Exception as e:
            print(f"Erro ao conectar com novo peer {node_id}: {e}")
    
    def exposed_join_ack(self, peer_id, peer_host, peer_port):
        """Recebe ACK de peer que recebeu JOIN (direto ou propagado)"""
        # Ignora se for o próprio nó
        if peer_id == self.node_manager.node_id:
            return
        
        with self.node_manager.peers_lock:
            if peer_id not in self.node_manager.peers:
                # Descobre novo peer via propagação
                try:
                    conn = rpyc.connect(peer_host, peer_port)
                    self.node_manager.peers[peer_id] = {
                        'host': peer_host,
                        'port': peer_port,
                        'connection': conn,
                        'last_heartbeat': time.time(),
                        'status': 'ACTIVE',
                        'missed_heartbeats': 0
                    }
                    print(f"Descoberto peer {peer_id} via propagação")
                    # Reidentifica líder
                    self.node_manager.identify_leader()
                except Exception as e:
                    print(f"Erro ao conectar com peer descoberto {peer_id}: {e}")
    
    def exposed_heartbeat(self, node_id, timestamp):
        """Recebe heartbeat de peer"""
        if node_id in self.node_manager.peers:
            self.node_manager.peers[node_id]['last_heartbeat'] = timestamp
            self.node_manager.peers[node_id]['status'] = 'ACTIVE'
            self.node_manager.peers[node_id]['missed_heartbeats'] = 0
    
    def exposed_election(self, sender_id):
        """Recebe mensagem ELECTION (algoritmo Bully)"""
        # Se meu ID é maior, respondo OK e inicio minha eleição
        if str(self.node_manager.node_id) > str(sender_id):
            print(f"Recebi ELECTION de {sender_id}, sou maior. Iniciando minha eleição.")
            self.node_manager.start_election()
            return True  # OK
        return False  # Ignora
    
    def exposed_coordinator(self, new_leader_id):
        """Recebe anúncio de novo coordenador"""
        print(f"Novo líder anunciado: {new_leader_id}")
        self.node_manager.leader_id = new_leader_id
        self.node_manager.is_leader = (new_leader_id == self.node_manager.node_id)
        
        with self.node_manager.election_lock:
            self.node_manager.election_in_progress = False
    
    def exposed_peer_list_update(self, peers_dict):
        """Atualiza lista de peers (mudanças)"""
        peers_dict_local = {}
        try:
            # Converte peers_dict para dict local se for netref
            if not isinstance(peers_dict, dict):
                # Tenta converter manualmente iterando
                try:
                    temp_dict = {}
                    for key in peers_dict:
                        temp_dict[key] = peers_dict[key]
                    peers_dict = temp_dict
                except:
                    # Se falhar, retorna silenciosamente
                    return
            
            for node_id, peer_info in peers_dict.items():
                peers_dict_local[str(node_id)] = {
                    'host': str(peer_info['host']),
                    'port': int(peer_info['port'])
                }
        except Exception as e:
            # Falhas de conexão são esperadas quando peers estão caindo
            return
        
        with self.node_manager.peers_lock:
            # Atualiza lista de peers
            for node_id, peer_info in peers_dict_local.items():
                if node_id != self.node_manager.node_id:
                    if node_id not in self.node_manager.peers:
                        # Novo peer descoberto
                        try:
                            conn = rpyc.connect(peer_info['host'], peer_info['port'])
                            self.node_manager.peers[node_id] = {
                                'host': peer_info['host'],
                                'port': peer_info['port'],
                                'connection': conn,
                                'last_heartbeat': time.time(),
                                'status': 'ACTIVE',
                                'missed_heartbeats': 0
                            }
                            print(f"Peer {node_id} adicionado via peer_list_update")
                        except Exception as e:
                            print(f"Erro ao conectar com peer {node_id}: {e}")
                    else:
                        # Atualiza informações existentes
                        self.node_manager.peers[node_id]['host'] = peer_info['host']
                        self.node_manager.peers[node_id]['port'] = peer_info['port']
            
            # Remove peers que não estão mais na lista
            to_remove = [
                node_id for node_id in self.node_manager.peers.keys()
                if node_id != self.node_manager.node_id and node_id not in peers_dict_local
            ]
            for node_id in to_remove:
                self.node_manager.remove_peer_connection(node_id)
            
            # Reidentifica líder após mudanças
            self.node_manager.identify_leader()
    
    def exposed_join_user(self, username):
        """Usuário entra no chat neste nó"""
        with self.node_manager.clients_lock:
            if username in self.node_manager.local_clients:
                return False
            self.node_manager.local_clients[username] = time.time()
            self.node_manager.message_queues.create_queue(username)
        
        print(f"{username} entrou no chat (no {self.node_manager.node_id})")
        
        # Envia histórico completo
        self.node_manager.message_queues.publish({
            'type': 'HISTORY',
            'messages': self.node_manager.history
        }, exclude=None)
        
        # Cria mensagem SYSTEM de join
        system_msg = {
            'type': 'SYSTEM',
            'message': f'{username} entrou no chat',
            'timestamp': time.time(),
            'msg_id': self.node_manager.get_next_msg_id()
        }
        
        # Líder sequencia e replica, backup encaminha
        if self.node_manager.is_leader:
            self.node_manager.sequence_and_replicate(system_msg)
        else:
            self.node_manager.forward_to_leader(system_msg)
        
        return True
    
    def exposed_leave_user(self, username):
        """Usuário sai do chat"""
        with self.node_manager.clients_lock:
            if username in self.node_manager.local_clients:
                del self.node_manager.local_clients[username]
            self.node_manager.message_queues.remove_queue(username)
        
        print(f"{username} saiu do chat (no {self.node_manager.node_id})")
        
        # Cria mensagem SYSTEM de leave
        system_msg = {
            'type': 'SYSTEM',
            'message': f'{username} saiu do chat',
            'timestamp': time.time(),
            'msg_id': self.node_manager.get_next_msg_id()
        }
        
        # Líder sequencia e replica, backup encaminha
        if self.node_manager.is_leader:
            self.node_manager.sequence_and_replicate(system_msg)
        else:
            self.node_manager.forward_to_leader(system_msg)
        
        return True
    
    def exposed_send_message(self, username, text):
        """Processa mensagem de usuário local"""
        with self.node_manager.clients_lock:
            if username not in self.node_manager.local_clients:
                return False
        
        chat_msg = {
            'type': 'CHAT',
            'sender': username,
            'message': text,
            'timestamp': time.time(),
            'msg_id': self.node_manager.get_next_msg_id()
        }
        
        # Líder sequencia e replica, backup encaminha
        if self.node_manager.is_leader:
            self.node_manager.sequence_and_replicate(chat_msg)
        else:
            self.node_manager.forward_to_leader(chat_msg)
        
        return True
    
    def exposed_get_messages(self, username):
        """Cliente UI obtém mensagens pendentes"""
        return self.node_manager.message_queues.consume(username, timeout=0.2)
    
    def exposed_read_confirm(self, username, msg_id):
        """Confirmação de leitura"""
        confirm_msg = {
            'type': 'READ_CONFIRM',
            'reader': username,
            'msg_id': self.node_manager.get_next_msg_id(),  # Gera ID único para confirmação
            'ref_msg_id': msg_id,  # Referência à mensagem original
            'timestamp': time.time()
        }
        
        # Líder sequencia e replica, backup encaminha
        if self.node_manager.is_leader:
            self.node_manager.sequence_and_replicate(confirm_msg)
        else:
            self.node_manager.forward_to_leader(confirm_msg)
        
        return True
    
    def exposed_get_history(self):
        """Retorna histórico completo (para sincronização)"""
        return self.node_manager.history
    
    def exposed_receive_replicated_chat(self, sender, message, timestamp, msg_id, seq_number, leader_id):
        """Backup recebe mensagem CHAT replicada do líder"""
        if msg_id in self.node_manager.processed_msg_ids:
            return
        
        self.node_manager.processed_msg_ids.add(msg_id)
        
        msg_dict = {
            'type': 'CHAT',
            'sender': sender,
            'message': message,
            'timestamp': timestamp,
            'msg_id': msg_id,
            'seq_number': seq_number,
            'leader_id': leader_id
        }
        
        # Verifica sequência
        if seq_number == self.node_manager.expected_seq + 1:
            self.node_manager.expected_seq = seq_number
            # Entrega imediatamente
            with self.node_manager.history_lock:
                self.node_manager.history.append(msg_dict)
            self.node_manager.notify_local_clients(msg_dict)
        else:
            # Gap detectado - solicita recuperação
            print(f"Gap detectado: esperado {self.node_manager.expected_seq+1}, recebido {seq_number}")
            # Por simplicidade, entrega mesmo com gap (em produção, solicitaria recuperação)
            self.node_manager.expected_seq = seq_number
            with self.node_manager.history_lock:
                self.node_manager.history.append(msg_dict)
            self.node_manager.notify_local_clients(msg_dict)
    
    def exposed_receive_replicated_system(self, message, timestamp, msg_id, seq_number, leader_id):
        """Backup recebe mensagem SYSTEM replicada do líder"""
        if msg_id in self.node_manager.processed_msg_ids:
            return
        
        self.node_manager.processed_msg_ids.add(msg_id)
        
        msg_dict = {
            'type': 'SYSTEM',
            'message': message,
            'timestamp': timestamp,
            'msg_id': msg_id,
            'seq_number': seq_number,
            'leader_id': leader_id
        }
        
        # Verifica sequência
        if seq_number == self.node_manager.expected_seq + 1:
            self.node_manager.expected_seq = seq_number
            with self.node_manager.history_lock:
                self.node_manager.history.append(msg_dict)
            self.node_manager.notify_local_clients(msg_dict)
        else:
            self.node_manager.expected_seq = seq_number
            with self.node_manager.history_lock:
                self.node_manager.history.append(msg_dict)
            self.node_manager.notify_local_clients(msg_dict)
    
    def exposed_receive_replicated_read_confirm(self, reader, ref_msg_id, timestamp, msg_id, seq_number, leader_id):
        """Backup recebe confirmação de leitura replicada do líder"""
        if msg_id in self.node_manager.processed_msg_ids:
            return
        
        self.node_manager.processed_msg_ids.add(msg_id)
        
        msg_dict = {
            'type': 'READ_CONFIRM',
            'reader': reader,
            'ref_msg_id': ref_msg_id,
            'timestamp': timestamp,
            'msg_id': msg_id,
            'seq_number': seq_number,
            'leader_id': leader_id
        }
        
        # Verifica sequência
        if seq_number == self.node_manager.expected_seq + 1:
            self.node_manager.expected_seq = seq_number
            with self.node_manager.history_lock:
                self.node_manager.history.append(msg_dict)
            self.node_manager.notify_local_clients(msg_dict)
        else:
            self.node_manager.expected_seq = seq_number
            with self.node_manager.history_lock:
                self.node_manager.history.append(msg_dict)
            self.node_manager.notify_local_clients(msg_dict)
    
    def exposed_forward_chat_message(self, sender, message, timestamp, msg_id):
        """Líder recebe mensagem encaminhada de backup"""
        chat_msg = {
            'type': 'CHAT',
            'sender': sender,
            'message': message,
            'timestamp': timestamp,
            'msg_id': msg_id
        }
        self.node_manager.sequence_and_replicate(chat_msg)
    
    def exposed_forward_system_message(self, message, timestamp, msg_id):
        """Líder recebe mensagem SYSTEM encaminhada de backup"""
        system_msg = {
            'type': 'SYSTEM',
            'message': message,
            'timestamp': timestamp,
            'msg_id': msg_id
        }
        self.node_manager.sequence_and_replicate(system_msg)
    
    def exposed_forward_read_confirm(self, reader, ref_msg_id, timestamp, msg_id):
        """Líder recebe confirmação de leitura encaminhada de backup"""
        confirm_msg = {
            'type': 'READ_CONFIRM',
            'reader': reader,
            'ref_msg_id': ref_msg_id,
            'timestamp': timestamp,
            'msg_id': msg_id
        }
        self.node_manager.sequence_and_replicate(confirm_msg)


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


class NodeManager:
    def __init__(self, node_id, host, port, is_bootstrap=False):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.is_bootstrap = is_bootstrap
        
        # Estruturas de dados
        self.peers = {}  # {node_id: {host, port, connection, last_heartbeat, status, missed_heartbeats}}
        self.peers_lock = threading.Lock()
        self.history = []  # Réplica local de mensagens
        self.history_lock = threading.Lock()
        self.local_clients = {}  # {username: timestamp}
        self.clients_lock = threading.Lock()
        self.message_queues = MessageQueue()
        self.processed_msg_ids = set()  # Cache de IDs processados
        self.msg_counter = 0
        self.msg_counter_lock = threading.Lock()
        
        # Threads e controle
        self.running = True
        self.server_thread = None
        self.heartbeat_sender_thread = None
        self.heartbeat_monitor_thread = None
        self.auto_save_thread = None
        self.leader_monitor_thread = None
        
        # Liderança e Eleição
        self.leader_id = None
        self.is_leader = False
        self.seq_counter = 0
        self.seq_lock = threading.Lock()
        self.expected_seq = 0
        self.election_in_progress = False
        self.election_lock = threading.Lock()
        self.election_responses = set()
        
        # Carrega histórico persistido
        self.load_history_from_disk()
    
    def get_next_msg_id(self):
        with self.msg_counter_lock:
            self.msg_counter += 1
            return f"{self.node_id}_{self.msg_counter}"
    
    def identify_leader(self):
        """Identifica líder atual (maior node_id ativo)"""
        with self.peers_lock:
            all_nodes = list(self.peers.keys()) + [self.node_id]
            # Bootstrap não participa da liderança
            all_nodes = [n for n in all_nodes if n != 'bootstrap']
        
        if not all_nodes:
            self.leader_id = self.node_id
            self.is_leader = True
        else:
            # Líder é o nó com maior ID
            leader = max(all_nodes, key=lambda x: str(x))
            self.leader_id = leader
            self.is_leader = (leader == self.node_id)
        
        print(f"Líder identificado: {self.leader_id} (eu sou líder: {self.is_leader})")
    
    
    def start_server(self):
        """Inicia servidor RPC em thread separada"""
        service = ReplicaNode(self)
        self.server = ThreadedServer(
            service,
            hostname=self.host,
            port=self.port,
            protocol_config={'allow_public_attrs': True}
        )
        
        def run_server():
            try:
                self.server.start()
            except Exception as e:
                if self.running:
                    print(f"Erro no servidor RPC: {e}")
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        print(f"No {self.node_id} servidor RPC iniciado em {self.host}:{self.port}")
    
    def stop_server(self):
        """Para o servidor RPC"""
        self.running = False
        if hasattr(self, 'server') and self.server:
            try:
                self.server.close()
            except:
                pass
    
    def connect_to_bootstrap(self):
        """Obtém lista inicial de peers do bootstrap"""
        if self.is_bootstrap:
            return {}
        
        try:
            bootstrap_conn = rpyc.connect(BOOTSTRAP_HOST, BOOTSTRAP_PORT)
            initial_peers = bootstrap_conn.root.exposed_get_initial_peers()
            peers_dict = {}
            if initial_peers:
                for node_id, peer_info in initial_peers.items():
                    peers_dict[str(node_id)] = {
                        'host': str(peer_info['host']),
                        'port': int(peer_info['port'])
                    }
            bootstrap_conn.close()
            return peers_dict
        except Exception as e:
            print(f"Erro ao conectar ao bootstrap: {e}")
            return None
    
    def join_network(self, initial_peers):
        """Envia JOIN"""
        timestamp = time.time()
        msg_id = self.get_next_msg_id()
        
        # Conecta ao bootstrap
        bootstrap_id = 'bootstrap'
        bootstrap_connected = False
        try:
            conn = rpyc.connect(BOOTSTRAP_HOST, BOOTSTRAP_PORT)
            conn.root.exposed_receive_join(
                node_id=self.node_id,
                host=self.host,
                port=self.port,
                timestamp=timestamp,
                msg_id=msg_id
            )
            with self.peers_lock:
                self.peers[bootstrap_id] = {
                    'host': BOOTSTRAP_HOST,
                    'port': BOOTSTRAP_PORT,
                    'connection': conn,
                    'last_heartbeat': time.time(),
                    'status': 'ACTIVE',
                    'missed_heartbeats': 0
                }
            print(f"Conectado ao bootstrap")
            bootstrap_connected = True
        except Exception as e:
            print(f"Erro ao conectar com bootstrap: {e}")
            return False
        
        if initial_peers:
            for peer_id, peer_info in initial_peers.items():
                if peer_id == self.node_id or peer_id == bootstrap_id:
                    continue
                try:
                    conn = rpyc.connect(peer_info['host'], peer_info['port'])
                    conn.root.exposed_receive_join(
                        node_id=self.node_id,
                        host=self.host,
                        port=self.port,
                        timestamp=timestamp,
                        msg_id=msg_id
                    )
                    with self.peers_lock:
                        self.peers[peer_id] = {
                            'host': peer_info['host'],
                            'port': peer_info['port'],
                            'connection': conn,
                            'last_heartbeat': time.time(),
                            'status': 'ACTIVE',
                            'missed_heartbeats': 0
                        }
                    print(f"Conectado a peer inicial {peer_id}")
                except Exception as e:
                    print(f"Erro ao conectar com peer inicial {peer_id}: {e}")
        
        return bootstrap_connected
    
    def propagate_join(self, node_id, host, port, timestamp, msg_id, exclude=None):
        """Propaga JOIN"""
        if msg_id in self.processed_msg_ids:
            return
        
        self.processed_msg_ids.add(msg_id)
        
        # Seleciona subset de peers para propagar
        available = []
        with self.peers_lock:
            for pid, pinfo in self.peers.items():
                if pid != exclude and pid != node_id and pinfo.get('status') == 'ACTIVE':
                    available.append((pid, pinfo))
        
        if not available:
            return
        
        fanout = min(PROPAGATION_FANOUT, len(available))
        targets = random.sample(available, fanout)
        
        for peer_id, peer_info in targets:
            try:
                peer_info['connection'].root.exposed_receive_join(
                    node_id=node_id,
                    host=host,
                    port=port,
                    timestamp=timestamp,
                    msg_id=msg_id
                )
            except Exception as e:
                print(f"Erro ao propagar JOIN para {peer_id}: {e}")
    
    def notify_local_clients(self, msg):
        """Notifica clientes locais sobre nova mensagem"""
        self.message_queues.publish(msg, exclude=None)
    
    def sequence_and_replicate(self, msg):
        """Líder sequencia mensagem e replica para backups"""
        with self.seq_lock:
            self.seq_counter += 1
            msg['seq_number'] = self.seq_counter
            msg['leader_id'] = self.node_id
        
        # Entrega localmente
        with self.history_lock:
            self.history.append(msg)
        self.notify_local_clients(msg)
        
        # Replica para backups
        self.replicate_to_backups(msg)
    
    def replicate_to_backups(self, msg):
        """Replica mensagem sequenciada para todos backups"""
        with self.peers_lock:
            peers_copy = dict(self.peers)
        
        for peer_id, peer_info in peers_copy.items():
            if peer_id == 'bootstrap':
                continue
            try:
                conn = peer_info['connection']
                if msg['type'] == 'CHAT':
                    conn.root.exposed_receive_replicated_chat(
                        sender=msg['sender'],
                        message=msg['message'],
                        timestamp=msg['timestamp'],
                        msg_id=msg['msg_id'],
                        seq_number=msg['seq_number'],
                        leader_id=msg['leader_id']
                    )
                elif msg['type'] == 'SYSTEM':
                    conn.root.exposed_receive_replicated_system(
                        message=msg['message'],
                        timestamp=msg['timestamp'],
                        msg_id=msg['msg_id'],
                        seq_number=msg['seq_number'],
                        leader_id=msg['leader_id']
                    )
                elif msg['type'] == 'READ_CONFIRM':
                    conn.root.exposed_receive_replicated_read_confirm(
                        reader=msg['reader'],
                        ref_msg_id=msg['ref_msg_id'],
                        timestamp=msg['timestamp'],
                        msg_id=msg['msg_id'],
                        seq_number=msg['seq_number'],
                        leader_id=msg['leader_id']
                    )
            except Exception as e:
                error_str = str(e)
                is_fatal_error = any(keyword in error_str for keyword in [
                    '10054',
                    'Connection refused',
                    'Connection reset',
                    'Broken pipe',
                    'EOFError',
                    'stream has been closed'
                ])
                if is_fatal_error:
                    self.remove_dead_peer(peer_id)
                else:
                    print(f"Erro ao replicar para {peer_id}: {e}")
    
    def forward_to_leader(self, msg):
        """Backup encaminha mensagem para líder"""
        if not self.leader_id or self.leader_id == self.node_id:
            # Sem líder ou sou o líder - não deveria acontecer
            return
        
        if self.leader_id not in self.peers:
            print(f"Líder {self.leader_id} não está na lista de peers. Iniciando eleição.")
            self.start_election()
            return
        
        try:
            conn = self.peers[self.leader_id]['connection']
            if msg['type'] == 'CHAT':
                conn.root.exposed_forward_chat_message(
                    sender=msg['sender'],
                    message=msg['message'],
                    timestamp=msg['timestamp'],
                    msg_id=msg['msg_id']
                )
            elif msg['type'] == 'SYSTEM':
                conn.root.exposed_forward_system_message(
                    message=msg['message'],
                    timestamp=msg['timestamp'],
                    msg_id=msg['msg_id']
                )
            elif msg['type'] == 'READ_CONFIRM':
                conn.root.exposed_forward_read_confirm(
                    reader=msg['reader'],
                    ref_msg_id=msg['ref_msg_id'],
                    timestamp=msg['timestamp'],
                    msg_id=msg['msg_id']
                )
        except Exception as e:
            error_str = str(e)
            is_fatal_error = any(keyword in error_str for keyword in [
                '10054',
                'Connection refused',
                'Connection reset',
                'Broken pipe',
                'EOFError',
                'stream has been closed'
            ])
            if is_fatal_error:
                print(f"Líder {self.leader_id} não responde. Iniciando eleição.")
                self.start_election()
            else:
                print(f"Erro ao encaminhar para líder: {e}")
    
    def start_heartbeat_sender(self):
        """Thread que envia heartbeat a cada 30-40s"""
        def send_heartbeat():
            while self.running:
                try:
                    interval = HEARTBEAT_INTERVAL + random.randint(0, HEARTBEAT_JITTER)
                    time.sleep(interval)
                    
                    if not self.running:
                        break
                    
                    timestamp = time.time()
                    peers_copy = {}
                    with self.peers_lock:
                        peers_copy = dict(self.peers)
                    
                    for peer_id, peer_info in peers_copy.items():
                        try:
                            conn = peer_info['connection']
                            conn.root.exposed_heartbeat(self.node_id, timestamp)
                        except Exception as e:
                            error_str = str(e)
                            is_fatal_error = any(keyword in error_str for keyword in [
                                '10054',
                                'Connection refused',
                                'Connection reset',
                                'Broken pipe',
                                'EOFError',
                                'stream has been closed'
                            ])
                            
                            if is_fatal_error:
                                self.remove_dead_peer(peer_id)
                            else:
                                with self.peers_lock:
                                    if peer_id in self.peers:
                                        self.peers[peer_id]['missed_heartbeats'] += 1
                except Exception as e:
                    if self.running:
                        print(f"Erro no heartbeat sender: {e}")
        
        self.heartbeat_sender_thread = threading.Thread(target=send_heartbeat, daemon=True)
        self.heartbeat_sender_thread.start()
    
    def start_heartbeat_monitor(self):
        """Thread que monitora timeouts"""
        def monitor_heartbeat():
            while self.running:
                try:
                    time.sleep(HEARTBEAT_CHECK_INTERVAL)
                    
                    if not self.running:
                        break
                    
                    current_time = time.time()
                    dead_peers = []
                    
                    with self.peers_lock:
                        for peer_id, peer_info in list(self.peers.items()):
                            time_since_heartbeat = current_time - peer_info.get('last_heartbeat', 0)
                            
                            if time_since_heartbeat > HEARTBEAT_TIMEOUT:
                                dead_peers.append(peer_id)
                    
                    for peer_id in dead_peers:
                        self.remove_dead_peer(peer_id)
                        
                except Exception as e:
                    if self.running:
                        print(f"Erro no heartbeat monitor: {e}")
        
        self.heartbeat_monitor_thread = threading.Thread(target=monitor_heartbeat, daemon=True)
        self.heartbeat_monitor_thread.start()
    
    def remove_dead_peer(self, node_id):
        """Remove peer que sofreu timeout"""
        with self.peers_lock:
            if node_id in self.peers:
                self.remove_peer_connection(node_id)
        
        print(f"Peer {node_id} removido (timeout)")
        
        # Se o peer removido era o líder, inicia eleição
        if node_id == self.leader_id:
            print(f"Líder {node_id} foi removido. Iniciando eleição.")
            self.leader_id = None
            self.is_leader = False
            self.start_election()
        
        # Cria mensagem SYSTEM
        system_msg = {
            'type': 'SYSTEM',
            'message': f'{node_id} saiu (timeout)',
            'timestamp': time.time(),
            'msg_id': self.get_next_msg_id()
        }
        
        # Líder sequencia e replica, backup encaminha
        if self.is_leader:
            self.sequence_and_replicate(system_msg)
        elif self.leader_id:
            self.forward_to_leader(system_msg)
        
        # Broadcast lista atualizada
        self.broadcast_peer_list()
    
    def remove_peer_connection(self, node_id):
        """Remove conexão com peer"""
        if node_id in self.peers:
            try:
                self.peers[node_id]['connection'].close()
            except:
                pass
            del self.peers[node_id]
    
    def start_election(self):
        """Inicia eleição Bully"""
        with self.election_lock:
            if self.election_in_progress:
                return
            self.election_in_progress = True
            self.election_responses.clear()
        
        print(f"Iniciando eleição (sou {self.node_id})")
        
        # Envia ELECTION para nós com ID maior
        with self.peers_lock:
            higher_peers = [
                (pid, pinfo) for pid, pinfo in self.peers.items()
                if str(pid) > str(self.node_id) and pid != 'bootstrap'
            ]
        
        for peer_id, peer_info in higher_peers:
            try:
                conn = peer_info['connection']
                response = conn.root.exposed_election(self.node_id)
                if response:
                    self.election_responses.add(peer_id)
            except:
                pass
        
        # Aguarda respostas
        time.sleep(2)
        
        with self.election_lock:
            if not self.election_responses:
                # Nenhum nó maior respondeu - sou o líder
                self.become_leader()
            # Senão, aguarda COORDINATOR
    
    def become_leader(self):
        """Torna-se o novo líder"""
        print(f"Tornando-me líder (sou {self.node_id})")
        self.leader_id = self.node_id
        self.is_leader = True
        
        # Anuncia para todos
        with self.peers_lock:
            peers_copy = dict(self.peers)
        
        for peer_id, peer_info in peers_copy.items():
            if peer_id == 'bootstrap':
                continue
            try:
                conn = peer_info['connection']
                conn.root.exposed_coordinator(self.node_id)
            except:
                pass
        
        with self.election_lock:
            self.election_in_progress = False
    
    
    def broadcast_peer_list(self):
        """Broadcast"""
        peers_dict = {}
        with self.peers_lock:
            for node_id, peer_info in self.peers.items():
                peers_dict[str(node_id)] = {
                    'host': str(peer_info['host']),
                    'port': int(peer_info['port'])
                }
            # Inclui próprio nó
            peers_dict[str(self.node_id)] = {
                'host': str(self.host),
                'port': int(self.port)
            }
        
        # Envia para todos peers ativos
        peers_copy = {}
        with self.peers_lock:
            peers_copy = dict(self.peers)
        
        for peer_id, peer_info in peers_copy.items():
            try:
                conn = peer_info['connection']
                conn.root.exposed_peer_list_update(peers_dict)
            except Exception as e:
                error_str = str(e)
                if not any(keyword in error_str for keyword in ['10054', 'EOFError', 'Connection reset']):
                    print(f"Erro ao broadcast peer list para {peer_id}: {e}")
    
    def sync_history(self):
        """Sincroniza histórico com peers (late-joiner)"""
        peers_copy = {}
        with self.peers_lock:
            peers_copy = dict(self.peers)
        
        for peer_id, peer_info in peers_copy.items():
            try:
                conn = peer_info['connection']
                remote_history = conn.root.exposed_get_history()
                
                remote_history_local = []
                try:
                    for msg in remote_history:
                        remote_history_local.append({
                            'type': str(msg.get('type', '')),
                            'msg_id': str(msg.get('msg_id', '')),
                            'timestamp': float(msg.get('timestamp', 0)),
                            'sender': str(msg.get('sender', '')),
                            'message': str(msg.get('message', '')),
                            'reader': str(msg.get('reader', '')),
                            'ref_msg_id': str(msg.get('ref_msg_id', '')),
                            'seq_number': int(msg.get('seq_number', 0)),
                            'leader_id': str(msg.get('leader_id', '')),
                        })
                except Exception as e:
                    print(f"Erro ao processar remote_history: {e}")
                    continue
                
                remote_ids = {msg.get('msg_id') for msg in remote_history_local}
                local_ids = {msg.get('msg_id') for msg in self.history}
                
                # Atualiza expected_seq com máximo visto
                max_seq = 0
                for msg in remote_history_local:
                    if 'seq_number' in msg:
                        max_seq = max(max_seq, msg['seq_number'])
                
                self.expected_seq = max(self.expected_seq, max_seq)
                
                for msg in remote_history_local:
                    if msg.get('msg_id') not in local_ids:
                        self.history.append(msg)
                        self.processed_msg_ids.add(msg.get('msg_id'))
                
                # Ordena por seq_number para manter ordem sequencial
                self.history.sort(key=lambda m: m.get('seq_number', 0))
                
                print(f"Histórico sincronizado com {peer_id}: {len(self.history)} mensagens")
                break
            except Exception as e:
                print(f"Erro ao sincronizar histórico com {peer_id}: {e}")
    
    def save_history_to_disk(self):
        """Salva histórico em disco"""
        try:
            filename = f'history_{self.node_id}.json'
            with open(filename, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"Erro ao salvar histórico: {e}")
    
    def load_history_from_disk(self):
        """Carrega histórico do disco"""
        try:
            filename = f'history_{self.node_id}.json'
            with open(filename, 'r') as f:
                self.history = json.load(f)
                self.processed_msg_ids = {msg.get('msg_id') for msg in self.history if msg.get('msg_id')}
                
                max_counter = 0
                for msg in self.history:
                    msg_id = msg.get('msg_id', '')
                    if msg_id and '_' in msg_id:
                        try:
                            parts = msg_id.split('_')
                            if len(parts) >= 2 and parts[0] == str(self.node_id):
                                counter = int(parts[1])
                                max_counter = max(max_counter, counter)
                        except (ValueError, IndexError):
                            continue
                
                with self.msg_counter_lock:
                    self.msg_counter = max_counter
                
                # Inicializa expected_seq e seq_counter com maior seq_number visto
                max_seq = 0
                for msg in self.history:
                    if 'seq_number' in msg:
                        max_seq = max(max_seq, msg['seq_number'])
                
                self.expected_seq = max_seq
                with self.seq_lock:
                    self.seq_counter = max_seq
                
                print(f"Histórico carregado: {len(self.history)} mensagens (contador em {self.msg_counter}, seq em {max_seq})")
        except FileNotFoundError:
            self.history = []
            self.processed_msg_ids = set()
        except Exception as e:
            print(f"Erro ao carregar histórico: {e}")
            self.history = []
            self.processed_msg_ids = set()
    
    def start_auto_save(self):
        """Thread que salva histórico periodicamente"""
        def auto_save():
            while self.running:
                time.sleep(HISTORY_SAVE_INTERVAL)
                if self.running:
                    self.save_history_to_disk()
        
        self.auto_save_thread = threading.Thread(target=auto_save, daemon=True)
        self.auto_save_thread.start()
    
    def start_leader_monitor(self):
        """Thread que monitora líder (só em backups)"""
        def monitor_leader():
            while self.running:
                try:
                    time.sleep(10)
                    
                    if self.is_leader:
                        continue  # Líder não monitora a si mesmo
                    
                    # Verifica se líder ainda está ativo
                    if self.leader_id and self.leader_id in self.peers:
                        last_hb = self.peers[self.leader_id].get('last_heartbeat', 0)
                        if time.time() - last_hb > 30:
                            print(f"Líder {self.leader_id} não responde. Iniciando eleição.")
                            self.start_election()
                    elif self.leader_id and self.leader_id not in self.peers:
                        # Líder não está mais na lista de peers
                        print(f"Líder {self.leader_id} não está mais na rede. Iniciando eleição.")
                        self.start_election()
                
                except Exception as e:
                    if self.running:
                        print(f"Erro no monitor de líder: {e}")
        
        self.leader_monitor_thread = threading.Thread(target=monitor_leader, daemon=True)
        self.leader_monitor_thread.start()
    
    
    def run(self):
        """Inicia nó"""
        # Inicia servidor RPC
        self.start_server()
        time.sleep(1)  # Aguarda servidor iniciar
        
        if not self.is_bootstrap:
            initial_peers = self.connect_to_bootstrap()
            if initial_peers is None:
                print(f"ERRO: Não foi possível conectar ao bootstrap em {BOOTSTRAP_HOST}:{BOOTSTRAP_PORT}")
                print("Encerrando nó...")
                self.running = False
                return
            
            join_success = self.join_network(initial_peers)
            if not join_success:
                print(f"ERRO: Não foi possível fazer JOIN na rede")
                print("Encerrando nó...")
                self.running = False
                return
            
            time.sleep(2)
            self.sync_history()
        
        # Identifica líder inicial
        self.identify_leader()
        
        # Inicia threads de manutenção
        self.start_heartbeat_sender()
        self.start_heartbeat_monitor()
        self.start_auto_save()
        self.start_leader_monitor()
        
        print(f"Nó {self.node_id} rodando. Pressione Ctrl+C para encerrar.")
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nEncerrando nó...")
            self.running = False
            self.save_history_to_disk()
            
            # Fecha conexões
            with self.peers_lock:
                for peer_id in list(self.peers.keys()):
                    self.remove_peer_connection(peer_id)
            
            print(f"Nó {self.node_id} encerrado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Nó P2P RPC')
    parser.add_argument('--node-id', default=None, help='ID do no')
    parser.add_argument('--port', type=int, default=None, help='Porta do no')
    parser.add_argument('--host', default='localhost', help='Host do no')
    parser.add_argument('--bootstrap', action='store_true', help='Este no é o bootstrap')
    parser.add_argument('--bootstrap-host', default=BOOTSTRAP_HOST, help='Host do bootstrap')
    parser.add_argument('--bootstrap-port', type=int, default=BOOTSTRAP_PORT, help='Porta do bootstrap')
    
    args = parser.parse_args()
    
    # Solicita parâmetros interativamente se não fornecidos
    node_id = args.node_id
    if not node_id:
        node_id = input("ID do no: ").strip()
        if not node_id:
            print("ID do no invalido!")
            sys.exit(1)
    
    port = args.port
    if port is None:
        try:
            port = int(input("Porta: ").strip())
        except (ValueError, EOFError):
            print("Porta invalida!")
            sys.exit(1)
    
    node = NodeManager(
        node_id=node_id,
        host=args.host,
        port=port,
        is_bootstrap=args.bootstrap
    )
    
    node.run()

