"""
Gestão de Drones - Estreito de Ormuz
==============================================
Correção crítica de concorrência distribuída:
  O estado dos drones NÃO vive mais em self.drones (RAM local).
  A fonte da verdade é o próprio ledger — igual ao que já é feito
  com saldos. Um drone está ocupado se e somente se existe uma
  transação DRONE_ALLOC confirmada (ou pendente) sem um
  DRONE_RELEASE correspondente.

  Isso resolve o race condition entre nós diferentes: o Nó A e o
  Nó B consultam o mesmo ledger distribuído para saber se um drone
  está livre. O threading.Lock protege apenas a escrita atômica na
  mempool local (evita race dentro do mesmo processo Flask).
"""

import threading
import time
import uuid

ESCORT_COST = 50   # créditos por escolta de drone
DRONE_IDS   = [f"DRONE-{i:02d}" for i in range(1, 6)]


class DroneManager:
    def __init__(self, blockchain):
        self.blockchain = blockchain
        # Lock local: protege apenas a seção crítica dentro do mesmo nó.
        # A proteção entre nós é garantida pelo ledger.
        self._lock = threading.Lock()

    # ── Estado derivado do ledger ──────────────

    def _drone_state_from_ledger(self, drone_id: str) -> dict:
        """
        Reconstrói o estado atual do drone varrendo TODA a cadeia
        confirmada + mempool, igual ao que get_balance faz para créditos.

        Retorna: {
            "status":      "available" | "on_mission",
            "assigned_to": str | None,
            "mission_id":  str | None,
            "route":       str | None,
            "alloc_tx":    str | None,   # tx_id da alocação ativa
            "start":       float | None,
        }
        """
        alloc_tx  = None   # tx_id da última alocação ainda aberta
        alloc_data = {}

        # 1. Percorre blocos confirmados
        for block in self.blockchain.chain:
            for tx in block.transactions:
                if tx.get("drone_id") != drone_id:
                    continue
                if tx.get("type") == "DRONE_ALLOC":
                    alloc_tx   = tx["tx_id"]
                    alloc_data = tx
                elif tx.get("type") == "DRONE_RELEASE":
                    # Se o release referencia a alocação ativa, fecha
                    if tx.get("alloc_tx") == alloc_tx:
                        alloc_tx   = None
                        alloc_data = {}

        # 2. Sobrepõe com mempool (transações ainda não mineradas)
        for tx in self.blockchain.pending_transactions:
            if tx.get("drone_id") != drone_id:
                continue
            if tx.get("type") == "DRONE_ALLOC":
                alloc_tx   = tx["tx_id"]
                alloc_data = tx
            elif tx.get("type") == "DRONE_RELEASE":
                if tx.get("alloc_tx") == alloc_tx:
                    alloc_tx   = None
                    alloc_data = {}

        if alloc_tx is None:
            return {
                "status": "available", "assigned_to": None,
                "mission_id": None, "route": None,
                "alloc_tx": None, "start": None,
            }
        return {
            "status":      "on_mission",
            "assigned_to": alloc_data.get("company"),
            "mission_id":  alloc_data.get("mission_id"),
            "route":       alloc_data.get("route"),
            "alloc_tx":    alloc_tx,
            "start":       alloc_data.get("timestamp"),
        }

    # ── Consulta pública ──────────────────────

    def list_drones(self) -> dict:
        """Retorna estado de todos os drones derivado do ledger."""
        return {d: self._drone_state_from_ledger(d) for d in DRONE_IDS}

    def available_drones(self) -> list:
        return [d for d in DRONE_IDS
                if self._drone_state_from_ledger(d)["status"] == "available"]

    # ── Requisição de escolta ──────────────────

    def request_escort(self, company: str, drone_id: str, route: str) -> tuple[bool, str]:
        """
        Alocação distribuída segura:
          1. Dentro do lock local, consulta o estado do drone NO LEDGER
          2. Verifica saldo no ledger
          3. Insere atomicamente DRONE_ALLOC + PAYMENT na mempool
          4. Propaga para peers (feito em app.py)

        Por que o lock local ainda importa:
          Impede que duas threads do mesmo nó Flask passem pela
          verificação simultaneamente (requisições concorrentes ao
          mesmo processo). Entre nós distintos, a proteção vem do
          ledger: quando ambos propagam e o minerador inclui no bloco,
          apenas a primeira transação é válida — a segunda referencia
          um drone já alocado e é rejeitada na validação da cadeia.
        """
        if drone_id not in DRONE_IDS:
            return False, f"Drone {drone_id} não existe"

        with self._lock:
            # ── 1. Estado do drone via ledger ────────
            state = self._drone_state_from_ledger(drone_id)
            if state["status"] != "available":
                return (
                    False,
                    f"Drone {drone_id} já alocado para {state['assigned_to']} "
                    f"(missão {state['mission_id']}) — fonte: ledger",
                )

            # ── 2. Saldo via ledger ──────────────────
            confirmed_balance = self.blockchain.get_balance(company)
            pending_spent = sum(
                t["amount"]
                for t in self.blockchain.pending_transactions
                if t.get("type") == "PAYMENT" and t.get("from") == company
            )
            available = confirmed_balance - pending_spent

            if available < ESCORT_COST:
                return (
                    False,
                    f"Créditos insuficientes: disponível={available}, custo={ESCORT_COST}",
                )

            # ── 3. Transações atômicas na mempool ───
            mission_id = f"MISS-{uuid.uuid4().hex[:6].upper()}"
            alloc_tx_id = f"alloc_{drone_id}_{uuid.uuid4().hex[:8]}"
            pay_tx_id   = f"pay_{drone_id}_{company}_{uuid.uuid4().hex[:8]}"

            # Transação de alocação do drone (estado no ledger)
            alloc_tx = {
                "type":       "DRONE_ALLOC",
                "drone_id":   drone_id,
                "company":    company,
                "mission_id": mission_id,
                "route":      route,
                "tx_id":      alloc_tx_id,
            }

            # Transação de pagamento em créditos
            pay_tx = {
                "type":     "PAYMENT",
                "from":     company,
                "to":       "FLEET_FUND",
                "amount":   ESCORT_COST,
                "tx_id":    pay_tx_id,
                "drone_id": drone_id,
                "route":    route,
                "note":     f"Escolta {mission_id} — {route}",
            }

            ok_alloc, msg_alloc = self.blockchain.add_transaction(alloc_tx)
            if not ok_alloc:
                return False, f"Falha ao registrar alocação: {msg_alloc}"

            ok_pay, msg_pay = self.blockchain.add_transaction(pay_tx)
            if not ok_pay:
                # Rollback: remove a alloc da mempool
                self.blockchain.pending_transactions = [
                    t for t in self.blockchain.pending_transactions
                    if t.get("tx_id") != alloc_tx_id
                ]
                return False, f"Falha no pagamento: {msg_pay}"

            return (
                True,
                f"Drone {drone_id} despachado. Missão {mission_id}. "
                f"alloc_tx={alloc_tx_id} pay_tx={pay_tx_id}",
            )

    # ── Conclusão de missão ────────────────────

    def complete_mission(self, drone_id: str, result: str, details: str = "") -> tuple[bool, str]:
        """
        Libera drone e registra laudo — ambos como transações no ledger.
        A liberação é um DRONE_RELEASE que referencia o alloc_tx ativo.
        """
        if drone_id not in DRONE_IDS:
            return False, f"Drone {drone_id} não existe"

        with self._lock:
            state = self._drone_state_from_ledger(drone_id)
            if state["status"] != "on_mission":
                return False, f"Drone {drone_id} não está em missão (ledger)"

            duration = round(time.time() - (state["start"] or time.time()), 1)
            release_tx_id = f"release_{drone_id}_{uuid.uuid4().hex[:8]}"
            log_tx_id     = f"log_{drone_id}_{uuid.uuid4().hex[:8]}"

            # Transação de liberação do drone
            release_tx = {
                "type":     "DRONE_RELEASE",
                "drone_id": drone_id,
                "alloc_tx": state["alloc_tx"],   # fecha o par ALLOC↔RELEASE
                "tx_id":    release_tx_id,
            }

            # Laudo imutável da missão
            log_tx = {
                "type":       "MISSION_LOG",
                "drone_id":   drone_id,
                "mission_id": state["mission_id"],
                "company":    state["assigned_to"],
                "route":      state["route"],
                "result":     result,
                "details":    details,
                "duration_s": duration,
                "alloc_tx":   state["alloc_tx"],
                "tx_id":      log_tx_id,
            }

            ok_r, msg_r = self.blockchain.add_transaction(release_tx)
            ok_l, msg_l = self.blockchain.add_mission_log(log_tx)

            if ok_r and ok_l:
                return True, f"Missão {state['mission_id']} concluída. Laudo registrado."
            return False, f"Erros: release={msg_r} | log={msg_l}"

    # ── Recarregar créditos ────────────────────

    def recharge_credits(self, company: str, amount: int) -> tuple[bool, str]:
        tx = {
            "type":   "PAYMENT",
            "from":   "FLEET_FUND",
            "to":     company,
            "amount": amount,
            "tx_id":  f"recharge_{company}_{uuid.uuid4().hex[:8]}",
            "note":   "Recarga de créditos operacionais",
        }
        return self.blockchain.add_transaction(tx)
