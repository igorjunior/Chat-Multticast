# Chat Distribuído - Trabalho SD

Sistema de chat com comunicação multicast e histórico sincronizado.

## Funcionalidades

O sistema implementa um chat onde varios clientes se conectam a um servidor central que distribui as mensagens para todos (multicast). Cada cliente mantem uma copia local do historico de mensagens.

Recursos implementados:
- Mensagens distribuidas para todos os clientes
- Historico replicado em cada cliente
- IDs sequenciais para manter ordem das mensagens
- Confirmacoes de leitura
- Novos clientes recebem todo o historico ao entrar

## Arquivos

- server.py: servidor que gerencia as conexoes e distribui mensagens
- client.py: cliente de chat com interface de linha de comando
- constCS.py: configuracoes (host, porta, buffer)

## Protocolo

Mensagens sao trocadas em JSON via TCP. Tipos de mensagem:
- JOIN: cliente entra no chat
- CHAT: mensagem de conversa
- HISTORY: sincronizacao do historico
- READ_CONFIRM: confirmacao de leitura
- SYSTEM: notificacoes do sistema

## Utilização

Iniciar servidor:
```bash
python server.py
```

Conectar clientes:
```bash
python client.py Erick
python client.py Igor
python client.py Matheus
```

Comandos disponiveis no cliente:
- Digite texto para enviar mensagem
- /history - ver historico
- /confirmations - ver confirmacoes de leitura  
- /quit - sair

## Como funciona

O servidor atribui IDs sequenciais (1, 2, 3...) para cada mensagem, garantindo que todos os clientes vejam na mesma ordem. Quando um novo cliente entra, ele recebe todo o historico do servidor para sincronizar.

Cada mensagem tem:
- ID unico (atribuido pelo servidor)
- Timestamp
- Sender
- Conteudo

O sistema resolve o problema de ordenacao de mensagens usando o servidor como coordenador central. Clientes desconectados sao removidos automaticamente.

## Proximas etapas do trabalho

- Parte 2: Substituir sockets por RPC e filas de mensagens
- Parte 3: Implementar ordenacao total (Cap. 5)
- Parte 4: Mecanismo de coordenacao mais leve (Cap. 7)

## Requisitos

Python 3

## Configuracao

Para mudar host/porta edite constCS.py:
```python
SERVER_HOST = 'localhost'
SERVER_PORT = 5679
BUFFER_SIZE = 4096
```
