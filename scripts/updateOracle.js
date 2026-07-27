const { ethers } = require("ethers");

async function main() {
  // 1. Récupération et nettoyage de la clé privée
  let privateKey = process.env.OPERATOR_PRIVATE_KEY;
  const rpcUrl = process.env.RPC_URL || "https://mainnet.base.org";
  const contractAddress = process.env.CONTRACT_ADDRESS;

  if (!privateKey) throw new Error("OPERATOR_PRIVATE_KEY manquante");
  if (!contractAddress) throw new Error("CONTRACT_ADDRESS manquante");

  // Nettoyage : retire espaces, sauts de ligne et guillemets parasites
  privateKey = privateKey.trim().replace(/^["']|["']$/g, '');

  // Ajout automatique du préfixe 0x si absent
  if (!privateKey.startsWith("0x")) {
    privateKey = `0x${privateKey}`;
  }

  // 2. Initialisation Provider & Wallet
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const wallet = new ethers.Wallet(privateKey, provider);
  console.log(`🤖 Operator Wallet: ${wallet.address}`);

  // 3. ABI adapté à XylemOracle.sol
  const contractABI = [
    "function anchorDay(string calldata day, string calldata parentHash, string calldata currentHash, string[] calldata cids) external",
    "function ledger(string calldata day) external view returns (string parentHash, string currentHash, uint256 timestamp)"
  ];

  const oracleContract = new ethers.Contract(contractAddress, contractABI, wallet);

  // 4. Préparation des données du jour (Hier)
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const dayStr = yesterday.toISOString().split('T')[0]; // Format: "YYYY-MM-DD"

  // Valeurs par défaut/placeholders pour le test
  const parentHash = process.env.PARENT_HASH || "0x0000000000000000000000000000000000000000000000000000000000000000";
  const currentHash = process.env.CURRENT_HASH || "0x1111111111111111111111111111111111111111111111111111111111111111";
  
  // Tableau de 1 à 24 CIDs obligatoire selon le contrat
  const cids = [process.env.IPFS_CID || "QmPlaceholderCIDForDailyLog12345678901234567890"];

  console.log(`📌 Tentative d'ancrage pour le jour : ${dayStr}`);

  // 5. Exécution de la transaction
  const tx = await oracleContract.anchorDay(dayStr, parentHash, currentHash, cids);
  console.log(`🚀 Transaction envoyée sur Base ! Hash: ${tx.hash}`);

  const receipt = await tx.wait();
  console.log(`✅ Jour ${dayStr} ancré avec succès dans le bloc ${receipt.blockNumber} !`);
}

main().catch((error) => {
  console.error("❌ Erreur d'ancrage Oracle :", error);
  process.exit(1);
});
