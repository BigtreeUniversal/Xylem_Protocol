import os
import json
import re
import hashlib
from datetime import datetime, timezone, timedelta

# ==============================================================================
# CONFIGURATION REPERTOIRES ET FICHIERS
# ==============================================================================
BASE_DATA_DIR = "/root/xylem_node"
OUTPUT_DIR = "/root/xylem_data/public_html"
LAST_ROOT_FILE = "/root/xylem_data/last_root.txt"

def get_last_root():
    """Lit la racine scellée du jour précédent (64 caractéristiques SHA-256)."""
    if os.path.exists(LAST_ROOT_FILE):
        with open(LAST_ROOT_FILE, "r", encoding="utf-8") as f:
            val = f.read().strip()
            if len(val) == 64:
                return val
    return "0" * 64

def save_last_root(root):
    """Enregistre la nouvelle racine scellée calculée."""
    with open(LAST_ROOT_FILE, "w", encoding="utf-8") as f:
        f.write(root)

def compute_merkle_root(leaves):
    """
    Calcul standard et déterministe d'un Arbre de Merkle par paires (SHA-256).
    Si le nombre de feuilles est impair, la dernière feuille est dupliquée.
    """
    if not leaves:
        return "0" * 64
    
    current_level = list(leaves)
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i+1] if (i+1) < len(current_level) else left
            combined = left + right
            parent_hash = hashlib.sha256(combined.encode('utf-8')).hexdigest()
            next_level.append(parent_hash)
        current_level = next_level
    return current_level[0]

