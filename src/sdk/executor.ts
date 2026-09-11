import { Connection, PublicKey, Keypair, clusterApiUrl } from "@solana/web3.js";
import { StrategyType } from "@meteora-ag/dlmm";
import BN from "bn.js";
import * as fs from "fs";
import * as readline from "readline";
import * as dotenv from "dotenv";
import bs58 from "bs58";
import Client from "./client";

// Load environment variables
dotenv.config();

/**
 * Strategy plan interface - matches Python export format
 */
export interface StrategyPlan {
    version: string;
    generated_at: string;
    metrics: {
        r_squared: number;
        residual: number;
        truncated: boolean;
        full_r_squared: number;
    };
    strategies: Array<{
        type: "rectangle" | "curve" | "bid_ask";
        center: number;
        width: number;
        weight: number;
    }>;
    pool_config?: {
        poolAddress: string;
        binStep: number;
        activeBin: number;
    };
}

/**
 * Deployment result for tracking created positions
 */
interface DeploymentResult {
    strategyIndex: number;
    type: string;
    positionKey: string | null;
    success: boolean;
    error?: string;
}

// ============================================================================
// WALLET LOADING
// ============================================================================

/**
 * Load wallet keypair from .env file
 * Supports both base58 encoded strings and JSON array formats
 */
function loadWalletFromEnv(): Keypair {
    const privateKey = process.env.PRIVATE_KEY;
    
    if (!privateKey) {
        throw new Error(
            "PRIVATE_KEY not found in .env file, Or you need to make a .env file." 
        );
    }
    
    try {
        // Check if it's a JSON array format (from keypair file)
        if (privateKey.trim().startsWith("[")) {
            const secretKey = Uint8Array.from(JSON.parse(privateKey));
            return Keypair.fromSecretKey(secretKey);
        }
        
        // Otherwise assume base58 encoded
        const secretKey = bs58.decode(privateKey);
        return Keypair.fromSecretKey(secretKey);
    } catch (error) {
        throw new Error(
            `Failed to parse PRIVATE_KEY: ${error}\n` +
            "Key should be either base58 encoded or JSON array format"
        );
    }
}

// ============================================================================
// INTERACTIVE PROMPTS
// ============================================================================

/**
 * Create readline interface for user input
 */
function createReadlineInterface(): readline.Interface {
    return readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });
}

/**
 * Ask user for yes/no confirmation
 */
async function askConfirmation(question: string): Promise<boolean> {
    const rl = createReadlineInterface();
    
    return new Promise((resolve) => {
        rl.question(`${question} (y/n): `, (answer) => {
            rl.close();
            const normalized = answer.toLowerCase().trim();
            resolve(normalized === 'y' || normalized === 'yes');
        });
    });
}

/**
 * Ask user for strategy deployment choice
 * Returns: 'yes', 'no', 'skip-all'
 */
async function askStrategyConfirmation(strategyNum: number, total: number): Promise<string> {
    const rl = createReadlineInterface();
    
    return new Promise((resolve) => {
        rl.question(`Deploy strategy ${strategyNum}/${total}? (y/n/skip-all): `, (answer) => {
            rl.close();
            const normalized = answer.toLowerCase().trim();
            if (normalized === 'skip-all' || normalized === 's') {
                resolve('skip-all');
            } else if (normalized === 'y' || normalized === 'yes') {
                resolve('yes');
            } else {
                resolve('no');
            }
        });
    });
}

// ============================================================================
// RETRY LOGIC
// ============================================================================

/**
 * Execute a function with one retry on failure
 */
async function executeWithRetry<T>(
    fn: () => Promise<T>,
    description: string
): Promise<T> {
    try {
        return await fn();
    } catch (error) {
        console.log(`\n  ! First attempt failed: ${error}`);
        console.log(`  Retrying ${description}...`);
        
        // Wait a bit before retry
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        return await fn(); // Retry once, throw if fails again
    }
}

// ============================================================================
// STRATEGY MAPPING
// ============================================================================

/**
 * Map Python strategy types to Meteora StrategyType
 */
function mapStrategyType(pythonType: string): StrategyType {
    switch (pythonType) {
        case "rectangle":
            return StrategyType.Spot;
        case "curve":
            return StrategyType.Curve;
        case "bid_ask":
            return StrategyType.BidAsk;
        default:
            throw new Error(`Unknown strategy type: ${pythonType}`);
    }
}

