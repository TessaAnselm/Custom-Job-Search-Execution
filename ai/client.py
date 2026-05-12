"""
Unified AI client — pick your provider via AI_PROVIDER env var.

Supported providers:
  gemini     → Google Gemini (free tier available via AI Studio)
  anthropic  → Anthropic Claude
  groq       → Groq (free tier, fast open-source models)
  openai     → OpenAI GPT
  ollama     → Local models via Ollama (completely free, no API key)

Set in .env:
  AI_PROVIDER=gemini
  GOOGLE_API_KEY=...          # for gemini
  ANTHROPIC_API_KEY=...       # for anthropic
  GROQ_API_KEY=...            # for groq
  OPENAI_API_KEY=...          # for openai
  OLLAMA_MODEL=llama3         # for ollama (default: llama3)
"""

import os


def _provider() -> str:
    return os.getenv("AI_PROVIDER", "openai").lower()


# ── Async (used by scorer, resume tailor, cover note) ────────────────────

async def complete_async(prompt: str, max_tokens: int = 600) -> str:
    p = _provider()

    if p == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        model = genai.GenerativeModel(
            os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            generation_config={"max_output_tokens": max_tokens},
        )
        response = await model.generate_content_async(prompt)
        return response.text.strip()

    if p == "anthropic":
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = await client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    if p == "groq":
        from groq import AsyncGroq
        client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
        resp = await client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    if p == "ollama":
        import ollama
        model = os.getenv("OLLAMA_MODEL", "llama3")
        response = ollama.generate(model=model, prompt=prompt)
        return response["response"].strip()

    # Default: openai
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = await client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ── Sync (used by app.py profile extraction) ─────────────────────────────

def complete_sync(prompt: str, max_tokens: int = 800) -> str:
    p = _provider()

    if p == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        model = genai.GenerativeModel(
            os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            generation_config={"max_output_tokens": max_tokens},
        )
        return model.generate_content(prompt).text.strip()

    if p == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()

    if p == "groq":
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        resp = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    if p == "ollama":
        import ollama
        model = os.getenv("OLLAMA_MODEL", "llama3")
        return ollama.generate(model=model, prompt=prompt)["response"].strip()

    # Default: openai
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()
