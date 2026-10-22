const fs = require("fs");
const { ethers } = require("ethers");

async function main() {
  let privateKey = process.env.OPERATOR_PRIVATE_KEY;
  const rpcUrl = process.env.RPC_URL || "https://mainnet.base.org";
  const contractAddress = process.env.CONTRACT_ADDRESS;

  if (!privateKey) throw new Error("OPERATOR_PRIVATE_KEY manquante dans l'environnement");
  if (!contractAddress) throw new Error("CONTRACT_ADDRESS manquante dans l'environnement");

  // Nettoyage sécurisé de la clé privée
  privateKey = privateKey.trim().replace(/^["']|["']$/g, '');
  if (!privateKey.startsWith("0x")) privateKey = `0x${privateKey}`;

  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const wallet = new ethers.Wallet(privateKey, provider);
  console.log(`🤖 Operator Wallet: ${wallet.address}`);

  // 1. Détermination du jour et du fichier cible (reçu de GitHub Actions)
  const dayStr = process.env.TARGET_DAY || (() => {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().split('T')[0];
  })();

  const fileName = process.env.TARGET_FILE || `page-${dayStr}.html`;
  console.log(`📄 Analyse du fichier : ${fileName} (Jour cible : ${dayStr})`);

  if (!fs.existsSync(fileName)) {
    throw new Error(`Fichier HTML introuvable : ${fileName}`);
  }

  const htmlContent = fs.readFileSync(fileName, "utf8");

  // 2. Extraction stricte des hachages PARENT ROOT (H_t-1) et SEALED ROOT (H_t)
  const parentMatch = htmlContent.match(/PARENT ROOT\s*:\s*<\/span>\s*<span[^>]*>([a-fA-F0-9]{64})<\/span>/);
  const sealedMatch = htmlContent.match(/SEALED ROOT\s*:\s*<\/span>\s*<span[^>]*>([a-fA-F0-9]{64})<\/span>/);

  if (!parentMatch || !sealedMatch) {
    throw new Error("Impossible d'extraire PARENT ROOT ou SEALED ROOT depuis le HTML !");
  }

  const parentHash = parentMatch[1];
  const currentHash = sealedMatch[1];

  // 3. Extraction stricte des CIDs IPFS (Nœud dédié: format Qm... v0)
  const cidRegex = /ipfs\.io\/ipfs\/(Qm[a-zA-Z0-9]{44})/g;
  const cids = [];
  let match;
  while ((match = cidRegex.exec(htmlContent)) !== null) {
    if (!cids.includes(match[1])) {
      cids.push(match[1]);
    }
  }

  console.log(`📌 Résumé des données pour ${dayStr} :`);
  console.log(`   - Parent Root (H_t-1) : ${parentHash}`);
  console.log(`   - Sealed Root (H_t)   : ${currentHash}`);
  console.log(`   - CIDs IPFS trouvés   : ${cids.length}`);

  if (cids.length < 1 || cids.length > 24) {
    throw new Error(`Nombre de CIDs invalide : ${cids.length} (attendu : 1 à 24)`);
  }

  // 4. Interaction avec XylemOracle.sol
  const contractABI = [
    "function anchorDay(string calldata day, string calldata parentHash, string calldata currentHash, string[] calldata cids) external",
    "function ledger(string calldata day) external view returns (string parentHash, string currentHash, uint256 timestamp)"
  ];

  const oracleContract = new ethers.Contract(contractAddress, contractABI, wallet);

  // 5. Envoi de la transaction
  console.log(`🚀 Soumission de l'ancrage sur la blockchain Base...`);
  const tx = await oracleContract.anchorDay(dayStr, parentHash, currentHash, cids);
  console.log(`⏳ En attente de validation (TX Hash: ${tx.hash})...`);

  const receipt = await tx.wait();
  console.log(`✅ Succès ! Jour ${dayStr} ancré dans le bloc n° ${receipt.blockNumber}`);
}

main().catch((error) => {
  console.error("❌ Erreur critique lors de l'exécution :", error.message);
  process.exit(1); // Arrête le workflow GitHub Actions pour empêcher le push
});
