# DLMM Compiler

**Optimize any liquidity distribution into deployable Meteora strategies**

---

| | |
|---|---|
| **Category** | DeFi / Devtool |
| **Stage** | Devnet (Mainnet planned) |
| **Requested** | $4,000 |
| **Duration** | 4 weeks |

**Links:** [GitHub](https://github.com/IggyLikesToCode/dlmm-compiler) | Demo | Docs

**Contact:** 
Ignacy Nieweglowski | ignacy@example.com - Founder
Lucas Nilsson | lucas.nilsson@live.com - Developer
Pranav | pranav@example.com - Developer

---

## Quick Start for Reviewers

| Resource | Link |
|----------|------|
| GitHub Repository | [github.com/IggyLikesToCode/dlmm-compiler](https://github.com/IggyLikesToCode/dlmm-compiler) |
| Demo Video | *(coming soon)* |
| Example Devnet TX | *(coming soon)* |
| One-command test | `python src/python/templates.py --target gaussian --center 34 --sigma 12 --plot` |
| Example output | See `strategy_plan.json` in repo |

---

## Definitions

- **DLMM (Dynamic Liquidity Market Maker):** Meteora's concentrated liquidity protocol on Solana, enabling LPs to deploy liquidity across discrete price bins
- **Strategy Types:**
  - *Spot* — Uniform liquidity across a bin range
  - *Curve* — Bell-shaped distribution peaking at center
  - *BidAsk* — U-shaped distribution with liquidity concentrated at edges

---

## Executive Summary

- **Building:** An open-source optimization engine that translates arbitrary liquidity distributions into deployable Meteora DLMM strategies on Solana
- **For:** DeFi protocols, liquidity providers, and quant traders who need precise liquidity positioning
- **Outcome:** Any target distribution (Gaussian, uniform, custom) deployed on-chain using 2-3 optimized strategies
- **Why Solana:** Meteora DLMM is Solana-native; sub-second finality and low fees enable dynamic multi-position management
- **Grant unlocks:** Mainnet deployment, npm SDK package, and web UI dashboard for non-technical users
- **Proof today:** Working devnet deployment achieving R² = 0.992 on Gaussian test distributions (see Evaluation Method below)

---

## Problem and Target User

**Problem:**
- Meteora DLMM supports only 3 strategy types (Spot, Curve, BidAsk) with limited parameterization
- LPs manually guess which combination approximates their desired distribution—often poorly
- Poor approximations lead to suboptimal fee capture and capital inefficiency
- To our knowledge, no existing open-source tooling mathematically optimizes strategy selection

**Target Users:**
- DeFi protocols deploying liquidity incentive programs
- Sophisticated LPs and market makers seeking precise positioning
- Treasury management teams optimizing protocol-owned liquidity

---

## Solution

**Core Workflow:**

```
User Input ──▶ Python Optimizer ──▶ strategy_plan.json ──▶ TS Executor ──▶ Meteora DLMM
(Gaussian,      (Greedy NNLS)        (weights, params)      (deploy)        (on-chain)
 uniform...)
```

- User specifies target distribution (Gaussian centered at bin X, sigma Y)
- Python optimizer generates ~6,000 template combinations across all strategy types
- Greedy forward selection + NNLS finds the optimal 2-3 strategies that best approximate the target
- JSON strategy plan exported with weights and parameters
- TypeScript executor deploys positions to Meteora via SDK
- *(Planned)* Web UI for visual distribution building and one-click deployment

**Differentiation:**
- To our knowledge, the **first open-source tool** that mathematically optimizes Meteora distributions
- **Open-source** and composable with other Solana DeFi tooling
- **High accuracy** on tested distributions (see Evaluation Method)
- **Any distribution shape:** Works with Gaussian, uniform, bimodal, or fully custom

---

## Evaluation Method

Our optimization quality is measured as follows:

| Parameter | Value |
|-----------|-------|
| **Objective function** | Minimize sum of squared errors between target and approximation |
| **Metric** | R² (coefficient of determination): 1.0 = perfect fit, 0.0 = mean baseline |
| **Bin space** | 69 bins (default DLMM bin count for test pools) |
| **Templates evaluated** | ~6,000 combinations (3 types × centers × widths) |
| **Constraint** | Max 2-3 strategies per deployment |
| **Test distributions** | Gaussian (sigma 10-15), uniform, curve, bid_ask shapes |

**Benchmark result:** On Gaussian targets (center=34, sigma=12), the optimizer achieves R² = 0.992 with 2 strategies, compared to naive top-k selection which yields R² < 0 (negative, worse than mean).

---

## Why Solana

- **Meteora DLMM is Solana-native** — the target protocol runs exclusively on Solana
- **Sub-second finality** — enables frequent repositioning and responsive liquidity management
- **Low transaction fees** — makes multi-position strategies economically viable (deploying 3 strategies costs pennies)
- **Composability** — integrates with Jupiter routing, Raydium, and other Solana DeFi primitives
- **Parallel execution** — handles batch deployments of multiple strategies efficiently
- **Active LP ecosystem** — growing demand for better liquidity tooling from protocols and treasuries

---

## Current Status and Proof

| Component | Status | Evidence |
|-----------|--------|----------|
| Python Optimizer | Complete | Greedy NNLS algorithm, ~6,000 templates, CLI with `--plot` |
| TypeScript Executor | Complete | Interactive deployment, retry logic, wallet handling |
| Devnet Deployment | Live | Pool `9RysHRCsAJQU...` tested successfully |
| Optimization Quality | Verified | R² = 0.992 on Gaussian (sigma=12, 2 strategies) |
| Documentation | Complete | README, CLI help, inline code comments |
| GitHub Repository | Public | [View repo](https://github.com/IggyLikesToCode/dlmm-compiler) |

**Benchmark:** Optimizer vs naive selection on 10 Gaussian targets: median R² improved from -0.5 to 0.99.

---

## Technical Approach

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DLMM Compiler                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────────────┐  │
│  │    INPUT     │    │  PYTHON LAYER    │    │    TYPESCRIPT LAYER      │  │
│  │              │    │                  │    │                          │  │
│  │ Target dist. │───▶│ Template Gen     │    │  Plan Loader             │  │
│  │ (gaussian,   │    │ (rect/curve/     │    │  Strategy Mapper         │  │
│  │  uniform...) │    │  bid_ask)        │    │  (Spot/Curve/BidAsk)     │  │
│  │              │    │       │          │    │         │                │  │
│  │ Parameters:  │    │       ▼          │    │         ▼                │  │
│  │ - center     │    │ Greedy NNLS      │    │  Position Deployer       │  │
│  │ - sigma      │    │ Solver           │    │  (with preflight sim)    │  │
│  │ - width      │    │       │          │    │         │                │  │
│  └──────────────┘    │       ▼          │    │         ▼                │  │
│                      │ strategy_plan    │───▶│  Meteora SDK             │  │
│                      │ .json            │    │  (@meteora-ag/dlmm)      │  │
│                      └──────────────────┘    └──────────────────────────┘  │
│                                                        │                    │
└────────────────────────────────────────────────────────┼────────────────────┘
                                                         │
                                                         ▼
                                              ┌──────────────────────┐
                                              │   SOLANA MAINNET     │
                                              │   Meteora DLMM       │
                                              │   (audited program)  │
                                              └──────────────────────┘
```

**Key Components:**

| Layer | Technology | Function |
|-------|------------|----------|
| Optimizer | Python, NumPy, SciPy | Template generation, NNLS solving, greedy selection |
| Executor | TypeScript, @meteora-ag/dlmm | Strategy mapping, wallet handling, on-chain deployment |
| Bridge | JSON | Portable strategy plans between optimizer and executor |
| Planned | React, Wallet Adapter | Web UI for visual distribution building |

**Security Posture:**
- **No custom on-chain program** — uses Meteora's audited smart contracts exclusively
- **User-controlled keys** — wallet never leaves user's machine; no key storage
- **Preflight simulation** — transactions simulated before signing (planned)
- **Sanity bounds** — max slippage, min/max bin ranges, weight normalization checks
- **Read-only preview** — full dry-run mode before any on-chain action
- **Open-source** — full code visibility for community review

---

## Milestones and Budget

| Milestone | Deliverables | Acceptance Criteria | Timeline | Funding |
|-----------|--------------|---------------------|----------|---------|
| **M1: SDK Package** | npm package `@dlmm/compiler`, TypeScript types, API docs, example app | Published to npm, CI passing, versioned API, typed docs, one reference example. Already built backend and algorithm. | Week 1 | $500 |
| **M2: Mainnet Deploy** | Mainnet network support, pool discovery, safety checks | Mainnet deployment demo, dry-run mode, rate limiting, simulated TX preview | Week 2 | $1,500 |
| **M3: Web UI** | Finalizing React dashboard, visual distribution builder, wallet connect | Deployed webapp, shareable strategy plans, export/replay. The ui foundation is already built. | Week 3 | $1,000 |
| **M4: Integrations** | Multi-pool support, example notebooks | Supports 10+ Meteora pools, 2 reference integrations with docs | Week 4 | $1,000 |

**Total: $4,000 over 4 weeks (1 months)**

**Adoption Targets:**
IGGY you need to fill this in

---

## Budget Breakdown

| Category | Amount | Justification |
|----------|--------|---------------|
| Engineering | $2,000 | Core development: SDK, mainnet support, UI |
| Infrastructure | $1,000 | Helius/Triton RPC, Vercel hosting, GitHub Actions CI; no custodial backend |
| Design | $1,000 | UI/UX for web dashboard |


---

## Impact and Success Metrics

**Measurable Outcomes (90-180 days):**

| Metric | Target | How Measured |
|--------|--------|--------------|
| Tracking error reduction | 50%+ improvement vs manual strategy selection | Benchmark suite comparing optimizer vs baseline on 20 test distributions |
| Time-to-deploy | < 5 minutes from target spec to on-chain position | Timed user tests |
| Strategies required for R² > 0.95 | 2-3 strategies (down from 5+ manual attempts) | Optimizer output logs |
| SDK adoption | 500+ npm downloads in 90 days | npm stats |
| GitHub engagement | 50+ stars, 5+ forks | GitHub metrics |

**Stretch targets:**
- Featured in Meteora ecosystem content
- 3+ protocols evaluating integration

---

## Team

**Ignacy Nieweglowski** — Project Founder
- Solana and TypeScript development experience
- Built and shipped Meteora DLMM integrations
- Background in quantitative optimization

**Lucas Nilsson** - Developer 
 - History within cryptospace and contract deployment 
 - Built algorithm and backend connection
 - Built frontend


**Pranav** - Developer
 - *to be filled in* 


---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Meteora API changes** | Medium | Pin SDK versions, monitor changelog, maintain compatibility layer |
| **Low adoption** | Medium | Partner with Meteora for visibility, content marketing, Discord presence |
| **Suboptimal strategies deployed** | Medium | Preflight simulation, sanity bounds, read-only preview before signing |
| **Competition** | Low | First-mover in open-source space, unique optimization approach |

---

## Non-Goals

This project explicitly does **not**:
- Build a new AMM or liquidity protocol
- Custody user funds or manage vaults
- Store private keys or wallet credentials
- Provide financial advice or guaranteed returns
- Replace Meteora — it enhances the LP experience on Meteora

---

## The Ask

| | |
|---|---|
| **Total Funding** | $4,000 (flexible within $1K-$4K) |
| **Structure** | Milestone-based payments |
| **Timeframe** | 4 weeks starting upon approval |
| **End Deliverable** | Production-ready SDK + Web UI for deploying mathematically optimized Meteora liquidity distributions |

---

*DLMM Compiler — Precision liquidity positioning for Solana DeFi*
