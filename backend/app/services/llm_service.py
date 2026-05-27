from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a cybersecurity analyst assistant integrated into a cross-layer "
    "anomaly detection system. The system monitors three layers:\n"
    "  • system — BGL kernel/hardware logs\n"
    "  • network — CICIDS-2017 network traffic flows\n"
    "  • application — TDA database access logs\n\n"
    "Analyze the provided data and give clear, concise, actionable insights. "
    "Be technical but accessible. Use bullet points where helpful."
)

def _http_post(url: str, payload: dict, headers: dict, timeout: int = 90) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from LLM API: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach LLM endpoint ({url}): {exc.reason}") from exc

def _stream_openai_compat(url: str, headers: dict, payload: dict):
    data = json.dumps({**payload, "stream": True}).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                chunk_str = line[5:].strip()
                if chunk_str == "[DONE]":
                    return
                try:
                    chunk = json.loads(chunk_str)
                    delta = chunk["choices"][0]["delta"].get("content") or ""
                    if delta:
                        yield delta
                except Exception:
                    pass
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from LLM API: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach LLM endpoint: {exc.reason}") from exc

def _call_anthropic(system: str, prompt: str, max_tokens: int, api_key: str) -> str:
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to backend/.env or switch to a free provider: "
            "LLM_PROVIDER=groq  or  LLM_PROVIDER=ollama"
        )
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic") from exc

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except anthropic.AuthenticationError as exc:
        raise RuntimeError("Invalid ANTHROPIC_API_KEY. Check backend/.env.") from exc
    except anthropic.BadRequestError as exc:
        msg = str(exc)
        if "credit balance" in msg or "billing" in msg.lower():
            raise RuntimeError(
                "Insufficient Anthropic credits. "
                "Go to console.anthropic.com/settings/billing — or switch to a free provider: "
                "set LLM_PROVIDER=groq or LLM_PROVIDER=ollama in backend/.env"
            ) from exc
        raise

def _call_groq(system: str, prompt: str, max_tokens: int, api_key: str, model: str) -> str:
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. "
            "Sign up free at console.groq.com, copy your key, then add to backend/.env: "
            "GROQ_API_KEY=gsk_..."
        )
    result = _http_post(
        "https://api.groq.com/openai/v1/chat/completions",
        payload={
            "model": model or "llama3-70b-8192",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return result["choices"][0]["message"]["content"]

def _call_ollama(system: str, prompt: str, base_url: str, model: str) -> str:
    base_url = (base_url or "http://localhost:11434").rstrip("/")
    result = _http_post(
        f"{base_url}/api/chat",
        payload={
            "model": model or "llama3",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        },
        headers={},
        timeout=180,
    )
    return result["message"]["content"]

def _call_openai(system: str, prompt: str, max_tokens: int, api_key: str, model: str) -> str:
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Get a key at platform.openai.com, then add to backend/.env:\n"
            "  OPENAI_API_KEY=sk-...\n"
            "  LLM_PROVIDER=openai"
        )
    result = _http_post(
        "https://api.openai.com/v1/chat/completions",
        payload={
            "model": model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            "max_tokens": max_tokens,
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected OpenAI response: {result}") from exc

def _call_gemini(prompt: str, system: str, max_tokens: int, api_key: str, model: str) -> str:
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Get a free key at aistudio.google.com (no credit card needed), then add to backend/.env: "
            "GEMINI_API_KEY=AIza..."
        )
    model = model or "gemini-1.5-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    result = _http_post(
        url,
        payload={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        },
        headers={},
    )
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {result}") from exc

def _build_dataset_context(db) -> str:
    if db is None:
        return ""
    try:
        from sqlalchemy import text
        row = db.execute(text("""
            SELECT (SELECT COUNT(1) FROM log_events)               AS total_logs,
                   (SELECT COUNT(1) FROM log_events WHERE label=1) AS total_anomalies,
                   (SELECT COUNT(1) FROM incidents)                AS total_incidents
        """)).fetchone()
        src = db.execute(text(
            "SELECT source, COUNT(1) AS n, SUM(CASE WHEN label=1 THEN 1 ELSE 0 END) AS a "
            "FROM log_events WHERE source IS NOT NULL GROUP BY source ORDER BY n DESC LIMIT 10"
        )).fetchall()
        sev = db.execute(text(
            "SELECT severity, COUNT(1) FROM incidents GROUP BY severity ORDER BY COUNT(1) DESC"
        )).fetchall()

        lines = [
            "## Live dataset statistics",
            f"- Total log events : {row[0]:,}",
            f"- Anomalous events : {row[1]:,} ({round(row[1]/row[0]*100,1) if row[0] else 0}%)",
            f"- Total incidents  : {row[2]:,}",
            "",
            "**Per-source breakdown:**",
        ]
        for r in src:
            rate = round(r[2] / r[1] * 100, 1) if r[1] else 0
            lines.append(f"  • {r[0]}: {r[1]:,} events, {r[2]:,} anomalies ({rate}%)")
        if sev:
            lines.append("")
            lines.append("**Incidents by severity:** " +
                         ", ".join(f"{r[0] or 'unknown'}: {r[1]}" for r in sev))
        return "\n".join(lines)
    except Exception:
        return ""

def _call_llm(system: str, prompt: str, max_tokens: int = 1024, db=None) -> str:
    from ..config import get_settings
    s = get_settings()
    provider = (s.LLM_PROVIDER or "local").lower()

    if provider == "local":
        from .local_assistant import answer as local_answer
        return local_answer(prompt, db=db)

    ctx = _build_dataset_context(db)
    enriched_system = system + ("\n\n" + ctx if ctx else "")

    if provider == "openai":
        return _call_openai(enriched_system, prompt, max_tokens, s.OPENAI_API_KEY, s.OPENAI_MODEL)
    elif provider == "gemini":
        return _call_gemini(prompt, enriched_system, max_tokens, s.GEMINI_API_KEY, s.GEMINI_MODEL)
    elif provider == "groq":
        return _call_groq(enriched_system, prompt, max_tokens, s.GROQ_API_KEY, s.GROQ_MODEL)
    elif provider == "ollama":
        return _call_ollama(enriched_system, prompt, s.OLLAMA_BASE_URL, s.OLLAMA_MODEL)
    elif provider == "anthropic":
        return _call_anthropic(enriched_system, prompt, max_tokens, s.ANTHROPIC_API_KEY)
    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER '{provider}'. "
            "Valid values: local | openai | gemini | groq | ollama | anthropic"
        )

