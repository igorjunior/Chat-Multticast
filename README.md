# Chat Distribuído P2P

Sistema de chat peer-to-peer com comunicação RPC, difusão de mensagens e histórico replicado.

## Funcionalidades

O sistema implementa um chat distribuído onde múltiplos nós servidores (peers) se conectam formando uma rede P2P. Cada nó mantém uma réplica completa do histórico e propaga mensagens para outros peers. Clientes (usuários) se conectam aos nós para enviar e receber mensagens.

Recursos implementados:
- Rede P2P com comunicação RPC (rpyc)
- Bootstrap leve para descoberta inicial de peers
- Difusão eficiente com propagação controlada (N*log(N))
- Discovery distribuído via JOIN propagado
- **Ordenação total com Relógios de Lamport
- Buffer de holdback para garantir ordem global
- Heartbeat para detecção de falhas (timeout 60s)
- Histórico replicado em todos os nós
- Persistência de mensagens em disco
- Confirmações de leitura
- Prevenção de duplicatas com cache de IDs

## Arquitetura

**Bootstrap Node:** Fornece lista inicial de peers quando novos nós entram na rede. É um servidor P2P.

**Peer Nodes:** São os servidores do sistema P2P. Cada nó/peer é um servidor RPC que mantém conexões com outros peers e propaga mensagens. Peers não são os clientes/usuários do chat, são os nós servidores da rede distribuída.

**Client UI:** Interface leve que conecta a um peer/nó local para enviar/receber mensagens. Representa um usuário do chat.

Cada nó armazena:
- Lista de peers (host, porta, conexão RPC)
- Histórico completo de mensagens (réplica local)
- Cache de IDs processados (previne duplicatas)
- Status de heartbeat dos peers
- Relógio lógico de Lamport
- Buffer de holdback para ordenação total

## Arquivos

- `node.py`: nó P2P com servidor RPC e lógica de propagação
- `client_ui.py`: cliente de chat com interface de linha de comando
- `constCS.py`: configurações (portas, timeouts, fanout)
- `start_bootstrap.bat`: script para iniciar nó bootstrap

## Protocolo

Comunicação via RPC (rpyc). Cada nó expõe métodos para:

**Gerenciamento de rede:**
- `get_initial_peers()`: obtém lista inicial do bootstrap
- `receive_join()`: recebe JOIN de novo peer e propaga
- `heartbeat()`: recebe heartbeat de peer
- `peer_list_update()`: sincroniza lista de peers

**Mensagens de chat:**
- `receive_chat_message()`: recebe mensagem CHAT com propagação
- `receive_system_message()`: recebe mensagem SYSTEM
- `receive_read_confirm()`: recebe confirmação de leitura

**Interface com cliente:**
- `join_user()`: usuário entra no chat
- `send_message()`: envia mensagem
- `get_messages()`: consome mensagens da fila
- `read_confirm()`: confirma leitura
- `leave_user()`: sai do chat

Tipos de mensagem:
- `CHAT`: mensagem de conversa
- `SYSTEM`: notificações do sistema
- `READ_CONFIRM`: confirmação de leitura
- `JOIN`: entrada de novo peer na rede

## Utilização

### Iniciar nó bootstrap

```bash
python node.py --node-id bootstrap --port 5679 --bootstrap
```

Ou simplesmente execute e forneça os argumentos quando solicitado:
```bash
python node.py
```

### Iniciar nós peers

```bash
python node.py --node-id node2 --port 5680
python node.py --node-id node3 --port 5681
```

Ou execute sem argumentos e será solicitado:
```bash
python node.py
```

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

O sistema usa **difusão controlada** para evitar N² mensagens:

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

### Detecção de Falhas

Sistema de heartbeat detecta nós inativos:

1. Cada nó envia heartbeat a cada 30-40s (com jitter)
2. Monitor verifica timeouts a cada 10s
3. Se peer não responde por 60s:
   - Peer é removido da lista local
   - Conexão RPC é fechada
   - Mensagem SYSTEM notifica saída
4. Se peer volta, reconecta ao bootstrap e sincroniza

### Ordenação Total (Total Order Multicast)

O sistema garante que **todos os peers entregam mensagens na mesma ordem global**:

**Algoritmo:**
- Cada mensagem recebe timestamp lógico de Lamport
- Ordenação determinística: `(lamport_ts, origin_node)`
- Buffer de holdback atrasa entrega até garantir ordem
- Condição de estabilidade: `lamport_ts < clock_local`

**Garantias:**
- ✅ Ordem total: todos entregam na mesma ordem
- ✅ Causalidade preservada
- ✅ Determinismo: desempate por `node_id`

**Cliente:**
- Mantém buffer ordenado próprio
- Só exibe mensagens quando na ordem correta
- Garante que usuário vê mensagens na ordem global

### Sincronização de Réplicas

- Novo nó que entra solicita histórico de peers
- Histórico já vem ordenado por `(lamport_ts, origin_node)`
- Relógio de Lamport inicializado com máximo visto
- Mensagens são salvas em disco a cada 5 minutos
- Ao reiniciar, nó carrega histórico e relógio do arquivo JSON

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

# Difusão
PROPAGATION_FANOUT = 3   # peers por propagação
MSG_ID_CACHE_SIZE = 10000

# Ordenação Total
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

### Histórico

Lista replicada em todos os nós, salva em `history_<node_id>.json`.