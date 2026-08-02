import os
import glob
import json
import base64
import time
from nostr.key import PrivateKey
from nostr.event import Event
from nostr.relay_manager import RelayManager

def main():
    # 1. Dossier où sont stockés les .ots téléchargés
    ots_dir = "./ots_downloaded"
    ots_files = glob.glob(os.path.join(ots_dir, "*.ots"))

    if not ots_files:
        print("❌ Aucun fichier .ots trouvé.")
        return

    # 2. Emballage des fichiers .ots en JSON / Base64
    bundle_data = {}
    for filepath in ots_files:
        filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode('utf-8')
            bundle_data[filename] = encoded_content

    print(f"Packagé {len(bundle_data)} fichiers .ots dans le bundle.")

    # 3. Préparation de la clé et du message Nostr
    nsec_hex = os.environ.get("NOSTR_PRIVATE_KEY")
    if not nsec_hex:
        print("❌ Clé privée Nostr manquante (NOSTR_PRIVATE_KEY).")
        return

    # Chargement direct depuis le format hexadécimal brut
    private_key = PrivateKey(bytes.fromhex(nsec_hex))
    content_json = json.dumps(bundle_data)

    event = Event(
        content=content_json,
        public_key=private_key.public_key.hex(),
        kind=1,
        tags=[["t", "opentimestamps"], ["t", "xylem"]]
    )
    private_key.sign_event(event)

    # 4. Connexion aux relais Nostr
    relay_manager = RelayManager()
    relays = [
        "wss://relay.damus.io",
        "wss://nos.lol",
        "wss://relay.nostr.band"
    ]
    for r in relays:
        relay_manager.add_relay(r)

    # Pause de 4 secondes pour stabiliser la connexion réseau
    time.sleep(4.0)

    # 5. Envoi
    try:
        relay_manager.publish_event(event)
        time.sleep(2.0)
    except Exception as e:
        print(f"Note lors de l'envoi : {e}")
    finally:
        relay_manager.close_connections()

    print("✅ Publication du bundle OTS terminée avec succès sur Nostr !")

if __name__ == "__main__":
    main()
