# PromptThrift MCP — Smart Token Compression for LLM Apps

> Cut 70-90% of your LLM API costs with intelligent conversation compression.
> Now with **Gemma 4 local compression** — smarter summaries, zero API cost.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io)
[![Gemma 4](https://img.shields.io/badge/Gemma_4-Supported-orange.svg)](https://deepmind.google/models/gemma/gemma-4/)

## The Problem

Every LLM API call resends your **entire conversation history**. A 20-turn chat costs 6x more per call than a 3-turn one — you're paying for the same old messages over and over.

```
Turn 1:  ████ 700 tokens ($0.002)
Turn 5:  ████████████████ 4,300 tokens ($0.013)
Turn 20: ████████████████████████████████████████ 12,500 tokens ($0.038)
                                              ↑ You're paying for THIS every call
```

## The Solution

PromptThrift is an MCP server with 4 tools to slash your API costs:

| Tool | What it does | Impact |
|------|-------------|--------|
| `promptthrift_compress_history` | Compress old turns into a smart summary | 50-90% fewer input tokens |
| `promptthrift_count_tokens` | Track token usage & costs across 14 models | Know where money goes |
| `promptthrift_suggest_model` | Recommend cheapest model for the task | 60-80% on simple tasks |
| `promptthrift_pin_facts` | Pin critical facts that survive compression | Never lose key context |

## Why PromptThrift?

| | PromptThrift | Context Mode | Headroom |
|---|---|---|---|
| License | **MIT** (commercial OK) | ELv2 (no competing) | Apache 2.0 |
| Compression type | **Conversation memory** | Tool schema virtualization | Tool output |
| Local LLM support | **Gemma 4 via Ollama** | No | No |
| Cost tracking | **Multi-model comparison** | No | No |
| Model routing | **Built-in** | No | No |
| Pinned facts | **Never-Compress List** | No | No |

## Quick Start

### Install

```bash
git clone https://github.com/woling-dev/promptthrift-mcp.git
cd promptthrift-mcp
pip install -r requirements.txt
```

### Optional: Enable Gemma 4 Compression

For smarter AI-powered compression (free, runs locally):

```bash
# Install Ollama: https://ollama.com
ollama pull gemma4:4b
```

PromptThrift auto-detects Ollama. If running → uses Gemma 4 for compression. If not → falls back to fast heuristic compression. Zero config needed.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "promptthrift": {
      "command": "python",
      "args": ["/path/to/promptthrift-mcp/server.py"]
    }
  }
}
```

### Cursor / Windsurf

Add to your MCP settings:

```json
{
  "mcpServers": {
    "promptthrift": {
      "command": "python",
      "args": ["/path/to/promptthrift-mcp/server.py"]
    }
  }
}
```

## Real-World Example

A customer service bot handling olive oil product Q&A:

**Before compression (sent every API call):**
```
Q: Can I drink olive oil straight?
A: Yes! Our extra virgin is drinkable. We have 500ml and 1000ml.
Q: What's the difference between PET and glass bottles?
A: Glass is our premium line. 1000ml PET is for heavy cooking families.
Q: Which one do you recommend?
A: For drinking: Extra Virgin 500ml. For salads/cooking: 1000ml.
Q: I also do a lot of frying.
A: For high-heat frying, our Pure Olive Oil 500ml (230°C smoke point).
```
~250 tokens × every subsequent API call

**After Gemma 4 compression:**
```
[Compressed history]
Customer asks about olive oil products. Key facts:
- Extra virgin (500ml glass) for drinking, single-origin available
- 1000ml PET for cooking/salads (lower grade, family-size)
- Pure olive oil 500ml for high-heat frying (230°C smoke point)
[End compressed history]
```
~80 tokens — **68% saved on every call after this point**

With 100 customers/day averaging 30 turns each on Claude Sonnet: **~$14/month saved** from one bot.

## Pinned Facts (Never-Compress List)

Some facts must **never** be lost during compression — user names, critical preferences, key decisions. Pin them:

```
You: "Pin the fact that this customer is allergic to nuts"

