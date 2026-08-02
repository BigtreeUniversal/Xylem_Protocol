import os
import sys
import glob
import json
import base64
from nostr.key import PrivateKey
from nostr.event import Event
from nostr.relay_manager import RelayManager

def main():
    # 1. Vérification du dossier contenant les .ots
    if len(sys.argv) < 2:
        print("Erreur: Veuillez spécifier le dossier contenant les fichiers .ots")
        sys.exit(1)
        
    ots_dir = sys.argv[1]
    ots_files = glob.glob(os.path.join(ots_dir, "*.ots"))
    
    if not ots_files:
        print(f"Aucun fichier .ots trouvé dans {ots_dir}")
        sys.exit(0)

    # 2. Emballage des 24 fichiers en Base64 dans un dictionnaire JSON
    bundle = {}
    for filepath in sorted(ots_files):
        filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
            bundle[filename] = encoded

    print(f"Packagé {len(bundle)} fichiers .ots dans le bundle.")

    # 3. Récupération de la clé privée depuis les secrets GitHub
    hex_private_key = os.environ.get("NOSTR_PRIVATE_KEY")
    if not hex_private_key:
        print("Erreur: La variable NOSTR_PRIVATE_KEY est introuvable.")
        sys.exit(1)

    # Si la clé commence par 'nsec', conversion ou utilisation de la clé brute
    if hex_private_key.startswith("nsec"):
        pk = PrivateKey.from_nsec(hex_private_key)
    else:
        pk = PrivateKey(bytes.fromhex(hex_private_key))

    # 4. Création de l'événement Nostr (Kind 1 - texte/données)
    event_content = json.dumps(bundle)
    event = Event(content=event_content, public_key=pk.public_key.hex())
    pk.sign_event(event)

    # 5. Envoi vers les relais publics Nostr
    relay_manager = RelayManager()
    relays = [
        "wss://relay.damus.io",
        "wss://nos.lol",
        "wss://relay.nostr.band"
    ]
    for r in relays:
        relay_manager.add_relay(r)

    relay_manager.open_connections()
    import time
    time.sleep(1.2) # Attente de la poignée de main SSH/WebSocket avec les relais
    
    relay_manager.publish_event(event)
    time.sleep(1.0)
    relay_manager.close_connections()

    print("✅ Publication du bundle OTS terminée avec succès sur Nostr !")

if __name__ == "__main__":
    main()