def explain_incident(incident: Dict[str, Any], events: List[Dict[str, Any]], db=None) -> str:
    event_count = len(events)
    sample_messages = "\n".join(
        f"  [{e.get('layer','?')}] {e.get('message','')[:120]}"
        for e in events[:6]
        if e.get("message")
    )

    prompt = (
        "Analyze this cross-layer security incident and explain what happened:\n\n"
        f"**Incident:**\n"
        f"- Severity: {incident.get('severity', 'unknown')}\n"
        f"- Entity: {incident.get('entity', 'N/A')}\n"
        f"- Layers involved: {', '.join(incident.get('sources', [])) or 'N/A'}\n"
        f"- Start: {incident.get('start_time', 'unknown')}\n"
        f"- End: {incident.get('end_time', 'unknown')}\n"
        f"- Events: {incident.get('event_count', event_count)} total, "
        f"{incident.get('anomaly_count', '?')} flagged anomalous\n"
        f"- Description: {incident.get('description', 'N/A')}\n\n"
    )
    if sample_messages:
        prompt += f"**Sample log messages ({min(6, event_count)} of {event_count}):**\n{sample_messages}\n\n"

    prompt += (
        "Provide:\n"
        "1. **What happened** — 1-2 sentence summary\n"
        "2. **Key indicators** — why this pattern is suspicious\n"
        "3. **Recommended actions** — 2-3 immediate steps\n"
        "4. **Risk assessment** — Low / Medium / High / Critical with justification"
    )
    return _call_llm(_SYSTEM_PROMPT, prompt, max_tokens=1024, db=db)

_SOURCE_CONTEXT = {
    "bgl": (
        "BGL (Blue Gene/L) system logs — each record is a kernel/hardware event on a supercomputer node. "
        "Feature fields capture component IDs, event types, node coordinates, and message severity. "
        "Anomalies typically represent hardware faults, memory errors (ECC/parity), node failures, "
        "kernel panics, or thermal events."
    ),
    "cicids": (
        "CICIDS-2017 network flow dataset — each record is a bidirectional TCP/UDP flow summarised "
        "into statistical features: byte counts, packet counts, inter-arrival times, flag counts, "
        "flow duration, and derived rates (Bytes/s, Packets/s). "
        "Anomalies are labelled attack flows including DDoS, DoS, port scans, brute-force, "
        "botnet C&C, infiltration, and web attacks."
    ),
    "tda": (
        "TDA (Threat Detection Analytics) database-access logs — each record captures a session's "
        "query behaviour: tables accessed, query types (SELECT/INSERT/DELETE), row counts, "
        "access frequency, and user/application context. "
        "Anomalies represent SQL injection attempts, privilege escalation, bulk data exfiltration, "
        "or unusual access patterns."
    ),
}

def _source_context(source: str) -> str:
    key = (source or "").lower().replace("-", "").replace("2017", "")
    for k, v in _SOURCE_CONTEXT.items():
        if k in key:
            return v
    return f"Source: {source}"

def _format_features(features: Dict[str, Any], max_items: int = 20) -> str:
    if not features:
        return ""
    numeric = [(k, v) for k, v in features.items() if isinstance(v, (int, float))]
    numeric.sort(key=lambda x: abs(x[1]), reverse=True)
    lines = []
    for k, v in numeric[:max_items]:
        if isinstance(v, float):
            lines.append(f"  {k}: {v:.6g}")
        else:
            lines.append(f"  {k}: {v:,}")
    non_numeric = [(k, v) for k, v in features.items() if not isinstance(v, (int, float))]
    for k, v in non_numeric[:5]:
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)

