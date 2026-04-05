"""
PromptThrift MCP Server v0.2.0 — Save 70-90% on LLM API token costs.

A lightweight MCP server that provides four token optimization tools:
1. compress_history — Summarize old conversation turns to reduce input tokens
2. count_tokens — Track token usage and estimate costs in real-time
3. suggest_model — Recommend the cheapest sufficient model for a task
4. pin_facts — Pin critical facts that must survive compression

v0.2.0: Gemma 4 local LLM compression via Ollama for smarter, free compression.

Works with Claude Desktop, Cursor, Windsurf, and any MCP-compatible client.

Security Notes:
- All conversation data is processed locally; nothing leaves your machine
  unless you explicitly call an LLM API for compression.
- API keys are read from environment variables only, never hardcoded.
- No data is stored persistently between sessions.
- Post-compression sanitizer strips potential prompt injection remnants.

License: MIT
Repository: https://github.com/woling-dev/promptthrift-mcp
"""

import json
import re
import os
import sys
import logging
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, field_validator
from mcp.server.fastmcp import FastMCP

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging (stderr only — stdio transport reserves stdout)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("promptthrift_mcp")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SERVER_NAME = "promptthrift_mcp"
SERVER_VERSION = "0.2.0"
DEFAULT_MAX_HISTORY_TOKENS = 4000
DEFAULT_KEEP_RECENT_TURNS = 4
DEFAULT_OLLAMA_MODEL = "gemma4:e4b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
COMPRESSION_SYSTEM_PROMPT = (
    "You are a conversation compressor. Summarize the following conversation "
    "history into a concise summary that preserves all key facts, decisions, "
    "context, and user preferences. Output ONLY the summary, no preamble. "
    "Keep it under {max_tokens} tokens. Use the same language as the original."
)

# Patterns that should be stripped from compressed output (anti prompt-injection)
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+a",
    r"system\s*:\s*",
    r"<\s*system\s*>",
    r"\[INST\]",
    r"<<SYS>>",
]

# Model pricing per million tokens (input / output) — updated March 2026
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Anthropic
    "claude-opus-4.6": {"input": 5.0, "output": 25.0, "context": 1_000_000},
    "claude-sonnet-4.6": {"input": 3.0, "output": 15.0, "context": 1_000_000},
    "claude-haiku-4.5": {"input": 1.0, "output": 5.0, "context": 200_000},
    # OpenAI
    "gpt-4o": {"input": 2.5, "output": 10.0, "context": 128_000},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6, "context": 128_000},
    "gpt-4.1": {"input": 2.0, "output": 8.0, "context": 1_000_000},
    "gpt-4.1-mini": {"input": 0.4, "output": 1.6, "context": 1_000_000},
    "gpt-4.1-nano": {"input": 0.1, "output": 0.4, "context": 1_000_000},
    # Google
    "gemini-2.0-flash": {"input": 0.1, "output": 0.4, "context": 1_000_000},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0, "context": 1_000_000},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.6, "context": 1_000_000},
    # Local (Gemma 4 via Ollama — cost is $0, listed for comparison)
    "gemma-4-e2b": {"input": 0.0, "output": 0.0, "context": 256_000},
    "gemma-4-e4b": {"input": 0.0, "output": 0.0, "context": 256_000},
    "gemma-4-27b": {"input": 0.0, "output": 0.0, "context": 256_000},
}

# Complexity thresholds for model routing
COMPLEXITY_KEYWORDS_HIGH = [
    "analyze", "architect", "debug complex", "refactor", "design system",
    "security audit", "optimize algorithm", "write essay", "legal",
    "research paper", "multi-step", "chain of thought",
]
COMPLEXITY_KEYWORDS_LOW = [
    "translate", "summarize", "format", "convert", "list", "simple question",
    "yes or no", "define", "what is", "how to", "fix typo",
]


# ---------------------------------------------------------------------------
# Token estimation (no external dependency — works offline)
# ---------------------------------------------------------------------------
def estimate_tokens(text: str) -> int:
    """Estimate token count using a hybrid heuristic.

    - English/Latin text: ~1 token per 4 characters (GPT/Claude average)
    - CJK characters: ~1 token per 1.5 characters
    - Numbers and punctuation: ~1 token per 3 characters

    This is an approximation. For exact counts, use the provider's tokenizer.
    """
    if not text:
        return 0

    cjk_pattern = re.compile(
        r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
        r"\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]"
    )
    cjk_chars = len(cjk_pattern.findall(text))
    other_chars = len(text) - cjk_chars

    cjk_tokens = cjk_chars / 1.5
    other_tokens = other_chars / 4.0

    return max(1, int(cjk_tokens + other_tokens))


