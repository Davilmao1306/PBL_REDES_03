"""
Blockchain do Estreito de Ormuz - Núcleo
Implementa: blocos, cadeia, PoW, validação, prevenção de duplo gasto
"""

import hashlib
import json
import time
from typing import List, Optional


# ──────────────────────────────────────────────
# Bloco
# ──────────────────────────────────────────────

class Block:
    def __init__(
        self,
        index: int,
        transactions: list,
        previous_hash: str,
        nonce: int = 0,
        timestamp: float = None,
    ):
        self.index = index
        self.timestamp = timestamp or time.time()
        self.transactions = transactions          # lista de dicts
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Calcula SHA-256 do conteúdo do bloco (determinístico)."""
        block_string = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "transactions": self.transactions,
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
            },
            sort_keys=True,
        )
        return hashlib.sha256(block_string.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        b = cls(
            index=data["index"],
            transactions=data["transactions"],
            previous_hash=data["previous_hash"],
            nonce=data["nonce"],
            timestamp=data["timestamp"],
        )
        b.hash = data["hash"]   # confia no hash recebido; validamos separado
        return b


# ──────────────────────────────────────────────
# Blockchain
# ──────────────────────────────────────────────

DIFFICULTY = 3          # zeros à esquerda exigidos (ajuste conforme hardware)
GENESIS_CREDITS = 1000  # créditos iniciais por empresa no bloco gênese


class Blockchain:
    def __init__(self):
        self.chain: List[Block] = []
        self.pending_transactions: List[dict] = []
        self._lock_mining = False   # flag simples para evitar mineração dupla

        # Bloco gênese com saldos iniciais das companhias
        self._create_genesis()

    # ── Gênese ────────────────────────────────

    def _create_genesis(self):
        """Cria o bloco 0 com emissão inicial de créditos para cada companhia."""
        genesis_txs = []
        for company in ["AlphaShipping", "BetaMarine", "GammaCargo", "DeltaNaval"]:
            genesis_txs.append({
                "type": "GENESIS",
                "to": company,
                "amount": GENESIS_CREDITS,
                "tx_id": f"genesis_{company}",
                "timestamp": 0,
            })
        genesis = Block(0, genesis_txs, "0")
        genesis.hash = genesis.compute_hash()
        self.chain.append(genesis)

    # ── PoW ───────────────────────────────────

    def proof_of_work(self, block: Block) -> str:
        """Minera o bloco: incrementa nonce até hash começar com DIFFICULTY zeros."""
        block.nonce = 0
        computed = block.compute_hash()
        prefix = "0" * DIFFICULTY
        while not computed.startswith(prefix):
            block.nonce += 1
            computed = block.compute_hash()
        return computed

    # ── Mineração ─────────────────────────────

    def mine_pending(self, miner_node: str) -> Optional[Block]:
        """
        Agrupa transações pendentes em um bloco e minera.
        Retorna None se não houver transações.
        """
        if not self.pending_transactions:
            return None

        # Pega todas as pendentes e limpa a fila
        txs = list(self.pending_transactions)
        self.pending_transactions = []

        new_block = Block(
            index=len(self.chain),
            transactions=txs,
            previous_hash=self.last_block.hash,
        )
        new_block.hash = self.proof_of_work(new_block)
        self.chain.append(new_block)
        return new_block

    # ── Saldos ────────────────────────────────

    def get_balance(self, company: str) -> int:
        """
        Deriva o saldo percorrendo TODOS os blocos confirmados.
        Nunca usa variável local — sempre recalcula a partir do ledger.
        """
        balance = 0
        for block in self.chain:
            for tx in block.transactions:
                if tx.get("type") == "GENESIS" and tx.get("to") == company:
                    balance += tx["amount"]
                elif tx.get("type") == "PAYMENT":
                    if tx.get("from") == company:
                        balance -= tx["amount"]
                    if tx.get("to") == company:
                        balance += tx["amount"]
                elif tx.get("type") == "REFUND":
                    if tx.get("to") == company:
                        balance += tx["amount"]
        return balance

    def all_balances(self) -> dict:
        companies = set()
        for block in self.chain:
            for tx in block.transactions:
                if "from" in tx:
                    companies.add(tx["from"])
                if "to" in tx:
                    companies.add(tx["to"])
        return {c: self.get_balance(c) for c in companies}

    # ── Ids de transações já confirmadas ──────

    def confirmed_tx_ids(self) -> set:
        """Conjunto de tx_id já incluídos em blocos — usado para duplo gasto."""
        ids = set()
        for block in self.chain:
            for tx in block.transactions:
                if "tx_id" in tx:
                    ids.add(tx["tx_id"])
        return ids

    def pending_tx_ids(self) -> set:
        return {tx["tx_id"] for tx in self.pending_transactions if "tx_id" in tx}

    # ── Adicionar transação ────────────────────

    def add_transaction(self, tx: dict) -> tuple[bool, str]:
        """
        Valida e adiciona transação à mempool.
        Retorna (sucesso, mensagem).
        """
        tx_type = tx.get("type")

        # ── Verificar tx_id duplicado (duplo gasto) ──
        if tx.get("tx_id") in self.confirmed_tx_ids():
            return False, "Transação já confirmada no ledger (duplo gasto bloqueado)"
        if tx.get("tx_id") in self.pending_tx_ids():
            return False, "Transação já está na mempool (duplo gasto bloqueado)"

        # ── Verificar drone já alocado no ledger (entre nós) ──────────────
        # Quando dois nós distintos enviam DRONE_ALLOC para o mesmo drone
        # quase simultaneamente, o segundo é rejeitado aqui na mempool.
        if tx_type == "DRONE_ALLOC":
            drone_id = tx.get("drone_id")
            # Verifica blocos confirmados
            alloc_open = False
            for block in self.chain:
                for t in block.transactions:
                    if t.get("drone_id") != drone_id:
                        continue
                    if t.get("type") == "DRONE_ALLOC":
                        alloc_open = True
                    elif t.get("type") == "DRONE_RELEASE":
                        alloc_open = False
            # Verifica mempool pendente
            for t in self.pending_transactions:
                if t.get("drone_id") != drone_id:
                    continue
                if t.get("type") == "DRONE_ALLOC":
                    alloc_open = True
                elif t.get("type") == "DRONE_RELEASE":
                    alloc_open = False
            if alloc_open:
                return False, f"Drone {drone_id} já está alocado no ledger (duplo gasto de drone bloqueado)"

        # ── Validar pagamento ────────────────────────
        if tx_type == "PAYMENT":
            sender = tx.get("from")
            amount = tx.get("amount", 0)

            # Saldo confirmado no ledger
            confirmed_balance = self.get_balance(sender)

            # Subtrair o que já está pendente para o mesmo sender
            pending_spent = sum(
                t["amount"]
                for t in self.pending_transactions
                if t.get("type") == "PAYMENT" and t.get("from") == sender
            )

            available = confirmed_balance - pending_spent

            if available < amount:
                return (
                    False,
                    f"Saldo insuficiente: disponível={available}, solicitado={amount}",
                )

        tx["timestamp"] = tx.get("timestamp", time.time())
        self.pending_transactions.append(tx)
        return True, "Transação aceita na mempool"

    # ── Missões (laudos imutáveis) ─────────────

    def add_mission_log(self, log: dict) -> tuple[bool, str]:
        """Registra laudo de missão como transação especial."""
        log["type"] = "MISSION_LOG"
        log["timestamp"] = log.get("timestamp", time.time())
        if not log.get("tx_id"):
            log["tx_id"] = f"mission_{log.get('drone_id', 'X')}_{int(log['timestamp'])}"
        return self.add_transaction(log)

    # ── Laudos ────────────────────────────────

    def get_mission_logs(self) -> list:
        logs = []
        for block in self.chain:
            for tx in block.transactions:
                if tx.get("type") == "MISSION_LOG":
                    logs.append({**tx, "block_index": block.index, "block_hash": block.hash})
        return logs

    def get_payments(self) -> list:
        payments = []
        for block in self.chain:
            for tx in block.transactions:
                if tx.get("type") == "PAYMENT":
                    payments.append({**tx, "block_index": block.index})
        return payments

    # ── Validação da cadeia ────────────────────

    def is_valid(self) -> bool:
        """
        Percorre a cadeia verificando:
        1. Hash de cada bloco está correto
        2. previous_hash encadeia corretamente
        3. Hash satisfaz dificuldade (exceto gênese)
        """
        prefix = "0" * DIFFICULTY
        for i in range(1, len(self.chain)):
            curr = self.chain[i]
            prev = self.chain[i - 1]

            # Recalcula e compara
            if curr.hash != curr.compute_hash():
                return False

            # Encadeamento
            if curr.previous_hash != prev.hash:
                return False

            # PoW
            if not curr.hash.startswith(prefix):
                return False

        return True

    # ── Substituição de cadeia (consenso) ─────

    def replace_chain(self, new_chain_data: list) -> bool:
        """
        Regra da cadeia mais longa: aceita nova cadeia se for mais longa e válida.
        """
        if len(new_chain_data) <= len(self.chain):
            return False

        # Reconstrói objetos Block
        new_chain = [Block.from_dict(b) for b in new_chain_data]

        # Valida nova cadeia
        prefix = "0" * DIFFICULTY
        for i in range(1, len(new_chain)):
            curr = new_chain[i]
            prev = new_chain[i - 1]
            if curr.hash != curr.compute_hash():
                return False
            if curr.previous_hash != prev.hash:
                return False
            if not curr.hash.startswith(prefix):
                return False

        self.chain = new_chain
        return True

    # ── Utilitários ───────────────────────────

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def to_list(self) -> list:
        return [b.to_dict() for b in self.chain]

    def length(self) -> int:
        return len(self.chain)
