"""MetrôBot SP — API FastAPI.

A lanterna ilumina, o algoritmo decide: toda rota e toda inferência vêm de
core/. O Llama (Groq) só narra os fatos já calculados; sem chave ou com a
API fora do ar, a narração usa o texto offline determinístico.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import AsyncIterator, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from groq import AsyncGroq, GroqError
from pydantic import BaseModel, Field

from core import grafo, logica
from core.planejador import planejar

load_dotenv()

RAIZ = Path(__file__).parent
MODELO_PADRAO = "llama-3.3-70b-versatile"

app = FastAPI(title="MetrôBot SP — Subsolo SP", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

Algoritmo = Literal["bfs", "dfs", "ambos"]


class PedidoRota(BaseModel):
    origem: str
    destino: str
    bloqueadas: list[str] = Field(default_factory=list)
    algoritmo: Algoritmo = "ambos"


class PedidoInferencia(BaseModel):
    bloqueadas: list[str] = Field(default_factory=list)
    incluir_rede: bool = False


def _planejar(origem: str, destino: str, bloqueadas: list[str], algoritmo: str) -> dict:
    try:
        return planejar(origem, destino, bloqueadas, algoritmo)
    except grafo.EstacaoDesconhecida as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro


# ---------------------------------------------------------------- dados

@app.get("/api/estacoes")
def estacoes() -> dict:
    return {
        "linhas": [
            {"id": lid, "nome": d["nome"], "cor": d["cor"], "estacoes": d["estacoes"]}
            for lid, d in grafo.LINHAS.items()
        ],
        "hubs": grafo.HUBS,
        "estacoes": [grafo.dossie(e) for e in grafo.ESTACOES],
    }


@app.get("/api/locais")
def locais() -> dict:
    return {
        "pendente": True,
        "aviso": "Lista oficial do enunciado ainda não fornecida.",
        "locais": [{"nome": k, "estacao": v} for k, v in grafo.LOCAIS_CONHECIDOS.items()],
    }


@app.post("/api/rota")
def rota(pedido: PedidoRota) -> dict:
    return _planejar(pedido.origem, pedido.destino, pedido.bloqueadas, pedido.algoritmo)


@app.post("/api/inferencia")
def inferencia(pedido: PedidoInferencia) -> dict:
    try:
        bloq = [grafo.resolver(b) for b in pedido.bloqueadas]
    except grafo.EstacaoDesconhecida as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    return logica.inferir(bloq).para_json(incluir_rede=pedido.incluir_rede)


# ---------------------------------------------------------------- narração

def fatos_para_narrar(plano: dict) -> dict:
    """Recorte dos fatos calculados pelo core/ — única fonte do narrador."""
    comp, diag = plano["comparacao"], plano["diagnostico"]
    principal = next(iter(comp.values()))
    return {
        "origem": plano["origem"],
        "destino": plano["destino"],
        "bloqueadas": plano["bloqueadas"],
        "encontrado": principal["encontrado"],
        "motivo": principal["motivo"],
        "paradas": principal["paradas"],
        "caminho": principal["caminho"],
        "trechos": [
            {**t, "linha": grafo.LINHAS[t["linha"]]["nome"]} for t in diag["trechos"]
        ],
        "baldeacoes": [
            {"estacao": b["estacao"],
             "de_linha": grafo.LINHAS[b["de_linha"]]["nome"],
             "para_linha": grafo.LINHAS[b["para_linha"]]["nome"]}
            for b in diag["baldeacoes"]
        ],
        "obstrucoes": diag["obstrucoes"],
        "esforco": {
            nome: {k: c[k] for k in ("nos_visitados", "passos", "backtracks") if k in c}
            for nome, c in comp.items()
        },
        "regras_pendentes": plano["inferencia"]["regras_pendentes"],
    }


def narracao_offline(f: dict) -> str:
    partes = [f"Central do Subsolo para viajante: pedido de {f['origem']} até {f['destino']}."]
    if f["bloqueadas"]:
        partes.append(f"Estações bloqueadas no despacho: {', '.join(f['bloqueadas'])}.")
    if not f["encontrado"]:
        if f["motivo"] == "origem bloqueada":
            partes.append(f"A estação de origem, {f['origem']}, está bloqueada. Nenhuma partida autorizada.")
        elif f["motivo"] == "destino bloqueado":
            partes.append(f"A estação de destino, {f['destino']}, está bloqueada. Nenhuma chegada autorizada.")
        else:
            partes.append(
                f"Túnel obstruído: {', '.join(f['obstrucoes'])} interrompe o único caminho. "
                "Destino inalcançável."
            )
    else:
        if f["paradas"] == 0:
            partes.append("Origem e destino são a mesma estação. Nenhum deslocamento necessário.")
        for t in f["trechos"]:
            partes.append(f"Siga pela Linha {t['linha']} de {t['de']} até {t['ate']} ({t['paradas']} paradas).")
        for b in f["baldeacoes"]:
            partes.append(f"Baldeação em {b['estacao']}: da Linha {b['de_linha']} para a Linha {b['para_linha']}.")
        if f["paradas"]:
            partes.append(f"Total: {f['paradas']} paradas.")
    for nome, e in f["esforco"].items():
        extra = f", {e['backtracks']} backtracks" if "backtracks" in e else ""
        partes.append(f"{nome}: {e['nos_visitados']} estações visitadas em {e['passos']} passos{extra}.")
    if f["encontrado"]:
        partes.append("Rota autorizada pela Central.")
    return " ".join(partes)


PROMPT_SISTEMA = (
    "Você é o narrador do 'Despachante do Subsolo', um rádio de metrô em São Paulo. "
    "Narre em português do Brasil, em no máximo 5 frases, SOMENTE os fatos do JSON "
    "recebido. Não invente estações, linhas, horários, números nem eventos. Não sugira "
    "outra rota: a rota já foi decidida pelo algoritmo. Se 'encontrado' for false, "
    "explique o motivo usando apenas 'motivo' e 'obstrucoes'."
)


def _sse(evento: str, dados: dict) -> str:
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


async def _trechos_offline(texto: str) -> AsyncIterator[str]:
    for palavra in texto.split(" "):
        yield palavra + " "


async def _trechos_llama(fatos: dict, chave: str) -> AsyncIterator[str]:
    cliente = AsyncGroq(api_key=chave, timeout=15.0, max_retries=0)
    fluxo = await cliente.chat.completions.create(
        model=os.environ.get("GROQ_MODEL", MODELO_PADRAO),
        messages=[
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": json.dumps(fatos, ensure_ascii=False)},
        ],
        temperature=0.3,
        max_completion_tokens=300,
        stream=True,
    )
    async for pedaco in fluxo:
        texto = pedaco.choices[0].delta.content if pedaco.choices else None
        if texto:
            yield texto


async def _narrar(fatos: dict) -> AsyncIterator[str]:
    offline = narracao_offline(fatos)
    chave = os.environ.get("GROQ_API_KEY", "").strip()
    yield _sse("fatos", fatos)
    if chave:
        enviou = False
        try:
            async for texto in _trechos_llama(fatos, chave):
                if not enviou:
                    yield _sse("inicio", {"fonte": "llama"})
                    enviou = True
                yield _sse("trecho", {"texto": texto})
            if enviou:
                yield _sse("fim", {"fonte": "llama"})
                return
            motivo = "resposta vazia do Llama"
        except GroqError as erro:  # rede, timeout, chave inválida, limite, modelo
            motivo = f"Llama indisponível ({type(erro).__name__})"
        # Falha no meio do fluxo: o front descarta o parcial e recebe o offline.
        yield _sse("inicio", {"fonte": "offline", "motivo": motivo, "reiniciar": enviou})
    else:
        yield _sse("inicio", {"fonte": "offline", "motivo": "GROQ_API_KEY não configurada",
                              "reiniciar": False})
    async for texto in _trechos_offline(offline):
        yield _sse("trecho", {"texto": texto})
    yield _sse("fim", {"fonte": "offline"})


@app.get("/api/narrar")
def narrar(
    origem: str,
    destino: str,
    bloqueadas: list[str] = Query(default_factory=list),
    algoritmo: Algoritmo = "ambos",
) -> StreamingResponse:
    """SSE (compatível com EventSource): fatos → inicio → trecho* → fim."""
    plano = _planejar(origem, destino, bloqueadas, algoritmo)
    return StreamingResponse(
        _narrar(fatos_para_narrar(plano)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------- front

app.mount("/", StaticFiles(directory=RAIZ / "static", html=True), name="static")