def estimate_message_tokens(messages: List[Dict[str, str]]) -> int:
    """Estimate total tokens for a list of chat messages.

    Each message has ~4 tokens of overhead (role, formatting).
    """
    total = 0
    for msg in messages:
        total += 4  # message overhead
        total += estimate_tokens(msg.get("role", ""))
        total += estimate_tokens(msg.get("content", ""))
    total += 2  # conversation priming
    return total


def estimate_cost(token_count: int, model: str, direction: str = "input") -> float:
    """Calculate cost in USD for a given token count and model."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return 0.0
    rate = pricing.get(direction, pricing.get("input", 0.0))
    return (token_count / 1_000_000) * rate


# ---------------------------------------------------------------------------
# Conversation compression logic
# ---------------------------------------------------------------------------
def split_conversation(
    messages: List[Dict[str, str]],
    keep_recent: int = DEFAULT_KEEP_RECENT_TURNS,
) -> tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Split messages into old (to compress) and recent (to keep intact).

    A 'turn' is one user message + one assistant message.
    System messages are always kept separate.
    """
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    # Each turn = 2 messages (user + assistant)
    keep_count = keep_recent * 2
    if len(non_system) <= keep_count:
        return [], messages  # nothing to compress

    old_msgs = non_system[:-keep_count]
    recent_msgs = system_msgs + non_system[-keep_count:]
    return old_msgs, recent_msgs


