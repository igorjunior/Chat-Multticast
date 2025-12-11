# Chat Distribuído P2P

Sistema de chat peer-to-peer com comunicação RPC, difusão de mensagens e histórico replicado.

**Duas implementações disponíveis:**
- **Parte 3 (`node.py`)**: Ordenação total com Relógios de Lamport
- **Parte 4 (`node_election.py`)**: Primary-Backup com Eleição de Líder (Bully Algorithm)

## Funcionalidades

O sistema implementa um chat distribuído onde múltiplos nós servidores (peers) se conectam formando uma rede P2P. Cada nó mantém uma réplica completa do histórico e propaga mensagens para outros peers. Clientes (usuários) se conectam aos nós para enviar e receber mensagens.

### Recursos Comuns (ambas versões):
- Rede P2P com comunicação RPC (rpyc)
- Bootstrap leve para descoberta inicial de peers
- Discovery distribuído via JOIN propagado
- Heartbeat para detecção de falhas (timeout 60s)
- Histórico replicado em todos os nós
- Persistência de mensagens em disco
- Confirmações de leitura
- Prevenção de duplicatas com cache de IDs

### Parte 3 - Ordenação Total (Lamport):
- **Ordenação total** com Relógios de Lamport
- Buffer de holdback para garantir ordem global
- Difusão eficiente com propagação controlada
- Todos os nós calculam e mantêm relógio lógico
- Thread de entrega verifica estabilidade a cada 100ms

### Parte 4 - Primary-Backup (Bully):
- **Eleição de líder** com algoritmo Bully
- Líder sequencia todas as mensagens
- Backups replicam mensagens do líder
- Entrega imediata (sem buffer de holdback)
- Menos overhead, latência reduzida
- Eleição automática quando líder falha (2-5s)

## Arquitetura

**Bootstrap Node:** Fornece lista inicial de peers quando novos nós entram na rede. É um servidor P2P.

**Peer Nodes:** São os servidores do sistema P2P. Cada nó/peer é um servidor RPC que mantém conexões com outros peers e propaga mensagens. Peers não são os clientes/usuários do chat, são os nós servidores da rede distribuída.

**Client UI:** Interface leve que conecta a um peer/nó local para enviar/receber mensagens. Representa um usuário do chat.

### Estruturas de Dados por Versão:

**Parte 3 (Lamport) - Cada nó armazena:**
- Lista de peers (host, porta, conexão RPC)
- Histórico completo de mensagens (réplica local)
- Cache de IDs processados (previne duplicatas)
- Status de heartbeat dos peers
- **Relógio lógico de Lamport**
- **Buffer de holdback para ordenação total**

**Parte 4 (Bully) - Cada nó armazena:**
- Lista de peers (host, porta, conexão RPC)
- Histórico completo de mensagens (réplica local)
- Cache de IDs processados (previne duplicatas)
- Status de heartbeat dos peers
- **ID do líder atual**
- **Contador de sequência (se for líder)**
- **Sequência esperada (se for backup)**

## Arquivos

- `node.py`: **Parte 3** - nó P2P com ordenação total Lamport
- `node_election.py`: **Parte 4** - nó P2P com Primary-Backup e eleição Bully
- `client_ui.py`: cliente de chat (compatível com ambas versões)
- `constCS.py`: configurações (portas, timeouts, fanout)
- `start_bootstrap.bat`: script para iniciar nó bootstrap

## Protocolo

Comunicação via RPC (rpyc). 

### Métodos Comuns (ambas versões):

**Gerenciamento de rede:**
- `get_initial_peers()`: obtém lista inicial do bootstrap
- `receive_join()`: recebe JOIN de novo peer e propaga
- `heartbeat()`: recebe heartbeat de peer
- `peer_list_update()`: sincroniza lista de peers

**Interface com cliente:**
- `join_user()`: usuário entra no chat
- `send_message()`: envia mensagem
- `get_messages()`: consome mensagens da fila
- `read_confirm()`: confirma leitura
- `leave_user()`: sai do chat

### Métodos Específicos:

**Parte 3 (Lamport):**
- `receive_chat_message()`: recebe mensagem CHAT e propaga
- `receive_system_message()`: recebe mensagem SYSTEM
- `receive_read_confirm()`: recebe confirmação de leitura

