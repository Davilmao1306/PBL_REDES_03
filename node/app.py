"""
Nó da Rede P2P - Estreito de Ormuz
Cada computador no laboratório executa este arquivo como um nó independente.
Comunicação via HTTP entre nós (simples, robusto para LAN).
"""

import argparse
import json
import threading
import time
import uuid
import os

import requests
from flask import Flask, jsonify, request, render_template

# Adiciona o diretório pai ao path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blockchain.chain import Blockchain
from blockchain.drones import DroneManager

# ──────────────────────────────────────────────
# Inicialização
# ──────────────────────────────────────────────

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"),
    static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"),
)

blockchain = Blockchain()
drone_manager = DroneManager(blockchain)

# Conjunto de peers conhecidos: {"http://192.168.1.10:5000", ...}
peers: set = set()

NODE_ID = str(uuid.uuid4())[:8]   # identificador curto deste nó

# ──────────────────────────────────────────────
# Helpers de broadcast
# ──────────────────────────────────────────────

def broadcast(endpoint: str, data: dict, exclude_self_port: int = None):
    """Envia POST para todos os peers conhecidos (fire-and-forget)."""
    for peer in list(peers):
        try:
            requests.post(f"{peer}{endpoint}", json=data, timeout=3)
        except Exception:
            pass   # peer offline — ignoramos


def sync_chain_from_peers():
    """Consulta todos os peers e substitui cadeia se houver uma mais longa válida."""
    longest = blockchain.to_list()
    for peer in list(peers):
        try:
            resp = requests.get(f"{peer}/chain", timeout=3)
            if resp.status_code == 200:
                data = resp.json()["chain"]
                if len(data) > len(longest):
                    longest = data
        except Exception:
            pass

    if len(longest) > len(blockchain.chain):
        replaced = blockchain.replace_chain(longest)
        return replaced
    return False


# ──────────────────────────────────────────────
# Rotas: Cadeia & Nós
# ──────────────────────────────────────────────

@app.route("/chain", methods=["GET"])
def get_chain():
    """Retorna a blockchain completa deste nó."""
    return jsonify({
        "node_id": NODE_ID,
        "chain": blockchain.to_list(),
        "length": blockchain.length(),
        "is_valid": blockchain.is_valid(),
        "peers": list(peers),
    })


@app.route("/nodes/register", methods=["POST"])
def register_node():
    """Registra um ou mais peers."""
    data = request.get_json()
    nodes = data.get("nodes", [])
    if not nodes:
        return jsonify({"error": "Forneça lista 'nodes'"}), 400

    for node in nodes:
        peers.add(node.rstrip("/"))

    return jsonify({
        "message": f"{len(nodes)} nó(s) registrado(s)",
        "total_peers": list(peers),
    }), 201


@app.route("/nodes/list", methods=["GET"])
def list_nodes():
    return jsonify({"node_id": NODE_ID, "peers": list(peers)})


@app.route("/nodes/sync", methods=["POST"])
def sync():
    """Força sincronização com peers (regra da cadeia mais longa)."""
    replaced = sync_chain_from_peers()
    return jsonify({
        "replaced": replaced,
        "chain_length": blockchain.length(),
    })


# Peer se auto-anuncia quando entra na rede
@app.route("/nodes/announce", methods=["POST"])
def announce():
    """Peer anuncia sua existência — registramos e devolvemos nossa lista."""
    data = request.get_json()
    new_peer = data.get("address")
    if new_peer:
        peers.add(new_peer.rstrip("/"))
    return jsonify({"peers": list(peers), "chain_length": blockchain.length()}), 200


# ──────────────────────────────────────────────
# Rotas: Mineração
# ──────────────────────────────────────────────

@app.route("/mine", methods=["POST"])
def mine():
    """Minera um bloco com todas as transações pendentes."""
    block = blockchain.mine_pending(miner_node=NODE_ID)
    if block is None:
        return jsonify({"message": "Nenhuma transação pendente para minerar"}), 200

    # Propaga o novo bloco para todos os peers
    broadcast("/blocks/new", {"block": block.to_dict()})

    return jsonify({
        "message": "Bloco minerado com sucesso",
        "block": block.to_dict(),
    }), 201