/**
 * Get human-readable name for Meteora strategy type
 */
function getStrategyTypeName(pythonType: string): string {
    switch (pythonType) {
        case "rectangle": return "Spot";
        case "curve": return "Curve";
        case "bid_ask": return "BidAsk";
        default: return pythonType;
    }
}

/**
 * Load a strategy plan from JSON file
 */
export function loadStrategyPlan(filePath: string): StrategyPlan {
    const content = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(content) as StrategyPlan;
}

/**
 * Calculate bin range for a strategy based on center and width
 */
function calculateBinRange(
    center: number,
    width: number,
    activeBin: number
): { minBinId: number; maxBinId: number } {
    const absoluteCenter = activeBin + center;
    const halfWidth = Math.floor(width / 2);
    
    return {
        minBinId: absoluteCenter - halfWidth,
        maxBinId: absoluteCenter + halfWidth
    };
}

// ============================================================================
// PREVIEW (DRY RUN)
// ============================================================================

/**
 * Preview what would be executed without actually deploying
 */
export function previewStrategyPlan(
    plan: StrategyPlan,
    poolAddress: string,
    totalXAmount: BN,
    totalYAmount: BN,
    activeBin: number,
    walletAddress?: string
): void {
    console.log("\n" + "=".repeat(60));
    console.log("STRATEGY PLAN PREVIEW (DRY RUN)");
    console.log("=".repeat(60));
    console.log(`Plan version: ${plan.version}`);
    console.log(`Generated at: ${plan.generated_at}`);
    
    console.log(`\nMetrics:`);
    console.log(`  R² quality: ${plan.metrics.r_squared.toFixed(4)}`);
    console.log(`  Residual: ${plan.metrics.residual.toFixed(6)}`);
    console.log(`  Truncated: ${plan.metrics.truncated}`);
    
    console.log(`\nDeployment Config:`);
    console.log(`  Network: Devnet`);
    console.log(`  Pool: ${poolAddress}`);
    console.log(`  Active bin: ${activeBin}`);
    console.log(`  Total X: ${totalXAmount.toString()}`);
    console.log(`  Total Y: ${totalYAmount.toString()}`);
    if (walletAddress) {
        console.log(`  Wallet: ${walletAddress}`);
    }
    
    console.log(`\nStrategies (${plan.strategies.length}):`);
    
    for (let i = 0; i < plan.strategies.length; i++) {
        const strat = plan.strategies[i];
        const { minBinId, maxBinId } = calculateBinRange(strat.center, strat.width, activeBin);
        const xAmount = new BN(totalXAmount.muln(Math.floor(strat.weight * 10000)).divn(10000));
        const yAmount = new BN(totalYAmount.muln(Math.floor(strat.weight * 10000)).divn(10000));
        
        console.log(`\n  ${i + 1}. ${strat.type.toUpperCase()} -> ${getStrategyTypeName(strat.type)}`);
        console.log(`     Center: ${strat.center}, Width: ${strat.width}`);
        console.log(`     Bin range: ${minBinId} to ${maxBinId}`);
        console.log(`     Weight: ${(strat.weight * 100).toFixed(2)}%`);
        console.log(`     X allocation: ${xAmount.toString()}`);
        console.log(`     Y allocation: ${yAmount.toString()}`);
    }
    
    console.log("\n" + "=".repeat(60));
}

// ============================================================================
// INTERACTIVE EXECUTION
// ============================================================================

/**
 * Execute a strategy plan interactively with confirmations
 */