**Parte 4 (Bully):**
- `receive_replicated_chat()`: backup recebe CHAT do líder
- `receive_replicated_system()`: backup recebe SYSTEM do líder
- `receive_replicated_read_confirm()`: backup recebe READ_CONFIRM do líder
- `forward_chat_message()`: líder recebe CHAT encaminhado de backup
- `forward_system_message()`: líder recebe SYSTEM encaminhado
- `forward_read_confirm()`: líder recebe READ_CONFIRM encaminhado
- `election()`: recebe mensagem ELECTION (algoritmo Bully)
- `coordinator()`: recebe anúncio de novo líder

Tipos de mensagem:
- `CHAT`: mensagem de conversa
- `SYSTEM`: notificações do sistema
- `READ_CONFIRM`: confirmação de leitura
- `JOIN`: entrada de novo peer na rede

## Utilização

**Escolha qual versão usar:**
- **Parte 3 (Lamport)**: use `node.py` para ordenação total garantida
- **Parte 4 (Bully)**: use `node_election.py` para menor latência com eleição de líder

### Parte 3 - Ordenação Total (Lamport)

**Iniciar nó bootstrap:**
```bash
python node.py --node-id bootstrap --port 5679 --bootstrap
```

**Iniciar nós peers:**
```bash
python node.py --node-id node2 --port 5680
python node.py --node-id node3 --port 5681
```

Ou execute sem argumentos e forneça quando solicitado:
```bash
python node.py
```

### Parte 4 - Primary-Backup (Bully)

**Iniciar nó bootstrap:**
```bash
python node_election.py --node-id bootstrap --port 5679 --bootstrap
```

**Iniciar nós peers:**
```bash
python node_election.py --node-id node2 --port 5680
python node_election.py --node-id node3 --port 5681
```

Ou execute sem argumentos e forneça quando solicitado:
```bash
python node_election.py
```

**Nota:** O nó com maior `node_id` será eleito líder automaticamente.

### Conectar clientes

```bash
python client_ui.py --username Alice --node-port 5679
python client_ui.py --username Bob --node-port 5680
```

Ou execute sem argumentos:
```bash
python client_ui.py
```

Comandos disponíveis no cliente:
- Digite texto para enviar mensagem
- `/history` - ver histórico
- `/confirmations` - ver confirmações de leitura  
- `/quit` - sair

## Como funciona

### Inicialização e Discovery

1. Nó bootstrap inicia e aguarda conexões
2. Novos peers se conectam ao bootstrap e obtêm lista inicial de peers
3. Cada peer envia JOIN para peers iniciais
4. JOIN é propagado pela rede (difusão)
5. Peers respondem com ACK, descobrindo-se mutuamente
6. Resultado: rede P2P totalmente conectada

### Propagação de Mensagens

#### Parte 3 (Lamport) - Difusão Controlada:

1. Usuário envia mensagem via client_ui
2. Nó local:
   - Incrementa relógio de Lamport
   - Gera ID único (`node_id_counter`)
   - Adiciona `lamport_ts` e `origin_node` à mensagem
   - Coloca mensagem no buffer de holdback
3. Nó propaga para subset de peers (fanout configurável)
4. Cada peer que recebe:
   - Verifica se já processou (cache de IDs)
   - Atualiza relógio de Lamport: `max(local, received) + 1`
   - Adiciona ao buffer de holdback ordenado
   - Propaga para seus vizinhos
5. Thread de entrega (a cada 100ms):
   - Verifica mensagens estáveis no buffer
   - Entrega na ordem `(lamport_ts, origin_node)`
   - Move para histórico e notifica clientes
6. Mensagem alcança todos os nós (~N*log(N) chamadas RPC)

#### Parte 4 (Bully) - Replicação Primary-Backup:

1. Usuário envia mensagem via client_ui
2. **Se nó é LÍDER:**
   - Incrementa contador de sequência
   - Gera ID único
   - Adiciona `seq_number` e `leader_id` à mensagem
   - Entrega localmente (history + notify)
   - Replica para todos os backups
3. **Se nó é BACKUP:**
   - Encaminha mensagem para o líder
   - Aguarda replicação do líder
4. **Backups recebem replicação:**
   - Verificam sequência esperada
   - Entregam imediatamente (sem buffer)
   - Notificam clientes locais
5. Mensagem alcança todos os nós (N chamadas RPC diretas)

### Detecção de Falhas

Sistema de heartbeat detecta nós inativos:

