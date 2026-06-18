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

# ──────────────────────────────────────────────
# Bloco
# ──────────────────────────────────────────────

class Block:
    """
    Representa um único bloco de dados dentro da Blockchain.
    Ele empacota as transações e as conecta matematicamente ao bloco anterior.
    """
    def __init__(
        self,
        index: int,
        transactions: list,
        previous_hash: str,
        nonce: int = 0,
        timestamp: float = None,
    ):
        # Posição do bloco na cadeia (ex: 0 é o Gênese, 1 é o próximo, etc)
        self.index = index
        
        # Marcação exata de quando o bloco foi criado
        self.timestamp = timestamp or time.time()
        
        # Lista contendo as transações de escolta e pagamentos (payload)
        self.transactions = transactions          
        
        # O "elo da corrente". É o hash do bloco que veio antes deste.
        # É isso que impede que blocos antigos sejam alterados sem quebrar a rede.
        self.previous_hash = previous_hash
        
        # Um número arbitrário usado APENAS para resolver o quebra-cabeça 
        # da mineração (Proof of Work). Ele muda até o hash ficar correto.
        self.nonce = nonce
        
        # O "RG" único deste bloco, calculado com base em todo o conteúdo acima.
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        """
        Calcula a assinatura digital única (SHA-256) do conteúdo do bloco.
        É uma função determinística: os mesmos dados sempre geram o mesmo hash.
        """
        # Converte o dicionário do bloco em uma string JSON.
        # O 'sort_keys=True' é OBRIGATÓRIO para garantir que a ordem 
        # das chaves não mude, o que geraria um hash totalmente diferente.
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
        # Aplica a função matemática SHA-256 e retorna o texto em hexadecimal
        return hashlib.sha256(block_string.encode()).hexdigest()

    def to_dict(self) -> dict:
        """
        Transforma o objeto Bloco em um dicionário Python.
        Isso é necessário para podermos enviar o bloco pela rede (via HTTP/JSON)
        para os outros computadores (peers).
        """
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
        """
        Faz o caminho inverso do 'to_dict'. 
        Quando um nó recebe um bloco pela rede (um dicionário JSON), 
        esse método reconstrói o objeto Block na memória.
        """
        b = cls(
            index=data["index"],
            transactions=data["transactions"],
            previous_hash=data["previous_hash"],
            nonce=data["nonce"],
            timestamp=data["timestamp"],
        )
        # Ao reconstruir, confiamos inicialmente no hash que veio da rede,
        # mas ele será rigorosamente validado depois pela regra de consenso.
        b.hash = data["hash"]   
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
        Calcula o saldo exato de uma empresa.
        ATENÇÃO BAREMA: Não existe uma variável 'saldo' guardada num banco de dados.
        O saldo é "derivado", ou seja, o sistema viaja no tempo lendo todos os blocos
        desde o Gênese, somando o que a empresa recebeu e subtraindo o que ela gastou.
        """
        balance = 0
        for block in self.chain:
            for tx in block.transactions:
                # Se for o dinheiro criado no Bloco 0
                if tx.get("type") == "GENESIS" and tx.get("to") == company:
                    balance += tx["amount"]
                # Se for um pagamento normal
                elif tx.get("type") == "PAYMENT":
                    if tx.get("from") == company:
                        balance -= tx["amount"] # Saiu dinheiro
                    if tx.get("to") == company:
                        balance += tx["amount"] # Entrou dinheiro
                # Se for um reembolso (caso a missão falhasse, por exemplo)
                elif tx.get("type") == "REFUND":
                    if tx.get("to") == company:
                        balance += tx["amount"]
        return balance

    def all_balances(self) -> dict:
        """Retorna o saldo de todas as empresas que já transacionaram na rede."""
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
        """
        Varre a blockchain e guarda todos os IDs de transações que já estão
        seladas em blocos. Usado para evitar que a mesma transação seja processada duas vezes.
        """
        ids = set()
        for block in self.chain:
            for tx in block.transactions:
                if "tx_id" in tx:
                    ids.add(tx["tx_id"])
        return ids

    def pending_tx_ids(self) -> set:
        """Retorna os IDs das transações que estão na fila de espera (mempool)."""
        return {tx["tx_id"] for tx in self.pending_transactions if "tx_id" in tx}

    # ── Adicionar transação (O FILTRO DE DUPLO GASTO) ────────────────────

    def add_transaction(self, tx: dict) -> tuple[bool, str]:
        """
        Valida e adiciona uma transação à fila de espera (mempool).
        É AQUI QUE O DUPLO GASTO É BARRADO.
        Retorna (Sucesso booleano, Mensagem).
        """
        tx_type = tx.get("type")

        # 1ª Barreira: A transação já existe em um bloco minerado?
        if tx.get("tx_id") in self.confirmed_tx_ids():
            return False, "Transação já confirmada no ledger (duplo gasto bloqueado)"
            
        # 2ª Barreira: A transação já está na fila de espera?
        if tx.get("tx_id") in self.pending_tx_ids():
            return False, "Transação já está na mempool (duplo gasto bloqueado)"

        # 3ª Barreira: Regra de Negócio (Tem dinheiro para pagar?)
        if tx_type == "PAYMENT":
            sender = tx.get("from")
            amount = tx.get("amount", 0)

            # Pega o saldo real confirmado nos blocos
            confirmed_balance = self.get_balance(sender)

            # Calcula quanto dinheiro a empresa já comprometeu na fila de espera.
            # Ex: Se ela tem 100, pediu um drone (50 na fila) e tentou pedir outro,
            # o pending_spent será 50.
            pending_spent = sum(
                t["amount"]
                for t in self.pending_transactions
                if t.get("type") == "PAYMENT" and t.get("from") == sender
            )

            # Saldo disponível = Saldo real - Dinheiro já comprometido na fila
            available = confirmed_balance - pending_spent

            # Se tentar gastar mais do que tem disponível, a transação é negada na hora
            if available < amount:
                return (
                    False,
                    f"Saldo insuficiente: disponível={available}, solicitado={amount}",
                )

        # Se passou por todas as barreiras, carimba a hora e coloca na fila
        tx["timestamp"] = tx.get("timestamp", time.time())
        self.pending_transactions.append(tx)
        return True, "Transação aceita na mempool"

    # ... (O restante do código, como add_mission_log e replace_chain, continua igual)
