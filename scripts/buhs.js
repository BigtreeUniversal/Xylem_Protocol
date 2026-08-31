#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const http = require('http');
const https = require('https');

// Configuration du pipeline
const PIPELINE_ID = "HEARTBEAT_01";
const SUISSE_URL = "http://83.228.222.219:3000/api/v1/stamp";
const TOKEN = "Bearer BUHS_SECURE_TOKEN_2026";

// Couleurs ANSI
const COLORS = {
    reset: "\x1b[0m",
    green: "\x1b[32m",
    cyan: "\x1b[36m",
    yellow: "\x1b[33m",
    red: "\x1b[31m",
    gray: "\x1b[90m",
    bold: "\x1b[1m"
};

// Bannière ASCII
const BANNER = `${COLORS.green}${COLORS.bold}
██████╗ ██╗   ██╗██╗  ██╗███████╗
██╔══██╗██║   ██║██║  ██║██╔════╝
██████╔╝██║   ██║███████║███████╗
██╔══██╗██║   ██║██╔══██║╚════██║
██████╔╝╚██████╔╝██║  ██║███████║
╚══════╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝

--- UNIVERSAL HARMONIC SYSTEM ---
${COLORS.reset}`;

// Extraction des arguments CLI
const args = process.argv.slice(2);
let ipfsPort = process.env.IPFS_PORT || "5001";
let filePath = null;

for (let i = 0; i < args.length; i++) {
    if (args[i] === '--port' || args[i] === '-p') {
        ipfsPort = args[i + 1];
        i++;
    } else if (!args[i].startsWith('-')) {
        filePath = args[i];
    }
}

if (!filePath) {
    console.log(BANNER);
    console.log(`${COLORS.yellow}Usage :${COLORS.reset} buhs <nom_du_fichier> [--port 5001]`);
    console.log(`${COLORS.gray}Exemple: buhs image.png --port 5001${COLORS.reset}\n`);
    process.exit(1);
}

const resolvedPath = path.resolve(filePath);

if (!fs.existsSync(resolvedPath)) {
    console.error(`${COLORS.red}Erreur: Le fichier "${filePath}" n'existe pas.${COLORS.reset}`);
    process.exit(1);
}

// Helper: Calcul SHA-256 en stream
function computeFileSHA256(file) {
    return new Promise((resolve, reject) => {
        const hash = crypto.createHash('sha256');
        const stream = fs.createReadStream(file);
        stream.on('data', data => hash.update(data));
        stream.on('end', () => resolve(hash.digest('hex')));
        stream.on('error', err => reject(err));
    });
}

// Helper: Calcul déterministe de la feuille V1
function computeV1Leaf(nanoTime, uuidTx, pipelineId, fileSha256) {
    const rawLeafData = `${nanoTime}${uuidTx}${pipelineId}${fileSha256}`;
    return crypto.createHash('sha256').update(rawLeafData, 'utf8').digest('hex');
}

// Helper: Envoi Multipart au nœud local IPFS
function uploadToLocalIPFS(file, port) {
    return new Promise((resolve, reject) => {
        const boundary = '----BUHSBoundary' + Math.random().toString(16).substring(2);
        const fileName = path.basename(file);
        const fileStream = fs.createReadStream(file);

        const header = `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${fileName}"\r\nContent-Type: application/octet-stream\r\n\r\n`;
        const footer = `\r\n--${boundary}--\r\n`;

        const stat = fs.statSync(file);
        const contentLength = Buffer.byteLength(header) + stat.size + Buffer.byteLength(footer);

        const req = http.request({
            hostname: '127.0.0.1',
            port: parseInt(port),
            path: '/api/v0/add?pin=true',
            method: 'POST',
            headers: {
                'Content-Type': `multipart/form-data; boundary=${boundary}`,
                'Content-Length': contentLength
            }
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                if (res.statusCode >= 200 && res.statusCode < 300) {
                    try {
                        const json = JSON.parse(data);
                        resolve(json.Hash);
                    } catch (e) {
                        reject(new Error("Réponse JSON invalide reçue de l'API IPFS."));
                    }
                } else {
                    reject(new Error(`Code HTTP ${res.statusCode} renvoyé par IPFS.`));
                }
            });
        });

        req.on('error', (err) => {
            reject(new Error(`Connexion impossible sur http://127.0.0.1:${port} (${err.message})`));
        });

        req.write(header);
        fileStream.on('data', chunk => req.write(chunk));
        fileStream.on('end', () => {
            req.write(footer);
            req.end();
        });
    });
}