@app.route("/blocks/new", methods=["POST"])
def receive_block():
    """
    Recebe bloco de outro nó.
    Verifica se encadeia corretamente; se não, sincroniza a cadeia inteira.
    """
    data = request.get_json()
    block_data = data.get("block")
    if not block_data:
        return jsonify({"error": "Bloco não fornecido"}), 400

    from blockchain.chain import Block
    new_block = Block.from_dict(block_data)

    last = blockchain.last_block
    prefix = "0" * blockchain.__class__.__dict__.get("DIFFICULTY", 3)

    # Verifica se o bloco encadeia com o último
    if (
        new_block.previous_hash == last.hash
        and new_block.hash == new_block.compute_hash()
        and new_block.hash.startswith("0" * 3)
    ):
        blockchain.chain.append(new_block)
        # Remove transações já confirmadas da mempool
        confirmed = blockchain.confirmed_tx_ids()
        blockchain.pending_transactions = [
            t for t in blockchain.pending_transactions
            if t.get("tx_id") not in confirmed
        ]
        return jsonify({"message": "Bloco aceito"}), 200
    else:
        # Cadeia diverge — pede a cadeia completa dos peers
        sync_chain_from_peers()
        return jsonify({"message": "Cadeia sincronizada"}), 200


# ──────────────────────────────────────────────
# Rotas: Transações
# ──────────────────────────────────────────────

@app.route("/transactions/pending", methods=["GET"])
def pending_txs():
    return jsonify({"pending": blockchain.pending_transactions})


@app.route("/transactions/new", methods=["POST"])
def new_transaction():
    """Adiciona transação manual (transferência de créditos entre empresas)."""
    data = request.get_json()
    required = ["type", "from", "to", "amount"]
    if not all(k in data for k in required):
        return jsonify({"error": f"Campos obrigatórios: {required}"}), 400

    if "tx_id" not in data:
        data["tx_id"] = f"tx_{uuid.uuid4().hex[:12]}"

    ok, msg = blockchain.add_transaction(data)
    if not ok:
        return jsonify({"error": msg}), 400

    # Propaga para peers
    broadcast("/transactions/receive", {"transaction": data})

    return jsonify({"message": msg, "tx_id": data["tx_id"]}), 201


@app.route("/transactions/receive", methods=["POST"])
def receive_transaction():
    """Recebe transação propagada por outro nó."""
    data = request.get_json()
    tx = data.get("transaction")
    if not tx:
        return jsonify({"error": "Transação não fornecida"}), 400

    ok, msg = blockchain.add_transaction(tx)
    return jsonify({"accepted": ok, "message": msg}), 200 if ok else 409


# ──────────────────────────────────────────────
# Rotas: Saldos e Auditoria
# ──────────────────────────────────────────────

@app.route("/balances", methods=["GET"])
def balances():
    """Retorna saldos derivados do ledger (nunca de variável local)."""
    return jsonify({
        "node_id": NODE_ID,
        "balances": blockchain.all_balances(),
        "derived_from_ledger": True,
    })


@app.route("/balance/<company>", methods=["GET"])
def balance(company):
    return jsonify({
        "company": company,
        "balance": blockchain.get_balance(company),
    })


@app.route("/logs", methods=["GET"])
def mission_logs():
    """Retorna todos os laudos de missão registrados no ledger."""
    return jsonify({
        "mission_logs": blockchain.get_mission_logs(),
        "total": len(blockchain.get_mission_logs()),
    })


@app.route("/payments", methods=["GET"])
def payments():
    return jsonify({"payments": blockchain.get_payments()})


@app.route("/audit/validate", methods=["GET"])
def audit_validate():
    """Auditoria: verifica integridade da cadeia deste nó."""
    valid = blockchain.is_valid()
    return jsonify({
        "node_id": NODE_ID,
        "chain_valid": valid,
        "chain_length": blockchain.length(),
        "last_hash": blockchain.last_block.hash,
    })


# ──────────────────────────────────────────────
# Rotas: Drones
# ──────────────────────────────────────────────

@app.route("/drones", methods=["GET"])
def list_drones():
    return jsonify({"drones": drone_manager.list_drones()})