1. Cada nó envia heartbeat a cada 30-40s (com jitter)
2. Monitor verifica timeouts a cada 10s
3. Se peer não responde por 60s:
   - Peer é removido da lista local
   - Conexão RPC é fechada
   - Mensagem SYSTEM notifica saída
4. Se peer volta, reconecta ao bootstrap e sincroniza

### Mecanismos de Coordenação

#### Parte 3 - Ordenação Total (Total Order Multicast)

O sistema garante que **todos os peers entregam mensagens na mesma ordem global**:

**Algoritmo:**
- Cada mensagem recebe timestamp lógico de Lamport
- Ordenação determinística: `(lamport_ts, origin_node)`
- Buffer de holdback atrasa entrega até garantir ordem
- Condição de estabilidade: `lamport_ts < clock_local`

**Cliente:**
- Mantém buffer ordenado próprio
- Só exibe mensagens quando na ordem correta
- Garante que usuário vê mensagens na ordem global

#### Parte 4 - Primary-Backup com Eleição de Líder (Bully)

O sistema usa **um líder para sequenciar todas as mensagens**:

**Algoritmo:**
- Líder é o nó com maior `node_id`
- Líder incrementa contador sequencial para cada mensagem
- Backups entregam mensagens na ordem do líder
- Sem holdback buffer (entrega imediata)

**Eleição de Líder (Bully):**
1. Nó detecta falha do líder (via heartbeat)
2. Envia ELECTION para nós com ID maior
3. Se recebe OK, aguarda novo líder
4. Se timeout sem OK, torna-se líder
5. Novo líder anuncia com COORDINATOR

### Sincronização de Réplicas

**Parte 3 (Lamport):**
- Novo nó solicita histórico de peers
- Histórico ordenado por `(lamport_ts, origin_node)`
- Relógio de Lamport inicializado com máximo visto
- Mensagens salvas em disco a cada 5 minutos
- Ao reiniciar, carrega histórico e relógio do JSON

**Parte 4 (Bully):**
- Novo nó solicita histórico de peers
- Histórico ordenado por `seq_number`
- Contador de sequência inicializado com máximo visto
- Identifica líder atual (maior node_id)
- Mensagens salvas em disco a cada 5 minutos
- Ao reiniciar, carrega histórico e reidentifica líder

## Requisitos

- Python 3
- rpyc (`pip install rpyc`)

## Configuração

Para mudar portas e timeouts edite `constCS.py`:

```python
# P2P
BOOTSTRAP_HOST = 'localhost'
BOOTSTRAP_PORT = 5679
NODE_BASE_PORT = 5679

# Heartbeat
HEARTBEAT_INTERVAL = 30  # segundos
HEARTBEAT_TIMEOUT = 60   # segundos

# Difusão (Parte 3 - Lamport)
PROPAGATION_FANOUT = 3   # peers por propagação
MSG_ID_CACHE_SIZE = 10000

# Ordenação Total (Parte 3 - Lamport)
LAMPORT_INITIAL_CLOCK = 0
DELIVERY_CHECK_INTERVAL = 0.1  # 100ms
```

## Estrutura de Dados

### Lista de Peers

```python
peers = {
    'node_2': {
        'host': 'localhost',
        'port': 5680,
        'connection': <rpyc_conn>,
        'last_heartbeat': 1234567890.0,
        'status': 'ACTIVE',
        'missed_heartbeats': 0
    }
}
```

### Mensagem

**Parte 3 (Lamport):**
```python
{
    'type': 'CHAT',
    'sender': 'Alice',
    'message': 'Olá mundo!',
    'timestamp': 1234567890.0,    # timestamp físico
    'msg_id': 'node1_42',          # ID único
    'lamport_ts': 156,             # timestamp lógico Lamport
    'origin_node': 'node1'         # nó de origem
}
```

**Parte 4 (Bully):**
```python
{
    'type': 'CHAT',
    'sender': 'Alice',
    'message': 'Olá mundo!',
    'timestamp': 1234567890.0,    # timestamp físico
    'msg_id': 'node1_42',          # ID único
    'seq_number': 156,             # sequência do líder
    'leader_id': 'node3'           # quem era o líder
}
```

### Histórico

Lista replicada em todos os nós, salva em `history_<node_id>.json`.

- **Parte 3**: Ordenado por `(lamport_ts, origin_node)`
- **Parte 4**: Ordenado por `seq_number`