def build_registry():
    now_utc = datetime.now(timezone.utc)
    hier = now_utc - timedelta(days=1)
    hier_str = hier.strftime('%Y-%m-%d')
    avant_hier = now_utc - timedelta(days=2)

    # 🚨 SÉCURITÉ CRON / BÊTA-TEST : Empêche la double exécution le même jour
    file_name = f"page-{hier_str}.html"
    target_page_path = os.path.join(OUTPUT_DIR, file_name)

    if os.path.exists(target_page_path) and os.environ.get("FORCE_REGEN") != "1":
        print(f"[!] REGISTRE {hier_str} DÉJÀ EXISTANT ({file_name}). ABORT POUR PROTÉGER LA SÉQUENCE.")
        return

    # Fenêtre glissante exacte pour l'Oracle IPFS (23h50 J-2 à 23h50 J-1)
    debut_fenetre = datetime(avant_hier.year, avant_hier.month, avant_hier.day, 23, 50, 0, tzinfo=timezone.utc)
    fin_fenetre = datetime(hier.year, hier.month, hier.day, 23, 50, 0, tzinfo=timezone.utc)

    # ⚠️ OBLIGATOIRE : Initialisation des conteneurs pour éviter l'erreur NameError
    tx_leaves = []
    oracle_records = []
    oracle_leaves = []

    # --------------------------------------------------------------------------
    # 1. TRANSACTIONS UTILISATEURS (Strict Alignment avec Rust API & Client JS)
    # --------------------------------------------------------------------------
    transactions_hier_file = os.path.join(BASE_DATA_DIR, f"transactions_{hier_str}.txt")
    if os.path.exists(transactions_hier_file):
      with open(transactions_hier_file, "r", encoding="utf-8") as f:
        for line in f:
            line_clean = line.strip()
            if line_clean:
                parts = [p.strip() for p in line_clean.split('|')]
                if len(parts) >= 4:
                    # Extraction exacte des métadonnées originelles du serveur Rust
                    nano_time = parts[0]     # Ex: "2026-07-28T17:16:48.560574824Z"
                    uuid_tx = parts[1]       # Ex: "ticket_id" / UUID
                    pipeline_id = parts[2]   # Ex: "HEARTBEAT_01" ou "BUHS_L1_HTTPS"
                    file_sha256 = parts[3]   # Hash SHA-256 du fichier source

                    # Formule de Hachage Déterministe V1 (Miroir de computeV1Leaf du JS/Wasm)
                    raw_leaf_data = f"{nano_time}{uuid_tx}{pipeline_id}{file_sha256}"
                    leaf_hash = hashlib.sha256(raw_leaf_data.encode('utf-8')).hexdigest()

                    tx_leaves.append(leaf_hash)

    # --------------------------------------------------------------------------
    # 2. REGISTRE ORACLE IPFS (Fenêtre glissante 23h50 J-2 -> 23h50 J-1)
    # --------------------------------------------------------------------------
    log_cron_live = os.path.join(BASE_DATA_DIR, "log_cron.txt")
    if os.path.exists(log_cron_live):
        with open(log_cron_live, "r", encoding="utf-8") as f:
            for line in f:
                if "✅ IPFS CID LOCAL :" in line:
                    try:
                        json_part = line.split("✅ IPFS CID LOCAL :")[1].strip()
                        data = json.loads(json_part)
                        filename = data.get("Name", "")
                        cid = data.get("Hash", "")

                        if cid and filename:
                            ts_match = re.search(r"(\d{10,13})", filename)
                            if ts_match:
                                raw_ts = int(ts_match.group(1))
                                ts_sec = raw_ts / 1000.0 if raw_ts > 1e11 else float(raw_ts)
                                dt_event = datetime.fromtimestamp(ts_sec, tz=timezone.utc)

                                if debut_fenetre <= dt_event < fin_fenetre:
                                    oracle_records.append({
                                        "filename": filename,
                                        "cid": cid,
                                        "dt": dt_event,
                                        "time_str": dt_event.strftime('%Y-%m-%d %H:%M:%S UTC')
                                    })
                    except Exception:
                        continue

    # Tri déterministe de l'Oracle par ordre chronologique
    oracle_records.sort(key=lambda x: x["dt"])

    # Conversion des CIDs en Hash SHA-256 pour l'Arbre de Merkle (Homogénéité)
    for rec in oracle_records:
        cid_sha256 = hashlib.sha256(rec["cid"].encode('utf-8')).hexdigest()
        oracle_leaves.append(cid_sha256)

    # --------------------------------------------------------------------------
    # 3. CALCUL DU MERKLE ROOT ET SCELLEMENT DE CONTINUITÉ (PARENTHOOD)
    # --------------------------------------------------------------------------
    prev_root = get_last_root()

    # 1. Racine Merkle "pure" des données du jour (Tx Utilisateurs + Scans IPFS)
    day_leaves_sequence = tx_leaves + oracle_leaves
    day_merkle_root = compute_merkle_root(day_leaves_sequence)

    # 2. Scellement final liant le jour J au jour J-1 (Chainage cryptographique)
    sealed_data = f"{prev_root}{day_merkle_root}"
    sealed_root = hashlib.sha256(sealed_data.encode('utf-8')).hexdigest()

    # --------------------------------------------------------------------------
    # 4. EXPORTATION HTML ET SAUVEGARDE
    # --------------------------------------------------------------------------
    html_content = generate_clean_html(
        records=oracle_records, 
        current_day=hier_str, 
        day_merkle_root=day_merkle_root,
        prev_root=prev_root, 
        sealed_root=sealed_root,
        tx_count=len(tx_leaves),
        oracle_count=len(oracle_leaves),
        total_leaves=len(day_leaves_sequence)
    )

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    file_name = f"page-{hier_str}.html"
    with open(os.path.join(OUTPUT_DIR, file_name), "w", encoding="utf-8") as out:
        out.write(html_content)

    # Sauvegarde de la racine scellée pour servir de PARENT au script de demain
    save_last_root(sealed_root)

    print(f"[+] REGISTRE {hier_str} SCELLÉ AVEC SUCCÈS")
    print(f"    - Transactions Utilisateurs : {len(tx_leaves)}")
    print(f"    - Captures Oracle IPFS     : {len(oracle_leaves)}")
    print(f"    - Total Feuilles du jour   : {len(day_leaves_sequence)}")
    print(f"    - DAY MERKLE ROOT (J-1)    : {day_merkle_root}")
    print(f"    - PARENT ROOT (J-2)        : {prev_root}")
    print(f"    - FINAL SEALED ROOT        : {sealed_root}")