export async function executeStrategyPlanInteractive(
    client: Client,
    plan: StrategyPlan,
    poolAddress: string,
    totalXAmount: BN,
    totalYAmount: BN,
    activeBin: number,
    slippage: number = 1
): Promise<DeploymentResult[]> {
    const results: DeploymentResult[] = [];
    let skipRemaining = false;
    
    console.log("\n" + "=".repeat(60));
    console.log("INTERACTIVE DEPLOYMENT");
    console.log("=".repeat(60));
    console.log(`Deploying ${plan.strategies.length} strategies to pool ${poolAddress}`);
    console.log(`Active bin: ${activeBin}`);
    console.log("");
    
    for (let i = 0; i < plan.strategies.length; i++) {
        const strat = plan.strategies[i];
        const stratNum = i + 1;
        
        // Calculate amounts
        const xAmount = new BN(totalXAmount.muln(Math.floor(strat.weight * 10000)).divn(10000));
        const yAmount = new BN(totalYAmount.muln(Math.floor(strat.weight * 10000)).divn(10000));
        const { minBinId, maxBinId } = calculateBinRange(strat.center, strat.width, activeBin);
        
        console.log(`\n--- Strategy ${stratNum}/${plan.strategies.length} ---`);
        console.log(`  Type: ${strat.type.toUpperCase()} -> ${getStrategyTypeName(strat.type)}`);
        console.log(`  Center: ${strat.center}, Width: ${strat.width}`);
        console.log(`  Bin range: ${minBinId} to ${maxBinId}`);
        console.log(`  Weight: ${(strat.weight * 100).toFixed(2)}%`);
        console.log(`  X Amount: ${xAmount.toString()}`);
        console.log(`  Y Amount: ${yAmount.toString()}`);
        
        // Check if we should skip
        if (skipRemaining) {
            console.log(`  [SKIPPED - user chose skip-all]`);
            results.push({
                strategyIndex: i,
                type: strat.type,
                positionKey: null,
                success: false,
                error: "Skipped by user"
            });
            continue;
        }
        
        // Ask for confirmation
        const choice = await askStrategyConfirmation(stratNum, plan.strategies.length);
        
        if (choice === 'skip-all') {
            skipRemaining = true;
            console.log(`  [SKIPPED - skipping all remaining]`);
            results.push({
                strategyIndex: i,
                type: strat.type,
                positionKey: null,
                success: false,
                error: "Skipped by user"
            });
            continue;
        }
        
        if (choice === 'no') {
            console.log(`  [SKIPPED]`);
            results.push({
                strategyIndex: i,
                type: strat.type,
                positionKey: null,
                success: false,
                error: "Skipped by user"
            });
            continue;
        }
        
        // Execute with retry
        try {
            console.log(`  Deploying...`);
            
            const strategyParams = await client.createStrategy(
                mapStrategyType(strat.type),
                minBinId,
                maxBinId
            );
            
            const positionKey = await executeWithRetry(
                () => client.createPosition(
                    poolAddress,
                    xAmount,
                    yAmount,
                    strategyParams,
                    slippage
                ),
                `strategy ${stratNum} deployment`
            );
            
            console.log(`  ✓ Position created: ${positionKey}`);
            results.push({
                strategyIndex: i,
                type: strat.type,
                positionKey: positionKey,
                success: true
            });
            
        } catch (error) {
            console.error(`  ✗ Failed after retry: ${error}`);
            results.push({
                strategyIndex: i,
                type: strat.type,
                positionKey: null,
                success: false,
                error: String(error)
            });
            
            // Ask if user wants to continue
            const continueDeployment = await askConfirmation("Continue with remaining strategies?");
            if (!continueDeployment) {
                console.log("\nDeployment stopped by user.");
                break;
            }
        }
    }
    
    // Print summary
    printDeploymentSummary(results, plan.strategies.length);
    
    return results;
}

/**
 * Print deployment summary
 */
function printDeploymentSummary(results: DeploymentResult[], total: number): void {
    console.log("\n" + "=".repeat(60));
    console.log("DEPLOYMENT SUMMARY");
    console.log("=".repeat(60));
    
    const successful = results.filter(r => r.success);
    const failed = results.filter(r => !r.success && r.error !== "Skipped by user");
    const skipped = results.filter(r => r.error === "Skipped by user");
    
    console.log(`\nTotal strategies: ${total}`);
    console.log(`  Successful: ${successful.length}`);
    console.log(`  Failed: ${failed.length}`);
    console.log(`  Skipped: ${skipped.length}`);
    
    if (successful.length > 0) {
        console.log(`\nCreated positions:`);
        for (const r of successful) {
            console.log(`  ${r.strategyIndex + 1}. ${r.type} -> ${r.positionKey}`);
        }
    }
    
    if (failed.length > 0) {
        console.log(`\nFailed strategies:`);
        for (const r of failed) {
            console.log(`  ${r.strategyIndex + 1}. ${r.type} - ${r.error}`);
        }
    }
    
    console.log("\n" + "=".repeat(60));
}

