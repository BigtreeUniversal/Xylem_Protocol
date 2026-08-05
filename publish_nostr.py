import os
import sys
import glob
import json
import base64
import asyncio
from nostr_sdk import Client, Keys, EventBuilder, Tag, Kind, NostrSigner, RelayUrl

async def main():
    ots_dir = "./ots_downloaded"
    ots_files = glob.glob(os.path.join(ots_dir, "*.ots"))

    if not ots_files:
        print("❌ ERREUR : Aucun fichier .ots trouvé.")
        sys.exit(1)

    # 1. Charger la carte des CIDs depuis l'index extrait du log_cron.txt
    cid_map = {}
    if os.path.exists("ipfs_index.jsonl"):
        with open("ipfs_index.jsonl", "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line.strip())
                    cid_map[data["Name"]] = data["Hash"]

    # 2. Construction du bundle enrichi
    bundle_data = {}
    for filepath in ots_files:
        filename = os.path.basename(filepath)
        img_name = filename.replace(".ots", "")
        
        with open(filepath, "rb") as f:
            encoded_ots = base64.b64encode(f.read()).decode('utf-8')
            
        bundle_data[img_name] = {
            "ots": encoded_ots,
            "cid": cid_map.get(img_name, None)
        }

    print(f"✅ Packagé {len(bundle_data)} Trônes avec leurs CIDs IPFS et OTS.")

    # 3. Configuration Nostr (Signer & Keys)
    raw_key = os.environ.get("NOSTR_PRIVATE_KEY", "").strip()
    if not raw_key:
        print("❌ Secret NOSTR_PRIVATE_KEY manquant.")
        sys.exit(1)

    try:
        # Parsing universel de la clé (nsec... ou hex)
        keys = Keys.parse(raw_key)

        # On passe directement la clé au Client
        client = Client(keys)

    except Exception as e:
        print(f"❌ ERREUR d'initialisation des clés Nostr : {e}")
        sys.exit(1)
    
    # Correction du typage strict avec RelayUrl.parse()
    relays = ["wss://relay.damus.io", "wss://nos.lol", "wss://relay.nostr.band"]
    for r in relays:
        await client.add_relay(RelayUrl.parse(r))

    await client.connect()

    # 4. Envoi de l'événement avec les tags d'indexation
    content_json = json.dumps(bundle_data)
    tags = [
        Tag.parse(["t", "opentimestamps"]),
        Tag.parse(["t", "xylem"]),
        Tag.parse(["t", "buhs_oracle"])
    ]

    builder = EventBuilder(Kind(1), content_json).tags(tags)

    try:
        output = await client.send_event_builder(builder)
        print(f"✅ 24 Trônes Binah publiés sur Nostr ! Event ID: {output.id.to_hex()}")
    except Exception as e:
        print(f"❌ ERREUR d'envoi Nostr : {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
