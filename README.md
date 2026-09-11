A modular open-source engine for constructing, optimizing, and deploying custom liquidity distributions on Meteora's Dynamic Liquidity Market Maker (DLMM) protocol.

The DLMM Compiler solves a fundamental problem in DeFi liquidity management: translating an arbitrary desired liquidity distribution into deployable strategies that Meteora's protocol supports.

### How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INPUT                                  │
│   "I want a Gaussian distribution centered at price X"              │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      PYTHON OPTIMIZER                               │
│   1. Generate template library (rectangle, curve, bid_ask)          │
│   2. Run greedy forward selection to find best strategies           │
│   3. Output: JSON strategy plan with optimal weights                │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      TYPESCRIPT EXECUTOR                            │
│   1. Load strategy plan JSON                                        │
│   2. Map to Meteora StrategyType (Spot/Curve/BidAsk)                │
│   3. Deploy positions on-chain                                      │
└─────────────────────────────────────────────────────────────────────┘


#Further Proofs