// ============================================================================
// CLI ARGUMENT PARSING
// ============================================================================

interface CLIArgs {
    planPath: string;
    poolAddress: string;
    amountX: string;
    amountY: string;
    preview: boolean;
}

function parseArgs(): CLIArgs | null {
    const args = process.argv.slice(2);
    
    if (args.length < 1 || args.includes("--help") || args.includes("-h")) {
        printUsage();
        return null;
    }
    
    const planPath = args[0];
    const preview = args.includes("--preview");
    
    // Parse named arguments
    let poolAddress = "";
    let amountX = "1000000000"; // Default: 1 token with 9 decimals
    let amountY = "1000000";    // Default: 1 token with 6 decimals
    
    for (let i = 1; i < args.length; i++) {
        if (args[i] === "--pool" && args[i + 1]) {
            poolAddress = args[i + 1];
            i++;
        } else if (args[i] === "--amount-x" && args[i + 1]) {
            amountX = args[i + 1];
            i++;
        } else if (args[i] === "--amount-y" && args[i + 1]) {
            amountY = args[i + 1];
            i++;
        }
    }
    
    return { planPath, poolAddress, amountX, amountY, preview };
}

function printUsage(): void {
    console.log(`
DLMM Compiler - Strategy Executor

Usage:
  npx ts-node executor.ts <plan.json> --pool <address> [options]

Arguments:
  <plan.json>              Path to strategy plan JSON file

Required:
  --pool <address>         Pool address to deploy to

Options:
  --amount-x <lamports>    Total X token amount (default: 1000000000)
  --amount-y <lamports>    Total Y token amount (default: 1000000)
  --preview                Preview only, don't execute

Environment:
  PRIVATE_KEY              Wallet private key (in .env file)

Examples:
  # Preview a strategy plan
  npx ts-node executor.ts strategy_plan.json --pool 9Rys... --preview

  # Deploy interactively
  npx ts-node executor.ts strategy_plan.json --pool 9Rys... --amount-x 1000000000 --amount-y 1000000
`);
}

// ============================================================================
// MAIN
// ============================================================================

async function main() {
    const cliArgs = parseArgs();
    if (!cliArgs) {
        process.exit(1);
    }
    
    const { planPath, poolAddress, amountX, amountY, preview } = cliArgs;
    
    // Validate pool address
    if (!poolAddress && !preview) {
        console.error("Error: --pool <address> is required for deployment");
        console.error("Use --preview for dry run without pool address");
        process.exit(1);
    }
    
    // Load strategy plan
    console.log(`Loading strategy plan from: ${planPath}`);
    const plan = loadStrategyPlan(planPath);
    
    const totalX = new BN(amountX);
    const totalY = new BN(amountY);
    
    if (preview) {
        // Preview mode - no wallet needed
        previewStrategyPlan(plan, poolAddress || "N/A", totalX, totalY, 0);
        return;
    }
    
    // Load wallet from .env
    console.log("Loading wallet from .env...");
    const wallet = loadWalletFromEnv();
    console.log(`Wallet address: ${wallet.publicKey.toBase58()}`);
    
    // Connect to devnet
    console.log("Connecting to Solana devnet...");
    const connection = new Connection(clusterApiUrl('devnet'), 'confirmed');
    
    // Create client
    const client = new Client(connection, wallet);
    
    // Query active bin from pool
    console.log(`Querying pool ${poolAddress}...`);
    const activeBinData = await client.getActiveBin(poolAddress);
    const activeBin = activeBinData.binId;
    console.log(`Active bin: ${activeBin}`);
    
    // Show preview first
    previewStrategyPlan(plan, poolAddress, totalX, totalY, activeBin, wallet.publicKey.toBase58());
    
    // Ask for confirmation to proceed
    const proceed = await askConfirmation("\nProceed with deployment?");
    if (!proceed) {
        console.log("Deployment cancelled.");
        process.exit(0);
    }
    
    // Execute interactively
    await executeStrategyPlanInteractive(
        client,
        plan,
        poolAddress,
        totalX,
        totalY,
        activeBin,
        1 // slippage
    );
}

// Run if called directly
main().catch((error) => {
    console.error("Error:", error);
    process.exit(1);
});
