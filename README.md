# PromptThrift MCP — Smart Token Compression for LLM Apps

> Cut 70-90% of your LLM API costs with intelligent conversation compression.
> Now with **Gemma 4 local compression** — smarter summaries, zero API cost.

<a href="https://glama.ai/mcp/servers/@woling-dev/promptthrift-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@woling-dev/promptthrift-mcp/badge" alt="PromptThrift MCP server" />
</a>

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-purple.svg)](https://modelcontextprotocol.io)
[![Gemma 4](https://img.shields.io/badge/Gemma_4-Supported-orange.svg)](https://deepmind.google/models/gemma/gemma-4/)

⭐ **If this saves you money, star this repo!** ⭐

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

**Option A: pip install (recommended)**
```bash
pip install git+https://github.com/woling-dev/promptthrift-mcp.git
```

**Option B: clone and install**
```bash
git clone https://github.com/woling-dev/promptthrift-mcp.git
cd promptthrift-mcp
pip install -e .
```

### Optional: Enable Gemma 4 Compression

For smarter AI-powered compression (free, runs locally):

```bash
# Install Ollama: https://ollama.com
ollama pull gemma4:e4b
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

An AI coding assistant debugging a complex issue over 30+ turns:

**Before compression (sent every API call):**
```
User: My Next.js app throws a hydration error on the /dashboard page.
Asst: That usually means server and client HTML don't match. Can you share the component?
User: [pastes 50 lines of DashboardLayout.tsx]
Asst: I see the issue — you're using `new Date()` directly in render, which differs
      between server and client. Let me also check your data fetching...
User: I also get a warning about useEffect running twice.
Asst: That's React 18 Strict Mode. Not related to hydration. Let me trace the real bug...
User: Wait, there's also a flash of unstyled content on first load.
Asst: That's a separate CSS loading order issue. Let me address both...
      [... 25 more turns of debugging, trying fixes, checking logs ...]
User: OK it's fixed now! But I want to add dark mode next.
Asst: Great! For dark mode with Next.js + Tailwind, here are three approaches...
```
~8,500 tokens after 30 turns — **and growing every single API call**

**After Gemma 4 compression:**
```
[Compressed history]
Resolved Next.js hydration error in DashboardLayout.tsx caused by
Date() in render (fixed with useEffect). Unrelated: React 18 Strict Mode
double-fire (expected), CSS flash (fixed via loading order).
User now wants to add dark mode to Next.js + Tailwind app.
[End compressed history]

[Recent turns preserved — last 4 turns intact]
```
~1,200 tokens — **86% saved on every subsequent call**

**Cost impact at scale (Claude Sonnet @ $3/MTok):**
| Scenario | Without PromptThrift | With PromptThrift | Monthly Savings |
|----------|---------------------|-------------------|-----------------|
| 1 dev, 20 sessions/day | $5.10/mo | $0.72/mo | **$4.38** |
| Team of 10 devs | $51/mo | $7.20/mo | **$43.80** |
| Customer service bot (500 chats/day) | $255/mo | $36/mo | **$219** |
| AI agent platform (5K sessions/day) | $2,550/mo | $357/mo | **$2,193** |

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
| LLM (Gemma 4) | AI-powered understanding | Excellent (70-90% reduction) | ~10-15s | Free (local) |

PromptThrift automatically uses the best available method. Install Ollama + Gemma 4 for maximum compression quality.

### When Does Compression Shine?

Compression effectiveness scales with conversation length and redundancy:

| Conversation Length | Typical Reduction | Best For |
|---|---|---|
| Short (< 5 turns, mostly technical) | 15-25% | Minimal savings — keep as-is |
| Medium (10-20 turns, mixed chat) | 50-70% | Sweet spot — clear cost reduction |
| Long (30+ turns, debugging/iterating) | **70-90%** | Massive savings — compress early and often |

**Why?** Short, dense conversations have little filler to remove. Longer conversations accumulate greetings, repeated context, exploratory dead-ends, and verbose explanations — exactly what the compressor strips away. A 30-turn debugging session with code snippets, back-and-forth troubleshooting, and final resolution compresses dramatically because only the conclusion and key decisions matter for future context.

**Rule of thumb:** Start compressing after 8-10 turns for best results.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PROMPTTHRIFT_OLLAMA_MODEL` | No | `gemma4:e4b` | Ollama model for LLM compression |
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
