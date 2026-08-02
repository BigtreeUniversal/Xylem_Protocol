import os
import sys
import glob
import json
import base64
import asyncio
from nostr_sdk import (
    Client,
    Keys,
    EventBuilder,
    Tag,
    Kind
)

async def main():
    # 1. Dossier des fichiers .ots
    ots_dir = "./ots_downloaded"
    ots_files = glob.glob(os.path.join(ots_dir, "*.ots"))

    if not ots_files:
        print("❌ ERREUR : Aucun fichier .ots trouvé dans la plage requise.")
        sys.exit(1)

    # 2. Encodage Base64 / JSON
    bundle_data = {}
    for filepath in ots_files:
        filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            encoded_content = base64.b64encode(f.read()).decode('utf-8')
            bundle_data[filename] = encoded_content

    print(f"✅ Packagé {len(bundle_data)} fichiers .ots dans le bundle.")

    # 3. Chargement sécurisé de la clé privée (nsec ou Hex)
    raw_key = os.environ.get("NOSTR_PRIVATE_KEY", "").strip()
    if not raw_key:
        print("❌ ERREUR : Secret NOSTR_PRIVATE_KEY introuvable.")
        sys.exit(1)

    try:
        if raw_key.startswith("nsec"):
            keys = Keys.parse(raw_key)
        else:
            keys = Keys.parse(raw_key) # Keys.parse de nostr-sdk gère intelligemment Hex et Bech32
    except Exception as e:
        print(f"❌ ERREUR : Format de clé Nostr invalide ({e})")
        sys.exit(1)

    # 4. Initialisation du client et ajout des relais
    client = Client(keys)
    
    relays = [
        "wss://relay.damus.io",
        "wss://nos.lol",
        "wss://relay.nostr.band"
    ]
    for r in relays:
        await client.add_relay(r)

    # Connexion aux relais
    await client.connect()
    print("📡 Connecté aux relais Nostr.")

    # 5. Construction de l'événement avec les tags
    content_json = json.dumps(bundle_data)
    
    # Création des tags "t" (hashtags)
    tag_opentimestamps = Tag.parse(["t", "opentimestamps"])
    tag_xylem = Tag.parse(["t", "xylem"])

    # Kind 1 = Text Note
    builder = EventBuilder(Kind(1), content_json).tags([tag_opentimestamps, tag_xylem])

    # 6. Envoi garanti avec confirmation des relais
    try:
        # send_event envoie et ATTEND la confirmation des relais
        output = await client.send_event_builder(builder)
        print(f"✅ Événement envoyé avec succès ! Event ID: {output.id.to_hex()}")
    except Exception as e:
        print(f"❌ ERREUR lors de l'envoi sur Nostr : {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
    