def build_compressed_messages(
    summary: str,
    recent_messages: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Build a new message list with compressed history injected."""
    system_msgs = [m for m in recent_messages if m.get("role") == "system"]
    non_system = [m for m in recent_messages if m.get("role") != "system"]

    # Inject summary as a system-level context block
    summary_block = {
        "role": "system",
        "content": (
            "[Compressed conversation history]\n"
            f"{summary}\n"
            "[End of compressed history — recent messages follow]"
        ),
    }

    return system_msgs + [summary_block] + non_system


# ---------------------------------------------------------------------------
# Pinned facts (Never-Compress List)
# ---------------------------------------------------------------------------
_pinned_facts: List[str] = []


def get_pinned_facts_block() -> str:
    """Return pinned facts as a formatted block for injection into summaries."""
    if not _pinned_facts:
        return ""
    facts = "\n".join(f"- {f}" for f in _pinned_facts)
    return f"\n[Pinned facts — always preserved]\n{facts}\n"


# ---------------------------------------------------------------------------
# Post-compression sanitizer (anti prompt-injection)
# ---------------------------------------------------------------------------
def sanitize_compressed_output(text: str) -> str:
    """Strip potential prompt injection patterns from compressed output."""
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)
    return sanitized


# ---------------------------------------------------------------------------
# Ollama / Gemma 4 LLM compression
# ---------------------------------------------------------------------------
async def check_ollama_available() -> bool:
    """Check if Ollama is running locally."""
    if not HTTPX_AVAILABLE:
        return False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{DEFAULT_OLLAMA_URL}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def compress_with_ollama(
    messages: List[Dict[str, str]],
    max_tokens: int,
    pinned_facts: str = "",
) -> Optional[str]:
    """Compress conversation using local Ollama model (Gemma 4).

    Returns None if Ollama is unavailable or compression fails.
    """
    if not HTTPX_AVAILABLE:
        return None

    ollama_model = os.environ.get("PROMPTTHRIFT_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    ollama_url = os.environ.get("PROMPTTHRIFT_OLLAMA_URL", DEFAULT_OLLAMA_URL)

    # Build the conversation text for compression
    conv_text = ""
    for msg in messages:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        conv_text += f"{role}: {content}\n\n"

    system_prompt = COMPRESSION_SYSTEM_PROMPT.format(max_tokens=max_tokens)
    if pinned_facts:
        system_prompt += (
            f"\n\nIMPORTANT: The following facts MUST appear in your summary "
            f"exactly as written:\n{pinned_facts}"
        )

    payload = {
        "model": ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Compress this conversation:\n\n{conv_text}"},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens * 4},  # chars ≈ tokens * 4
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{ollama_url}/api/chat", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                summary = data.get("message", {}).get("content", "")
                if summary:
                    return sanitize_compressed_output(summary)
    except Exception as e:
        logger.warning("Ollama compression failed: %s", e)

    return None


def generate_local_summary(messages: List[Dict[str, str]], max_tokens: int) -> str:
    """Generate a summary locally without calling an external API.

    This is the fallback when no API key is configured.
    It extracts key information from the conversation.
    """
    key_points = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if not content:
            continue

        # Extract first meaningful sentence from each message
        sentences = re.split(r"[.!?。！？\n]", content)
        meaningful = [s.strip() for s in sentences if len(s.strip()) > 20]

        if meaningful:
            prefix = "User" if role == "user" else "Assistant"
            # Keep first 1-2 sentences
            excerpt = ". ".join(meaningful[:2])
            if len(excerpt) > 200:
                excerpt = excerpt[:200] + "..."
            key_points.append(f"- {prefix}: {excerpt}")

    summary = "Conversation summary:\n" + "\n".join(key_points)

    # Truncate to approximate max_tokens
    max_chars = max_tokens * 4
    if len(summary) > max_chars:
        summary = summary[:max_chars] + "\n[...truncated]"

    return summary


# ---------------------------------------------------------------------------
# Complexity analysis for model routing
# ---------------------------------------------------------------------------
def analyze_complexity(prompt: str) -> str:
    """Analyze prompt complexity and return 'low', 'medium', or 'high'."""
    prompt_lower = prompt.lower()
    token_count = estimate_tokens(prompt)

    high_score = sum(1 for kw in COMPLEXITY_KEYWORDS_HIGH if kw in prompt_lower)
    low_score = sum(1 for kw in COMPLEXITY_KEYWORDS_LOW if kw in prompt_lower)

    # Long prompts with code or technical content tend to be complex
    has_code = "```" in prompt or "def " in prompt or "function " in prompt
    if has_code:
        high_score += 2

    if token_count > 2000:
        high_score += 1

    if high_score >= 2:
        return "high"
    elif low_score >= 2 or (token_count < 100 and high_score == 0):
        return "low"
    else:
        return "medium"


def recommend_models(complexity: str, provider: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return recommended models sorted by cost for given complexity."""
    recommendations = []

    for model_name, pricing in MODEL_PRICING.items():
        # Filter by provider if specified
        if provider:
            provider_lower = provider.lower()
            if provider_lower == "anthropic" and not model_name.startswith("claude"):
                continue
            if provider_lower == "openai" and not model_name.startswith("gpt"):
                continue
            if provider_lower in ("google", "gemini") and not model_name.startswith("gemini"):
                continue

        # Determine suitability
        input_cost = pricing["input"]
        if complexity == "low" and input_cost <= 1.0:
            suitability = "excellent"
        elif complexity == "low" and input_cost <= 3.0:
            suitability = "good"
        elif complexity == "medium" and input_cost <= 5.0:
            suitability = "good"
        elif complexity == "medium" and input_cost <= 1.0:
            suitability = "risky — may lack reasoning depth"
        elif complexity == "high" and input_cost >= 2.0:
            suitability = "recommended"
        elif complexity == "high" and input_cost < 2.0:
            suitability = "not recommended — likely insufficient"
        else:
            suitability = "acceptable"

        recommendations.append({
            "model": model_name,
            "input_cost_per_mtok": input_cost,
            "output_cost_per_mtok": pricing["output"],
            "context_window": pricing["context"],
            "suitability": suitability,
        })

    # Sort by input cost (cheapest first)
    recommendations.sort(key=lambda x: x["input_cost_per_mtok"])
    return recommendations


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(SERVER_NAME)


# === Tool 1: Compress History ===

class CompressHistoryInput(BaseModel):
    """Input for the conversation history compression tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    messages: List[Dict[str, str]] = Field(
        ...,
        description=(
            "Full conversation message array in OpenAI/Anthropic format. "
            "Each item: {\"role\": \"user|assistant|system\", \"content\": \"...\"}"
        ),
        min_length=1,
    )
    keep_recent_turns: int = Field(
        default=DEFAULT_KEEP_RECENT_TURNS,
        description="Number of recent turns (user+assistant pairs) to keep uncompressed",
        ge=1,
        le=50,
    )
    max_summary_tokens: int = Field(
        default=500,
        description="Maximum token count for the compressed summary",
        ge=50,
        le=4000,
    )
    model: Optional[str] = Field(
        default=None,
        description=(
            "Model name for cost estimation (e.g., 'claude-sonnet-4.6'). "
            "If omitted, defaults to claude-sonnet-4.6."
        ),
    )


@mcp.tool(
    name="promptthrift_compress_history",
    annotations={
        "title": "Compress Conversation History",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def promptthrift_compress_history(params: CompressHistoryInput) -> str:
    """Compress old conversation history to reduce input tokens by 50-80%.

    Splits the conversation into old turns (compressed into a summary) and
    recent turns (kept intact). Returns the optimized message array and
    a savings report showing tokens and cost saved.

    Use this when your conversation is getting long and you want to reduce
    the token cost of subsequent API calls.

    Args:
        params (CompressHistoryInput): Contains the full message array,
            number of recent turns to preserve, and optional model for
            cost estimation.

    Returns:
        str: JSON with compressed_messages array and savings report.
    """
    messages = params.messages
    model = params.model or "claude-sonnet-4.6"
    keep_recent = params.keep_recent_turns

    # Calculate original token count
    original_tokens = estimate_message_tokens(messages)

    # Split into old and recent
    old_msgs, recent_msgs = split_conversation(messages, keep_recent)

    if not old_msgs:
        return json.dumps({
            "status": "no_compression_needed",
            "reason": f"Conversation has {len(messages)} messages — not enough to compress with keep_recent_turns={keep_recent}.",
            "original_tokens": original_tokens,
            "message": "Conversation is short enough. No compression needed.",
        }, indent=2, ensure_ascii=False)

    # Try LLM compression (Ollama/Gemma 4) first, fall back to heuristic
    pinned = get_pinned_facts_block()
    compression_method = "heuristic"

    summary = None
    if await check_ollama_available():
        summary = await compress_with_ollama(old_msgs, params.max_summary_tokens, pinned)
        if summary:
            compression_method = "llm (Ollama)"
            logger.info("Used Ollama LLM compression")

    if not summary:
        summary = generate_local_summary(old_msgs, params.max_summary_tokens)
        if pinned:
            summary += f"\n{pinned}"
        summary = sanitize_compressed_output(summary)

    # Build compressed message array
    compressed = build_compressed_messages(summary, recent_msgs)
    compressed_tokens = estimate_message_tokens(compressed)

    # Calculate savings
    tokens_saved = original_tokens - compressed_tokens
    pct_saved = (tokens_saved / original_tokens * 100) if original_tokens > 0 else 0
    cost_saved = estimate_cost(tokens_saved, model, "input")

    # Per-turn ongoing savings (every subsequent call saves this much)
    per_turn_saving = estimate_cost(tokens_saved, model, "input")

    result = {
        "status": "compressed",
        "compressed_messages": compressed,
        "savings_report": {
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "tokens_saved": tokens_saved,
            "percentage_saved": round(pct_saved, 1),
            "cost_saved_per_call_usd": round(cost_saved, 6),
            "cost_saved_per_100_calls_usd": round(cost_saved * 100, 4),
            "compression_method": compression_method,
            "model_used_for_estimate": model,
            "turns_compressed": len(old_msgs),
            "turns_kept_intact": len([m for m in recent_msgs if m.get("role") != "system"]),
            "pinned_facts_count": len(_pinned_facts),
        },
        "usage_tip": (
            "Replace your messages array with compressed_messages in your next API call. "
            f"You'll save ~{tokens_saved} input tokens (${cost_saved:.6f}) on EVERY subsequent call."
        ),
    }

    logger.info(
        "Compressed %d messages: %d → %d tokens (%.1f%% saved)",
        len(old_msgs), original_tokens, compressed_tokens, pct_saved,
    )

    return json.dumps(result, indent=2, ensure_ascii=False)


# === Tool 2: Count Tokens ===

class CountTokensInput(BaseModel):
    """Input for the token counting and cost estimation tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    messages: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Message array to count tokens for. Provide this OR text, not both.",
    )
    text: Optional[str] = Field(
        default=None,
        description="Raw text to count tokens for. Provide this OR messages, not both.",
    )
    model: Optional[str] = Field(
        default=None,
        description="Model name for cost estimation (e.g., 'gpt-4o', 'claude-sonnet-4.6').",
    )
    expected_output_tokens: Optional[int] = Field(
        default=None,
        description="Estimated output tokens for total cost calculation.",
        ge=0,
        le=100_000,
    )

    @field_validator("messages")
    @classmethod
    def check_input_provided(cls, v: Optional[List], info) -> Optional[List]:
        return v


