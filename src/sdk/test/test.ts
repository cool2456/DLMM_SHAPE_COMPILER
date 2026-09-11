import { Connection, clusterApiUrl, PublicKey, Keypair } from "@solana/web3.js";
import { createMint, getOrCreateAssociatedTokenAccount, mintTo } from "@solana/spl-token";
import DLMM, {StrategyType} from "@meteora-ag/dlmm";
import * as fs from "fs";
import BN from "bn.js";
import Client from "../client";

//devnet pool stuff for testing
const walletData = JSON.parse(fs.readFileSync("./config/devnet_wallet.json", "utf-8"));
const wallet = Keypair.fromSecretKey(new Uint8Array(walletData["secretKey"]));

const connection = new Connection(clusterApiUrl('devnet'), 'confirmed');

const config = fs.readFileSync("./config/pool_config.json", "utf-8");
const pool_address = JSON.parse(config)["poolAddress"];

console.log(pool_address);

const client = new Client(connection, wallet);

async function main(){
    const accountInfo = await connection.getAccountInfo(new PublicKey(pool_address));
    console.log("Pool account info:", accountInfo);

    const pool_info = await client.getActiveBin(pool_address);
    console.log("Active bin info:", pool_info);

    const strategy = await client.createStrategy(StrategyType.Spot, pool_info.binId - 10, pool_info.binId + 10);

    //client.createPosition(pool_address, new BN(10_000_000_000), new BN(10_000_000), strategy, 1)
    await client.removeLiquidity(pool_address, "97Xe2ZdEEQFp2xct8sbRSPu58ShBjTp8TpCmGoqUAGMo", -10, 10, new BN(10000), true);
}

main();

// To run tests: ts-node ./src/sdk/test.ts
//97Xe2ZdEEQFp2xct8sbRSPu58ShBjTp8TpCmGoqUAGMo devnet position