// Helper: Requéteur HTTPS pour l'ancrage
function anchorToServer(sha256Hash) {
    return new Promise((resolve, reject) => {
        const payload = JSON.stringify({
            client_id: PIPELINE_ID,
            payload_hash: sha256Hash
        });

        const urlParts = new URL(SUISSE_URL);
        const client = urlParts.protocol === 'https:' ? https : http;

        const req = client.request({
            hostname: urlParts.hostname,
            port: urlParts.port || (urlParts.protocol === 'https:' ? 443 : 80),
            path: urlParts.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': TOKEN,
                'Content-Length': Buffer.byteLength(payload)
            }
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                if (res.statusCode >= 200 && res.statusCode < 300) {
                    try {
                        resolve(JSON.parse(data));
                    } catch (e) {
                        reject(new Error("Réponse serveur malformée."));
                    }
                } else {
                    reject(new Error(`Erreur serveur HTTP ${res.statusCode}`));
                }
            });
        });

        req.on('error', err => reject(err));
        req.write(payload);
        req.end();
    });
}

// Moteur principal
async function main() {
    console.log(BANNER);
    const stats = fs.statSync(resolvedPath);
    console.log(`${COLORS.cyan}[1/4] Lecture du fichier :${COLORS.reset} ${path.basename(resolvedPath)} (${stats.size} octets)`);

    // 1. Calcul SHA-256
    const sha256 = await computeFileSHA256(resolvedPath);
    console.log(`      ${COLORS.gray}SHA-256 : ${sha256}${COLORS.reset}`);

    // 2. Publication IPFS
    console.log(`${COLORS.cyan}[2/4] Publication sur le nœud IPFS local (port ${ipfsPort})...${COLORS.reset}`);
    let cid = "N/A";
    try {
        cid = await uploadToLocalIPFS(resolvedPath, ipfsPort);
        console.log(`      ${COLORS.green}✔ CID IPFS : ${cid}${COLORS.reset}`);
    } catch (err) {
        console.log(`      ${COLORS.red}❌ Erreur IPFS : ${err.message}${COLORS.reset}`);
        console.log(`      ${COLORS.gray}Continuation de l'ancrage sans publication IPFS...${COLORS.reset}`);
    }

    // 3. Ancrage Serveur
    console.log(`${COLORS.cyan}[3/4] Ancrage immuable vers le nœud ${PIPELINE_ID}...${COLORS.reset}`);
    try {
        const serverData = await anchorToServer(sha256);
        const uuidTx = serverData.ticket_id;
        const timestampStr = serverData.timestamp;

        const leafHash = computeV1Leaf(timestampStr, uuidTx, PIPELINE_ID, sha256);

        console.log(`      ${COLORS.green}✔ Horodatage Strate 1 Validé${COLORS.reset}`);
        console.log(`      Ticket UUID : ${COLORS.bold}${uuidTx}${COLORS.reset}`);
        console.log(`      Chrony UTC  : ${timestampStr}`);

        // 4. Génération de la Preuve (.buhs)
        const proofReceipt = {
            schema: "V1_SOVEREIGN",
            pipeline_id: PIPELINE_ID,
            file_name: path.basename(resolvedPath),
            file_size: stats.size,
            file_sha256: sha256,
            ipfs_cid: cid,
            transaction: {
                nano_time: timestampStr,
                uuid: uuidTx,
                leaf_hash: leafHash
            },
            anchored_at: new Date().toISOString()
        };

        const proofFileName = `${resolvedPath}.buhs`;
        fs.writeFileSync(proofFileName, JSON.stringify(proofReceipt, null, 2));
        console.log(`${COLORS.cyan}[4/4] Preuve générée avec succès :${COLORS.reset}`);
        console.log(`      ${COLORS.green}📄 ${proofFileName}${COLORS.reset}\n`);

    } catch (err) {
        console.error(`\n${COLORS.red}🚨 ÉCHEC DE L'ANCRAGE : ${err.message}${COLORS.reset}\n`);
        process.exit(1);
    }
}

main();