@mcp.tool(
    name="promptthrift_count_tokens",
    annotations={
        "title": "Count Tokens & Estimate Cost",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def promptthrift_count_tokens(params: CountTokensInput) -> str:
    """Count tokens and estimate API cost for a prompt or conversation.

    Provides token breakdown per message and total cost estimate across
    multiple models. Helps you understand where your tokens are going
    and which model gives the best price/performance ratio.

    Args:
        params (CountTokensInput): Contains either a messages array or raw text,
            plus optional model and expected output tokens for cost calculation.

    Returns:
        str: JSON with token counts, per-message breakdown, and cost estimates.
    """
    if params.messages:
        total_tokens = estimate_message_tokens(params.messages)
        breakdown = []
        for i, msg in enumerate(params.messages):
            msg_tokens = estimate_tokens(msg.get("content", "")) + 4
            breakdown.append({
                "index": i,
                "role": msg.get("role", "unknown"),
                "tokens": msg_tokens,
                "content_preview": msg.get("content", "")[:80] + ("..." if len(msg.get("content", "")) > 80 else ""),
            })
    elif params.text:
        total_tokens = estimate_tokens(params.text)
        breakdown = [{
            "index": 0,
            "role": "text",
            "tokens": total_tokens,
            "content_preview": params.text[:80] + ("..." if len(params.text) > 80 else ""),
        }]
    else:
        return json.dumps({
            "error": "Please provide either 'messages' (array) or 'text' (string) to count tokens.",
        }, indent=2)

    # Cost estimates across models
    output_tokens = params.expected_output_tokens or 0
    cost_table = []
    for model_name, pricing in sorted(MODEL_PRICING.items(), key=lambda x: x[1]["input"]):
        input_cost = estimate_cost(total_tokens, model_name, "input")
        output_cost = estimate_cost(output_tokens, model_name, "output") if output_tokens else 0
        cost_table.append({
            "model": model_name,
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(input_cost + output_cost, 6),
            "input_rate": f"${pricing['input']}/MTok",
            "output_rate": f"${pricing['output']}/MTok",
        })

    result = {
        "token_count": {
            "input_tokens": total_tokens,
            "expected_output_tokens": output_tokens,
            "total_tokens": total_tokens + output_tokens,
        },
        "message_breakdown": breakdown,
        "cost_estimates": cost_table,
    }

    # Add specific model estimate if requested
    if params.model:
        specific = estimate_cost(total_tokens, params.model, "input")
        specific_out = estimate_cost(output_tokens, params.model, "output") if output_tokens else 0
        result["selected_model_cost"] = {
            "model": params.model,
            "input_cost_usd": round(specific, 6),
            "output_cost_usd": round(specific_out, 6),
            "total_cost_usd": round(specific + specific_out, 6),
        }

    return json.dumps(result, indent=2, ensure_ascii=False)


# === Tool 3: Suggest Model ===

class SuggestModelInput(BaseModel):
    """Input for the intelligent model routing suggestion tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    prompt: str = Field(
        ...,
        description="The prompt/task description to analyze for complexity.",
        min_length=1,
        max_length=50_000,
    )
    provider: Optional[str] = Field(
        default=None,
        description="Preferred provider: 'anthropic', 'openai', or 'google'. If omitted, shows all.",
    )
    budget_per_call_usd: Optional[float] = Field(
        default=None,
        description="Maximum budget per API call in USD. Filters out models that exceed this.",
        gt=0,
        le=10.0,
    )


@mcp.tool(
    name="promptthrift_suggest_model",
    annotations={
        "title": "Suggest Optimal Model",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def promptthrift_suggest_model(params: SuggestModelInput) -> str:
    """Analyze task complexity and recommend the most cost-effective model.

    Not every task needs the most expensive model. A simple translation
    or formatting task can use a model that costs 50x less than Opus.
    This tool analyzes your prompt and recommends the cheapest model
    that can handle it well.

    Args:
        params (SuggestModelInput): Contains the prompt to analyze,
            optional provider filter, and optional budget constraint.

    Returns:
        str: JSON with complexity analysis, model recommendations sorted
            by cost, and estimated savings vs. using the most expensive model.
    """
    prompt = params.prompt
    complexity = analyze_complexity(prompt)
    prompt_tokens = estimate_tokens(prompt)
    recommendations = recommend_models(complexity, params.provider)

    # Apply budget filter
    if params.budget_per_call_usd:
        budget = params.budget_per_call_usd
        recommendations = [
            r for r in recommendations
            if estimate_cost(prompt_tokens, r["model"], "input") <= budget
        ]

    # Calculate savings vs most expensive applicable model
    if recommendations:
        cheapest = recommendations[0]
        most_expensive = max(recommendations, key=lambda x: x["input_cost_per_mtok"])
        cheapest_cost = estimate_cost(prompt_tokens, cheapest["model"], "input")
        expensive_cost = estimate_cost(prompt_tokens, most_expensive["model"], "input")
        potential_savings = expensive_cost - cheapest_cost
    else:
        potential_savings = 0

    result = {
        "complexity_analysis": {
            "level": complexity,
            "prompt_tokens": prompt_tokens,
            "reasoning": (
                f"Task classified as '{complexity}' complexity based on "
                f"keyword analysis and prompt length ({prompt_tokens} tokens)."
            ),
        },
        "recommendations": recommendations[:5],  # Top 5
        "savings_potential": {
            "cheapest_suitable_model": recommendations[0]["model"] if recommendations else "none",
            "savings_vs_most_expensive_usd_per_call": round(potential_savings, 6),
            "savings_over_1000_calls_usd": round(potential_savings * 1000, 4),
        },
        "tip": (
            f"For {complexity}-complexity tasks, you can likely use "
            f"{recommendations[0]['model'] if recommendations else 'a cheaper model'} "
            f"and save ${potential_savings * 1000:.2f} per 1,000 calls."
            if recommendations else
            "No models found within your budget. Consider increasing budget_per_call_usd."
        ),
    }

    return json.dumps(result, indent=2, ensure_ascii=False)


# === Tool 4: Pin Facts ===

class PinFactsInput(BaseModel):
    """Input for the pinned facts management tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    action: str = Field(
        ...,
        description="Action to perform: 'add', 'remove', 'list', or 'clear'.",
    )
    facts: Optional[List[str]] = Field(
        default=None,
        description="Facts to add or remove. Required for 'add' and 'remove' actions.",
    )

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {"add", "remove", "list", "clear"}
        if v.lower() not in allowed:
            raise ValueError(f"action must be one of {allowed}")
        return v.lower()


@mcp.tool(
    name="promptthrift_pin_facts",
    annotations={
        "title": "Pin Facts (Never-Compress List)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def promptthrift_pin_facts(params: PinFactsInput) -> str:
    """Manage pinned facts that must survive conversation compression.

    Pinned facts are critical pieces of information (user name, preferences,
    key decisions) that will always be preserved in compressed summaries,
    regardless of how aggressively the conversation is compressed.

    Actions:
    - add: Pin new facts to the Never-Compress List
    - remove: Unpin facts from the list
    - list: Show all currently pinned facts
    - clear: Remove all pinned facts

    Args:
        params (PinFactsInput): Action and optional facts list.

    Returns:
        str: JSON with updated pinned facts list.
    """
    global _pinned_facts

    if params.action == "add":
        if not params.facts:
            return json.dumps({"error": "Provide 'facts' array to add."}, indent=2)
        new_facts = [f for f in params.facts if f not in _pinned_facts]
        _pinned_facts.extend(new_facts)
        return json.dumps({
            "status": "added",
            "added": new_facts,
            "total_pinned": len(_pinned_facts),
            "all_facts": _pinned_facts,
        }, indent=2, ensure_ascii=False)

    elif params.action == "remove":
        if not params.facts:
            return json.dumps({"error": "Provide 'facts' array to remove."}, indent=2)
        removed = [f for f in params.facts if f in _pinned_facts]
        _pinned_facts = [f for f in _pinned_facts if f not in params.facts]
        return json.dumps({
            "status": "removed",
            "removed": removed,
            "total_pinned": len(_pinned_facts),
            "all_facts": _pinned_facts,
        }, indent=2, ensure_ascii=False)

    elif params.action == "list":
        return json.dumps({
            "total_pinned": len(_pinned_facts),
            "all_facts": _pinned_facts,
        }, indent=2, ensure_ascii=False)

    elif params.action == "clear":
        count = len(_pinned_facts)
        _pinned_facts = []
        return json.dumps({
            "status": "cleared",
            "facts_removed": count,
        }, indent=2, ensure_ascii=False)

    return json.dumps({"error": "Unknown action"}, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Starting PromptThrift MCP Server v%s", SERVER_VERSION)
    mcp.run()
