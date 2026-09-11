import {Connection, clusterApiUrl, PublicKey, Keypair, sendAndConfirmTransaction} from "@solana/web3.js";
import DLMM, { BinLiquidity, LbPairAccount, PositionInfo, LbPosition, StrategyParameters, StrategyType} from "@meteora-ag/dlmm"
import BN from "bn.js";

async function checkConnection(): Promise<void> {
    const connection = new Connection(clusterApiUrl('devnet'), 'confirmed');

    const version = await connection.getVersion();
    console.log("Solana Cluster version:", version);

    const slot = await connection.getSlot();
    console.log("Current slot:", slot);

}

checkConnection().catch(err => {
    console.error("Error connecting to Solana cluster:", err);
});

// To check connection run `ts-node ./src/sdk/client.ts`

class Client {
    connection: Connection;
    wallet: Keypair;

    constructor(connection: Connection, wallet: Keypair) {
        this.connection = connection;
        this.wallet = wallet;
    }

    get address(): PublicKey {
        return this.wallet.publicKey;
    }

    async load(poolAddress: string): Promise<DLMM> {
        const pk = new PublicKey(poolAddress);
        const dlmm = await DLMM.create(this.connection, pk);
        return dlmm;
    }

    async getActiveBin(poolAddress: string): Promise<BinLiquidity> {
        const dlmm = await this.load(poolAddress);
        const activeBin = await dlmm.getActiveBin();
        return activeBin;
    }

    async getAllLbPairPositionsByUser(connection: Connection, usrPubKey: PublicKey): Promise<Map<string, PositionInfo>> {
        const lbPairs = await DLMM.getAllLbPairPositionsByUser(connection, usrPubKey);
        return lbPairs;
    }

    async getPosition(pool_address: string, positionAddress: string): Promise<LbPosition> {
        const dlmm = await this.load(pool_address);
        const position = await dlmm.getPosition(new PublicKey(positionAddress));
        return position;
    }

    async createStrategy(strategyType: StrategyType, minBinId: number, maxBinId: number) {
        return {strategyType: strategyType, minBinId: minBinId, maxBinId: maxBinId};
    }

    async createPosition(pool_address: string, totalXAmount: BN, totalYAmount: BN, strategy: StrategyParameters, slippage?: number): Promise<string> {
        const dlmm = await this.load(pool_address);

        const positionKeyPair = Keypair.generate();

        console.log("Creating position with parameters:")
        console.log("Total X Amount:", totalXAmount.toString());
        console.log("Total Y Amount:", totalYAmount.toString());
        console.log("Strategy:", strategy);
        console.log("Slippage:", slippage);

        const tx = await dlmm.initializePositionAndAddLiquidityByStrategy({
            positionPubKey: positionKeyPair.publicKey,
            totalXAmount: totalXAmount,
            totalYAmount: totalYAmount,
            strategy: strategy,
            user: this.wallet.publicKey,
            slippage: slippage
        });

        const signature = await sendAndConfirmTransaction(
            this.connection,
            tx,
            [this.wallet, positionKeyPair]
        );

        console.log("Position created: ", positionKeyPair.publicKey.toBase58());
        console.log("Transaction signature: ", signature);
        
        return positionKeyPair.publicKey.toBase58();
    }

    async claimAllRewardsByPosition(pool_address: string,positionAddress: string): Promise<void> {
        const dlmm = await this.load(pool_address);

        const position = await this.getPosition(pool_address, positionAddress);
        const txs = await dlmm.claimAllRewardsByPosition({
            owner: this.wallet.publicKey,
            position: position
        });

        for (const tx of txs) {
            const signature = await sendAndConfirmTransaction(
                this.connection,
                tx,
                [this.wallet]
            );
            console.log("Rewards claimed. Transaction signature: ", signature);
        }

    }

    async closePosition(pool_address: string, positionAddress: string): Promise<void> {
        //position must be empty before closing
        const dlmm = await this.load(pool_address);

        const position = await this.getPosition(pool_address, positionAddress);
        const tx = await dlmm.closePosition({
            owner: this.wallet.publicKey,
            position: position
        });

        const signature = await sendAndConfirmTransaction(
            this.connection,
            tx,
            [this.wallet]
        );
        console.log("Position closed. Transaction signature: ", signature);
    }

    async removeLiquidity(pool_address: string, position_address: string, from: number, to: number, bps: BN, shouldClaimAndClose: boolean): Promise<void> {
        const dlmm = await this.load(pool_address);

        const txs = await dlmm.removeLiquidity({user: this.wallet.publicKey, position: new PublicKey(position_address), fromBinId: from, toBinId: to, bps: bps, shouldClaimAndClose: shouldClaimAndClose});

        for (const tx of txs) {
            const signature = await sendAndConfirmTransaction(
                this.connection,
                tx,
                [this.wallet]
            );
            console.log("Liquidity removed. Transaction signature: ", signature);
        }
    }

}

export default Client;