def explain_log_event(log: Dict[str, Any], db=None,
                      extra_signals: Optional[List[str]] = None) -> str:
    source      = log.get("source", "unknown")
    layer       = log.get("layer",  "unknown")
    confidence  = log.get("confidence")
    raw_text    = str(log.get("raw") or "")[:800]
    message     = str(log.get("message") or "")[:400]
    features    = log.get("features") or {}
    entity      = log.get("entity") or "N/A"
    timestamp   = log.get("timestamp", "unknown")

    conf_str = f"{round(confidence * 100, 1)}%" if confidence is not None else "unknown"
    features_str = _format_features(features)

    signals_str = ""
    if extra_signals:
        signals_str = "\n".join(f"  • {s}" for s in extra_signals)
        signals_str = f"\nPRE-DETECTED HEURISTIC SIGNALS (from rule engine):\n{signals_str}\n"

    prompt = (
        "You are a cybersecurity analyst. Below is a SINGLE log event that the ML anomaly "
        "detection model flagged. Your job is to explain exactly WHY THIS SPECIFIC EVENT "
        "is anomalous by referencing its actual values — do NOT give generic advice.\n\n"

        f"SOURCE CONTEXT:\n{_source_context(source)}\n\n"

        f"EVENT DETAILS:\n"
        f"  ID        : {log.get('id', '?')}\n"
        f"  Layer     : {layer}\n"
        f"  Source    : {source}\n"
        f"  Timestamp : {timestamp}\n"
        f"  Entity    : {entity}\n"
        f"  ML verdict: ANOMALY  (model confidence: {conf_str})\n"
    )

    if raw_text:
        prompt += f"\nRAW LOG CONTENT:\n  {raw_text}\n"
    if message and message != raw_text:
        prompt += f"\nPARSED MESSAGE:\n  {message}\n"
    if features_str:
        prompt += (
            f"\nFEATURE VALUES (sorted by magnitude — highest = most unusual):\n"
            f"{features_str}\n"
        )
    if signals_str:
        prompt += signals_str

    prompt += (
        "\nNow answer these four questions — be SPECIFIC, cite actual values from above:\n\n"
        "1. **Root cause** — Which exact feature values or keywords make this event anomalous? "
        "Quote the values and explain why they deviate from normal (e.g. 'Flow Bytes/s of 2.5M "
        "is ~1000× higher than benign traffic average of ~2K').\n\n"
        "2. **Attack / failure pattern** — Given these exact indicators, what specific threat or "
        "failure does this most likely represent? Name the attack type or fault category.\n\n"
        "3. **Severity verdict** — Rate as Critical / High / Medium / Low with one sentence "
        "justification tied to the values you saw.\n\n"
        "4. **Immediate action** — One concrete step the analyst should take RIGHT NOW based on "
        "this specific event (e.g. 'Block source IP 192.168.x.x', 'Isolate node BG/L-R00-M0-N04')."
    )

    return _call_llm(_SYSTEM_PROMPT, prompt, max_tokens=900, db=db)

def chat(question: str, db=None) -> str:
    extended_system = (
        _SYSTEM_PROMPT
        + "\n\nYou can answer questions about:\n"
        "  • How anomaly detection works in each layer\n"
        "  • Interpreting ML metrics (precision, recall, F1, FPR)\n"
        "  • Common attack patterns in BGL / CICIDS / TDA data\n"
        "  • How to reduce false positives\n"
        "  • Cross-layer correlation and incident triage\n"
        "  • General cybersecurity best practices\n\n"
        "If you don't have enough context, ask for clarification."
    )
    return _call_llm(extended_system, question, max_tokens=1024, db=db)

def stream_chat(question: str, db=None):
    from ..config import get_settings
    s = get_settings()
    provider = (s.LLM_PROVIDER or "local").lower()

    extended_system = (
        _SYSTEM_PROMPT
        + "\n\nYou can answer questions about:\n"
        "  • How anomaly detection works in each layer\n"
        "  • Interpreting ML metrics (precision, recall, F1, FPR)\n"
        "  • Common attack patterns in BGL / CICIDS / TDA data\n"
        "  • How to reduce false positives\n"
        "  • Cross-layer correlation and incident triage\n"
        "  • General cybersecurity best practices\n\n"
        "If you don't have enough context, ask for clarification."
    )

    if provider in ("groq", "openai"):
        ctx = _build_dataset_context(db)
        system = extended_system + ("\n\n" + ctx if ctx else "")

        if provider == "groq":
            if not s.GROQ_API_KEY:
                raise RuntimeError("GROQ_API_KEY not set in backend/.env")
            yield from _stream_openai_compat(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {s.GROQ_API_KEY}"},
                payload={
                    "model": s.GROQ_MODEL or "llama3-70b-8192",
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
                    "max_tokens": 1024,
                },
            )
        else:
            if not s.OPENAI_API_KEY:
                raise RuntimeError("OPENAI_API_KEY not set in backend/.env")
            yield from _stream_openai_compat(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {s.OPENAI_API_KEY}"},
                payload={
                    "model": s.OPENAI_MODEL or "gpt-4o-mini",
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
                    "max_tokens": 1024,
                },
            )
    else:
        yield chat(question, db=db)
