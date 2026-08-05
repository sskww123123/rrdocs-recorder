"""
analyzer.py
MeetingAnalyzer – Pydantic structured Ollama pipeline.

Stage 1 (TextBlob) – fast, offline sentiment + phrase count
Stage 2 (Ollama)   – deep LLM extraction using Pydantic schema to guarantee JSON format.
                     Acts as a 3-way model: 
                     1. Error corrector (texto_corregido)
                     2. Analyzer (conceptos, resumen, sesgos)
                     3. Action Items (tareas_acciones)
"""

import re
import json
import sys
import types
from pydantic import BaseModel, Field

from textblob import TextBlob #type: ignore
import ollama #type: ignore

# ---------------------------------------------------------------------------
# cgi shim (keeps any legacy httpx-based code from crashing on Python 3.11+)
# ---------------------------------------------------------------------------
if "cgi" not in sys.modules:
    _cgi = types.ModuleType("cgi")
    def _parse_header(line):
        parts = [p.strip() for p in line.split(";")]
        key   = parts[0]
        pdict = {}
        for part in parts[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                pdict[k.strip().lower()] = v.strip().strip('"')
        return key, pdict
    _cgi.parse_header = _parse_header # type: ignore
    sys.modules["cgi"] = _cgi

# ---------------------------------------------------------------------------
# Pydantic Schema for Guaranteed JSON Output
# ---------------------------------------------------------------------------
class MeetingAnalysisSchema(BaseModel):
    texto_corregido: list[str] = Field(
        description=(
            "La transcripción pulida dividida en párrafos. "
            "INSTRUCCIONES DE CORRECCIÓN DE AUDIO:\n"
            "1. Arregla confusiones fonéticas típicas de Whisper en diseño, proyectos y tecnología:\n"
            "   - 'sábila' / 'sabia' -> 'metodología Ágil (Agile)'\n"
            "   - 'variación' -> 'validación'\n"
            "   - 'afectos' -> 'aspectos'\n"
            "   - Conserva términos como: stakeholders, entregables, mapa de actores, retos, síntesis.\n"
            "2. RESPETO A LA ORALIDAD:\n"
            "   - NO modifiques la voz del hablante ni cambies pronombres válidos ('yo', 'ustedes').\n"
            "   - NO fuerces verbos a infinitivo si el hablante los usó en presente o pasado."
        )
    )
    conceptos_principales: list[str] = Field(description="5 conceptos técnicos, nombres de proyectos, o ideas principales de la reunión. NUNCA palabras sueltas o conectores.")
    resumen_ejecutivo: list[str] = Field(description="Un resumen ejecutivo de 3 puntos clave.")
    sesgos_cognitivos: list[str] = Field(description="Sesgos cognitivos detectados en la conversación.")
    tareas_acciones: list[str] = Field(description="Tareas específicas o action items asignados a personas durante la reunión.")

# Model to use. Falls back through the list until one responds.
# Prioritize 2GB-3GB models that fit perfectly in a 4GB RTX 3050 Ti VRAM.
# Model to use. Falls back through the list until one responds.
# Prioritize 2GB-3GB models that fit perfectly in a 4GB RTX 3050 Ti VRAM.
_MODEL_PREFERENCE = [
    "phi4-mini",
    "kwangsuklee/Qwen3.5-4B.Q4_K_M-Claude-4.6-Opus-Reasoning-Distilled-v2",
    "llama3.2",
    "llama3.1",
    "llama3"
]

_OLLAMA_PROMPT_TEMPLATE = """\
Actúa como un restaurador de transcripciones y analizador experto de reuniones sobre diseño, tecnología y metodologías.
Analiza la siguiente transcripción y extrae EXACTAMENTE los campos solicitados en el esquema JSON.

REGLAS CRÍTICAS:
1. En 'texto_corregido', arregla las palabras mal interpretadas por el micrófono/Whisper (por ejemplo: 'sábila' -> 'metodología Ágil (Agile)', 'variación' -> 'validación', 'afectos' -> 'aspectos').
2. NO cambies la voz, modismos orales ni pronombres del hablante ('yo', 'ustedes').
3. Para 'conceptos_principales', extrae solo frases clave o proyectos, NUNCA conectores ni palabras sueltas.

Transcripción:
\"\"\"
{transcript}
\"\"\"
"""

class MeetingAnalyzer:
    def __init__(self, model: str | None = None):
        self._model: str | None = model

    def _resolve_model(self) -> str:
        if self._model:
            return self._model
        try:
            available = {m["name"] for m in ollama.list()["models"]} | {m["name"].split(":")[0] for m in ollama.list()["models"]}
            for candidate in _MODEL_PREFERENCE:
                if candidate in available:
                    self._model = candidate
                    print(f"[Analyzer] Using Ollama model: {candidate}")
                    return candidate
        except Exception as exc:
            print(f"[Analyzer] Could not list Ollama models: {exc}")
        self._model = _MODEL_PREFERENCE[0]
        return self._model

    def _textblob_metrics(self, texto: str) -> dict:
        blob          = TextBlob(texto)
        total_phrases = len(blob.sentences) #type: ignore
        sentiment     = blob.sentiment.polarity #type: ignore
        subjectivity  = blob.sentiment.subjectivity #type: ignore
        return {
            "sentiment":     round(sentiment, 4),
            "subjectivity":  round(subjectivity, 4),
            "total_phrases": total_phrases,
        }

    def analizar_contexto(self, texto: str) -> dict:
        _SAFE_DEFAULT = {
            "texto_corregido":       [],
            "conceptos_principales": [],
            "resumen_ejecutivo":     [],
            "sesgos_cognitivos":     [],
            "tareas_acciones":       []
        }
        if not texto or not texto.strip():
            return _SAFE_DEFAULT

        model  = self._resolve_model()
        prompt = _OLLAMA_PROMPT_TEMPLATE.format(transcript=texto.strip())

        print(f"[Analyzer] Sending transcript to Ollama [{model}] ({len(texto.split())} words)...")
        try:
            # Native Structured Outputs in Ollama >= 0.6.0
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format=MeetingAnalysisSchema.model_json_schema(),
                options={"temperature": 0.1}
            )
            raw_text = response["message"]["content"].strip()
            print(f"[DEBUG] Ollama raw output: {raw_text[:200]}...")
            
            # Since we passed a JSON schema, raw_text is guaranteed to be JSON
            parsed = json.loads(raw_text)
            return {
                "texto_corregido":       parsed.get("texto_corregido", []),
                "conceptos_principales": parsed.get("conceptos_principales", [])[:5],
                "resumen_ejecutivo":     parsed.get("resumen_ejecutivo",     [])[:3],
                "sesgos_cognitivos":     parsed.get("sesgos_cognitivos",     []),
                "tareas_acciones":       parsed.get("tareas_acciones",       [])
            }
        except Exception as exc:
            print(f"[Analyzer] Ollama call/parse failed: {exc}")
            return _SAFE_DEFAULT

    def analizar_reunion(self, texto_transcrito: str) -> dict:
        if not texto_transcrito or not texto_transcrito.strip():
            return {
                "sentiment":            0.0,
                "subjectivity":         0.0,
                "total_phrases":        0,
                "top_keywords":         [],
                "texto_corregido":      [],
                "conceptos_principales":[],
                "resumen_ejecutivo":    [],
                "sesgos_cognitivos":    [],
                "tareas_acciones":      [],
                "texto_original":       "",
            }

        metrics = self._textblob_metrics(texto_transcrito)
        llm_data = self.analizar_contexto(texto_transcrito)

        return {
            **metrics,
            "top_keywords":          llm_data.get("conceptos_principales", []),
            "texto_corregido":       llm_data.get("texto_corregido", []),
            "conceptos_principales": llm_data.get("conceptos_principales", []),
            "resumen_ejecutivo":     llm_data.get("resumen_ejecutivo", []),
            "sesgos_cognitivos":     llm_data.get("sesgos_cognitivos", []),
            "tareas_acciones":       llm_data.get("tareas_acciones", []),
            "texto_original":        texto_transcrito,
        }