→ promptthrift_pin_facts(action="add", facts=["Customer is allergic to nuts"])
→ This fact will appear in ALL future compressed summaries, guaranteed.
```

## Supported Models (April 2026 pricing)

| Model | Input $/MTok | Output $/MTok | Local? |
|-------|-------------|---------------|--------|
| gemma-4-e2b | **$0.00** | **$0.00** | Ollama |
| gemma-4-e4b | **$0.00** | **$0.00** | Ollama |
| gemma-4-27b | **$0.00** | **$0.00** | Ollama |
| gemini-2.0-flash | $0.10 | $0.40 | |
| gpt-4.1-nano | $0.10 | $0.40 | |
| gpt-4o-mini | $0.15 | $0.60 | |
| gemini-2.5-flash | $0.15 | $0.60 | |
| gpt-4.1-mini | $0.40 | $1.60 | |
| claude-haiku-4.5 | $1.00 | $5.00 | |
| gemini-2.5-pro | $1.25 | $10.00 | |
| gpt-4.1 | $2.00 | $8.00 | |
| gpt-4o | $2.50 | $10.00 | |
| claude-sonnet-4.6 | $3.00 | $15.00 | |
| claude-opus-4.6 | $5.00 | $25.00 | |

## How It Works

```
Before (every API call sends ALL of this):
┌──────────────────────────────────┐
│ System prompt      (500 tokens)  │
│ Turn 1: user+asst  (600 tokens)  │  ← Repeated every call
│ Turn 2: user+asst  (600 tokens)  │  ← Repeated every call
│ ...                              │
│ Turn 8: user+asst  (600 tokens)  │  ← Repeated every call
│ Turn 9: user+asst  (new)         │
│ Turn 10: user      (new)         │
└──────────────────────────────────┘
Total: ~6,500 tokens per call

After PromptThrift compression:
┌──────────────────────────────────┐
│ System prompt      (500 tokens)  │
│ [Pinned facts]      (50 tokens)  │  ← Always preserved
│ [Compressed summary](200 tokens) │  ← Turns 1-8 in 200 tokens!
│ Turn 9: user+asst  (kept)        │
│ Turn 10: user      (kept)        │
└──────────────────────────────────┘
Total: ~1,750 tokens per call (73% saved!)
```

### Compression Modes

| Mode | Method | Quality | Speed | Cost |
|------|--------|---------|-------|------|
| Heuristic | Rule-based extraction | Good (50-60% reduction) | Instant | Free |
| LLM (Gemma 4) | AI-powered understanding | Excellent (70-90% reduction) | ~2s | Free (local) |

PromptThrift automatically uses the best available method. Install Ollama + Gemma 4 for maximum compression quality.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PROMPTTHRIFT_OLLAMA_MODEL` | No | `gemma4:4b` | Ollama model for LLM compression |
| `PROMPTTHRIFT_OLLAMA_URL` | No | `http://localhost:11434` | Ollama API endpoint |
| `PROMPTTHRIFT_DEFAULT_MODEL` | No | `claude-sonnet-4.6` | Default model for cost estimates |

## Security

- All data processed **locally** by default — nothing leaves your machine
- Ollama compression runs 100% on your hardware
- **Post-compression sanitizer** strips prompt injection patterns from summaries
- API keys read from environment variables only, never hardcoded
- No persistent storage, no telemetry, no third-party calls

## Roadmap

- [x] Heuristic conversation compression
- [x] Multi-model token counting (14 models)
- [x] Intelligent model routing
- [x] **Gemma 4 local LLM compression via Ollama**
- [x] **Pinned facts (Never-Compress List)**
- [x] **Post-compression security sanitizer**
- [ ] Cloud-based compression (Anthropic/OpenAI API fallback)
- [ ] Prompt caching optimization advisor
- [ ] Web dashboard for usage analytics
- [ ] VS Code extension

## Contributing

PRs welcome! This project uses MIT license — fork it, improve it, ship it.

## License

[MIT License](LICENSE) — Free for personal and commercial use.

---

Built by [Woling Dev Lab](https://github.com/woling-dev)

**Star this repo if it saves you money!**
