# Configurações P2P
BOOTSTRAP_HOST = 'localhost'
BOOTSTRAP_PORT = 5679
NODE_BASE_PORT = 5679
DEFAULT_NODE_HOST = 'localhost'
RPC_TIMEOUT = 0.2

# Configurações de Heartbeat e Detecção de Falhas
HEARTBEAT_INTERVAL = 30  # Envia heartbeat a cada 30 segundos
HEARTBEAT_JITTER = 10  # Variação aleatória (30-40s)
HEARTBEAT_TIMEOUT = 60  # Remove peer após 60 segundos sem resposta
HEARTBEAT_CHECK_INTERVAL = 10  # Verifica timeouts a cada 10s
MAX_MISSED_HEARTBEATS = 2  # Marca como suspeito após 2 heartbeats

# Sistema de Difusão (Propagação)
PROPAGATION_FANOUT = 3  # Cada nó propaga para 3 vizinhos
MSG_ID_CACHE_SIZE = 10000  # Cache de IDs já processados
MESSAGE_TIMESTAMP_TOLERANCE = 3600  # 1 hora de tolerância para validação

# Persistência
HISTORY_SAVE_INTERVAL = 300  # Salva histórico a cada 5 minutos
