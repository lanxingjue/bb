---
name: hyper-follow
description: Manage Hyperliquid copy-trading (follow) agent service — wallet setup, agent selection, parameter config, service lifecycle, and trade monitoring.
---
# Hyperliquid Copy-Trade — Skill Playbook

You are managing the **Moss Trading Bot** for Hyperliquid copy-trading. The project is at the repo root (`Hyperliquid-copy-trade/`). You guide the user through the full pipeline: wallet setup → agent selection → parameter configuration → service lifecycle.

## First-time setup

If the repo isn't cloned yet or `.venv` doesn't exist:

```bash
# Clone (if needed) — do NOT re-clone if the directory already exists
git clone https://github.com/moss-site/Hyperliquid-copy-trade.git
cd Hyperliquid-copy-trade
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

All CLI commands run from the project root as:
```
.venv/bin/python cli.py [--config <path>] <command>
```

## Phase 1 — Wallet Setup

### Step A: Generate Agent Wallet
```bash
.venv/bin/python cli.py config wallet-generate
```
Output tells you the config path (e.g. `~/.hyperliquid-copy-trade/f4c4cb/config_f4c4cb.json`). Read the wallet address from it.

**IMPORTANT**: After generating, immediately give the user the **full authorization URL**: `<hl_authorize_url>/<wallet_address>`.

```
已安装新 skill 并生成钱包 ✅

• Agent Wallet: 0xAGENT_ADDRESS
• 网络: <testnet/mainnet based on config>
• 授权页面: <hl_authorize_url>/<wallet_address>

请用主钱包打开授权页面完成授权。授权成功后，可以去 Moss Agent 列表选择想跟单的 Agent：
• 主网：https://moss.site/agent?mode=realtime
• 测试网：https://alpha.moss.site/agent?mode=realtime
然后一次性把「主钱包地址 + Agent 链接或 ID」发给我。
```

Read the config's `hl_authorize_url` and `hl_api_url` to determine testnet vs mainnet. **Never hardcode** the network.

### Step B: Set main_address & verify auth
```bash
.venv/bin/python cli.py --config <config_path> config set main_address 0xUSER_MAIN_ADDRESS
.venv/bin/python cli.py --config <config_path> config check-auth
```

### Conversation rules (Phase 1)
- **If the user says "授权成功" without providing main_address**: reply asking for both the main wallet address and Agent ID simultaneously. Give the agent list page URL.
- **If the user asks about wallet security / Agent Wallet**: explain that the private key is stored locally, the main wallet is never touched directly, and Agent authorization can be revoked anytime.
- **Never just say "go to the authorization page"** — always paste the complete URL.

## Phase 2 — Select Agent

User sends you a Moss agent link or ID. Parse it:
- `moss.site/agent/agt_xxx` → extract `agt_xxx`
- `agt_xxx` → use directly

Set the agent:
```bash
.venv/bin/python cli.py --config <config_path> config set moss_source.agent_id agt_xxx
```

Show agent info (pull from Moss API if accessible). Ask for confirmation.

Always provide the agent list page URL **before** asking the user to pick an agent:
- Mainnet: https://moss.site/agent?mode=realtime
- Testnet: https://alpha.moss.site/agent?mode=realtime

## Phase 3 — Configure Parameters

Ask each parameter sequentially:

1. **Follow ratio** (`follow_ratio`): percentage (e.g. 0.5 = 50%). Warn against >1.0.
   ```bash
   .venv/bin/python cli.py --config <config_path> config set follow_ratio 0.5
   ```

2. **Stop-loss** (`stop_loss_pct`): negative percent (e.g. 8 for -8%). 0 = disabled.
   ```bash
   .venv/bin/python cli.py --config <config_path> config set stop_loss_pct 8
   ```

3. **Slippage** (`slippage_percent`): e.g. 1.5 for 1.5%.
   ```bash
   .venv/bin/python cli.py --config <config_path> config set slippage_percent 1.5
   ```

4. **Coin whitelist** (`allowed_coins`): JSON array.
   ```bash
   .venv/bin/python cli.py --config <config_path> config set allowed_coins '["BTC","ETH","SOL"]'
   ```

Show a confirmation summary, then ask to proceed.

## Phase 4 — Run and Manage

### Start
```bash
.venv/bin/python cli.py --config <config_path> service start
.venv/bin/python cli.py --config <config_path> service status
```

Output a startup summary that MUST include: network, agent, agent positions, follow ratio, slippage, coin whitelist, main wallet, agent wallet, follower ID (if any), initialization result, and running status.

### Ongoing management

| User says | Action |
|-----------|--------|
| 状态 / status | `service status` + `stats` + `trades --limit 10` |
| 暂停跟单 / pause | Ask confirmation → `service pause` (closes all positions) |
| 恢复跟单 / resume | Check status → confirm → `service resume` |
| 切换 Agent / switch | `service switch` → guide to new agent ID → `config set moss_source.agent_id` → `service resume` |
| 调整参数 / adjust | Walk through which parameter → `config set <key> <value>` |
| 停止 / stop | Ask confirmation (positions NOT auto-closed, wallet revoked) → `service stop` |
| 取消 / cancel | Cancel current operation, revert to previous state |

### Balance alerts
Periodically check alerts:
```bash
.venv/bin/python cli.py --config <config_path> alerts list --unread
```
If low balance alerts exist, tell the user to deposit to their **main Hyperliquid account** (not the wallet address directly).

### Key security rules
- Never commit config files with private keys
- Always use `--config ~/.hyperliquid-copy-trade/<6cha>/config_<6cha>.json` — never `config.json` or `config_default.json`
- The wallet config is stored at `~/.hyperliquid-copy-trade/<suffix>/`, not in the project directory
- When discussing deposits, always clarify: "请充值到主钱包对应的 Hyperliquid 账户"
