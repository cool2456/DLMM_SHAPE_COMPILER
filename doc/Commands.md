
### Current Project Structure

```
dlmm-compiler/
├── src/
│   ├── python/
│   │   ├── __init__.py      # Module exports
│   │   └── templates.py     # Core optimizer + CLI (535 lines)
│   └── sdk/
│       ├── client.ts        # Meteora DLMM client wrapper
│       ├── executor.ts      # Strategy plan executor
│       └── test.ts          # SDK test file
├── config/
│   └── pool_config.json     # Pool configuration
├── doc/
│   └── plans/               # Implementation plans (completed)
├── requirements.txt         # Python deps: numpy, scipy, matplotlib
└── package.json             # Node deps: @meteora-ag/dlmm, @solana/web3.js
```

---

### Python Optimizer Commands


| Option | Description | Default |
|--------|-------------|---------|
| `--target` | `gaussian`, `uniform`, `curve`, `bid_ask` | `gaussian` |
| `--center` | Center bin position | `34` |
| `--sigma` | Gaussian spread (only for gaussian) | `12` |
| `--width` | Width (for uniform/curve/bid_ask) | `25` |
| `--bins` | Total number of bins | `69` |
| `--max-strategies` | Max strategies to output | `3` |
| `--output`, `-o` | JSON output path | None |
| `--plot` | Show matplotlib visualization | False |
| `--quiet`, `-q` | Suppress verbose output | False |

**Example commands:**
```bash
# Gaussian → JSON (production use)
python src/python/templates.py --target gaussian --center 34 --sigma 12 --max-strategies 3 -o strategy_plan.json

# Uniform distribution
python src/python/templates.py --target uniform --center 34 --width 20 --max-strategies 2 -o plan.json

# With visualization (demo/debugging)
python src/python/templates.py --target gaussian --center 34 --sigma 10 --plot

```

---

### TypeScript Executor Commands

**Preview a strategy plan:**
```bash
npx ts-node src/sdk/executor.ts strategy_plan.json --preview
```

