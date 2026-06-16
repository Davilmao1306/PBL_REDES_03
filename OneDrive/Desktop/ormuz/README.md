# Estreito de Ormuz — Blockchain P2P

Ledger distribuído para gestão de drones, créditos operacionais e laudos imutáveis de missão.

---

## Requisitos

- Python 3.10+
- Todos os computadores na **mesma rede Wi-Fi/LAN** do laboratório

---

## Instalação (em **cada** computador)

```bash
# 1. Clone ou copie a pasta ormuz/

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Descubra o IP do computador
#    Linux/macOS:
ip a | grep "inet " | grep -v 127
#    Windows:
ipconfig
```

---

## Execução em múltiplos computadores

### Computador A (primeiro nó — sem peers)

```bash
python node/app.py --port 5000 --automine
```

### Computador B (conecta ao A)

```bash
# Substitua 192.168.X.X pelo IP real do Computador A
python node/app.py --port 5000 --peers http://192.168.X.X:5000 --automine
```

### Computador C (conecta ao A e ao B)

```bash
python node/app.py --port 5000 --peers http://192.168.X.X:5000 http://192.168.Y.Y:5000 --automine
```

> **Dica:** todos podem usar a porta 5000. O que diferencia os nós é o IP da máquina.

---

## Interface Web

Abra no navegador de **qualquer** computador na rede:

```
http://IP_DA_MAQUINA:5000/
```

---

## API REST — Referência Completa

### Cadeia e nós

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/chain` | Retorna a blockchain completa |
| GET | `/nodes/list` | Lista peers conhecidos |
| POST | `/nodes/register` | Registra novos peers `{"nodes": ["http://IP:PORT"]}` |
| POST | `/nodes/sync` | Sincroniza cadeia com peers (cadeia mais longa) |
| POST | `/mine` | Minera bloco com transações pendentes |

### Saldos e auditoria

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/balances` | Saldos de todas as empresas (derivados do ledger) |
| GET | `/balance/<empresa>` | Saldo de empresa específica |
| GET | `/logs` | Laudos de missão registrados no ledger |
| GET | `/payments` | Histórico de pagamentos |
| GET | `/audit/validate` | Valida integridade da cadeia |
| GET | `/transactions/pending` | Transações na mempool |

### Drones

| Método | Rota | Body | Descrição |
|--------|------|------|-----------|
| GET | `/drones` | — | Status de todos os drones |
| POST | `/drones/request` | `{company, drone_id, route}` | Solicita escolta (50 créditos) |
| POST | `/drones/complete` | `{drone_id, result, details}` | Conclui missão e grava laudo |

### Transações

| Método | Rota | Body | Descrição |
|--------|------|------|-----------|
| POST | `/transactions/new` | `{type, from, to, amount}` | Transferência de créditos |

---

## Testes para a arguição

### 1. Teste de integridade (adulteração)

```bash
# Em outro terminal, verifique a cadeia
curl http://IP:5000/audit/validate

# Resposta esperada: "chain_valid": true
```

### 2. Teste de duplo gasto

```bash
# Em duas janelas simultaneamente, tente usar o mesmo saldo:
curl -X POST http://IP_A:5000/drones/request \
  -H "Content-Type: application/json" \
  -d '{"company":"AlphaShipping","drone_id":"DRONE-01","route":"Norte"}'

curl -X POST http://IP_B:5000/drones/request \
  -H "Content-Type: application/json" \
  -d '{"company":"AlphaShipping","drone_id":"DRONE-01","route":"Norte"}'

# Apenas UMA deve ser aceita
```

### 3. Teste de falha de nó

```bash
# Derrube o Computador A (Ctrl+C)
# Faça uma requisição no Computador B — deve funcionar normalmente
curl http://IP_B:5000/chain
```

### 4. Teste de sincronização

```bash
# Com nó A off, mine um bloco no B
curl -X POST http://IP_B:5000/mine

# Ligue A novamente e sincronize
python node/app.py --port 5000 --peers http://IP_B:5000
# A cadeia do B (maior) será adotada automaticamente
```

### 5. Consulta de saldo consistente

```bash
# Compare saldo da mesma empresa em dois nós
curl http://IP_A:5000/balance/AlphaShipping
curl http://IP_B:5000/balance/AlphaShipping
# Devem retornar o mesmo valor após sincronização
```

---

## Resultados de missão disponíveis

| Valor | Descrição |
|-------|-----------|
| `ROTA_SEGURA` | Passagem liberada |
| `OBSTACULO` | Obstáculo físico detectado |
| `INCIDENTE` | Atividade militar suspeita |
| `BLOQUEIO` | Rota bloqueada |

---

## Empresas pré-configuradas (bloco gênese)

Cada empresa recebe **1000 créditos** no bloco gênese:

- `AlphaShipping`
- `BetaMarine`
- `GammaCargo`
- `DeltaNaval`

Custo de escolta: **50 créditos** por missão.

---

## Arquitetura

```
┌──────────────────────────────────────────────────────┐
│                    Rede P2P (HTTP/LAN)               │
│                                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────┐  │
│  │   NÓ A      │◄──►│   NÓ B      │◄──►│  NÓ C    │  │
│  │ :5000       │    │ :5000       │    │ :5000    │  │
│  │             │    │             │    │          │  │
│  │ Blockchain  │    │ Blockchain  │    │Blockchain│  │
│  │ (cópia local│    │ (cópia local│    │(cópia    │  │
│  │  completa)  │    │  completa)  │    │ completa)│  │
│  └─────────────┘    └─────────────┘    └──────────┘  │
└──────────────────────────────────────────────────────┘

Consenso: cadeia mais longa válida (PoW — 3 zeros)
Propagação: broadcast HTTP para todos os peers conhecidos
```

---

## Perguntas frequentes da arguição

**Por que blockchain e não banco de dados?**
Bancos de dados têm um ponto central de confiança. A blockchain distribui o ledger entre todos os nós — nenhuma nação pode alterar um registro sem que a rede detecte pela quebra do encadeamento de hashes.

**Como funciona o consenso?**
Proof-of-Work (PoW): o hash do bloco deve começar com 3 zeros. Na divergência de cadeia (fork), a regra da cadeia mais longa vence.

**Como o duplo gasto é prevenido?**
Antes de aceitar uma transação na mempool, o nó soma os gastos pendentes do remetente e compara com o saldo derivado do ledger. Se insuficiente, rejeita. O `tx_id` único também impede reenvios.

**O que garante a imutabilidade dos laudos?**
Cada bloco contém o hash do bloco anterior. Alterar qualquer campo de qualquer bloco invalida toda a cadeia subsequente — detectável por qualquer nó com `GET /audit/validate`.