def generate_clean_html(records, current_day, day_merkle_root, prev_root, sealed_root, tx_count, oracle_count, total_leaves):
    rows_html = ""
    for r in records:
        rows_html += f"""
        <tr class="border-b border-emerald-900/40 hover:bg-emerald-500/5 text-sm font-mono">
            <td class="px-4 py-3 text-emerald-400 font-bold">{r['filename']}</td>
            <td class="px-4 py-3 text-emerald-300 break-all select-all">{r['cid']}</td>
            <td class="px-4 py-3 text-emerald-600">{r['time_str']}</td>
            <td class="px-4 py-3 text-emerald-400 font-bold">✅ OTS | IPFS_OK</td>
            <td class="px-4 py-3 text-right">
                <a href="https://ipfs.io/ipfs/{r['cid']}" target="_blank" rel="noopener noreferrer" class="brand-btn">OPEN</a>
            </td>
        </tr>
        """

    if not rows_html:
        rows_html = '<tr><td colspan="5" class="px-4 py-8 text-center text-emerald-700 italic">-- Aucun scan Oracle sur la période 23h50-23h50 --</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[ XYLEM TERMINAL ]</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background: #010402; color: #00ff66; font-family: monospace; }}
        .box {{ border: 1px solid #00cc55; background: rgba(0, 10, 3, 0.5); padding: 16px; margin-bottom: 24px; }}
        .brand-btn {{ border: 1px solid #00cc55; color: #00ff66; background: rgba(0,30,10,0.2); padding: 2px 10px; font-weight: bold; font-size: 12px; text-decoration: none; }}
        .brand-btn:hover {{ background: #00ff66; color: #010402; box-shadow: 0 0 8px #00ff66; }}
    </style>
</head>
<body class="p-8">
<div class="max-w-7xl mx-auto">

    <h1 class="text-xl font-bold mb-6 text-emerald-400" style="text-shadow: 0 0 6px rgba(0,255,102,0.3);">[ XYLEM TERMINAL ]</h1>
    
    <div class="box text-sm leading-relaxed">
        <p><span class="text-emerald-600">> DAY          :</span> <span class="text-white">{current_day}</span></p>
        <p><span class="text-emerald-600">> DAY MERKLE   :</span> <span class="text-white font-bold select-all">{day_merkle_root}</span></p>
        <p><span class="text-emerald-600">> PARENT ROOT  :</span> <span class="text-emerald-500 select-all">{prev_root}</span></p>
        <p><span class="text-emerald-600">> SEALED ROOT  :</span> <span class="text-emerald-300 font-bold select-all">{sealed_root}</span></p>
        <p><span class="text-emerald-600">> METRICS      :</span> <span class="text-emerald-400">{tx_count} Tx | {oracle_count} Oracle | Total {total_leaves} Leaves</span></p>
    </div>

    <div class="box overflow-x-auto !p-0">
        <table class="w-full text-left border-collapse">
            <thead>
                <tr class="border-b border-emerald-500 bg-emerald-950/20 text-xs text-emerald-400 font-bold uppercase tracking-wider">
                    <th class="px-4 py-3">ORACLE FILE</th>
                    <th class="px-4 py-3">CID IPFS</th>
                    <th class="px-4 py-3">TIMESTAMP (23H50-23H50)</th>
                    <th class="px-4 py-3">STATUS</th>
                    <th class="px-4 py-3 text-right">LINK</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>

</div>
</body>
</html>"""

if __name__ == "__main__":
    build_registry()