@app.route("/drones/request", methods=["POST"])
def request_drone():
    """
    Requisita drone para escolta.
    Body: {"company": "AlphaShipping", "drone_id": "DRONE-01", "route": "Canal-Norte"}
    """
    data = request.get_json()
    company = data.get("company")
    drone_id = data.get("drone_id")
    route = data.get("route", "Rota desconhecida")

    if not company or not drone_id:
        return jsonify({"error": "Campos obrigatórios: company, drone_id"}), 400

    ok, msg = drone_manager.request_escort(company, drone_id, route)
    if not ok:
        return jsonify({"error": msg}), 400

    # Propaga DRONE_ALLOC + PAYMENT para todos os peers (últimas 2 txs inseridas).
    # Isso permite que outros nós atualizem sua visão do ledger e rejeitem
    # qualquer alocação duplicada antes mesmo de minerar.
    for tx in list(blockchain.pending_transactions)[-2:]:
        broadcast("/transactions/receive", {"transaction": tx})

    return jsonify({"message": msg}), 200


@app.route("/drones/complete", methods=["POST"])
def complete_drone():
    """
    Conclui missão e registra laudo.
    Body: {"drone_id": "DRONE-01", "result": "ROTA_SEGURA", "details": "..."}
    """
    data = request.get_json()
    drone_id = data.get("drone_id")
    result = data.get("result", "MISSAO_CONCLUIDA")
    details = data.get("details", "")

    if not drone_id:
        return jsonify({"error": "Campo obrigatório: drone_id"}), 400

    ok, msg = drone_manager.complete_mission(drone_id, result, details)
    if not ok:
        return jsonify({"error": msg}), 400

    # Propaga DRONE_RELEASE + MISSION_LOG para todos os peers (últimas 2 txs).
    for tx in list(blockchain.pending_transactions)[-2:]:
        broadcast("/transactions/receive", {"transaction": tx})

    return jsonify({"message": msg}), 200


# ──────────────────────────────────────────────
# Interface Web
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", node_id=NODE_ID)


# ──────────────────────────────────────────────
# Auto-mineração periódica (opcional)
# ──────────────────────────────────────────────

def auto_mine_loop(interval: int = 15):
    """A cada N segundos, minera as pendentes automaticamente."""
    while True:
        time.sleep(interval)
        if blockchain.pending_transactions:
            block = blockchain.mine_pending(NODE_ID)
            if block:
                broadcast("/blocks/new", {"block": block.to_dict()})
                print(f"[AUTO-MINE] Bloco #{block.index} minerado — {len(block.transactions)} txs")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nó Blockchain — Estreito de Ormuz")
    parser.add_argument("--port", type=int, default=5000, help="Porta deste nó")
    parser.add_argument(
        "--peers",
        nargs="*",
        default=[],
        help='Endereços de peers iniciais, ex: --peers http://192.168.1.10:5000',
    )
    parser.add_argument(
        "--automine",
        action="store_true",
        help="Ativa mineração automática a cada 15 segundos",
    )
    args = parser.parse_args()

    # Registrar peers iniciais
    for p in args.peers:
        peers.add(p.rstrip("/"))

    # Anunciar para peers e sincronizar cadeia
    my_address = f"http://0.0.0.0:{args.port}"
    for peer in list(peers):
        try:
            resp = requests.post(
                f"{peer}/nodes/announce",
                json={"address": f"http://{get_local_ip()}:{args.port}"},
                timeout=3,
            )
            if resp.status_code == 200:
                data = resp.json()
                for p in data.get("peers", []):
                    peers.add(p)
        except Exception:
            pass

    sync_chain_from_peers()

    # Auto-mineração em background
    if args.automine:
        t = threading.Thread(target=auto_mine_loop, daemon=True)
        t.start()
        print(f"[AUTO-MINE] Ativo — minerando a cada 15 segundos")

    print(f"\n{'='*55}")
    print(f"  NODO ORMUZ  |  ID: {NODE_ID}  |  Porta: {args.port}")
    print(f"  Peers: {list(peers) or 'nenhum'}")
    print(f"  Interface: http://localhost:{args.port}/")
    print(f"{'='*55}\n")

    app.run(host="0.0.0.0", port=args.port, debug=False)


def get_local_ip():
    """Obtém IP local da máquina."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nó Blockchain — Estreito de Ormuz")
