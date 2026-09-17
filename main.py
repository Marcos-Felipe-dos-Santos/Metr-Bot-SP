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
from core.planejador import planejar, validar_nomes

load_dotenv()

RAIZ = Path(__file__).parent
MODELO_PADRAO = "llama-3.3-70b-versatile"
# Limites folgados: modelos com raciocínio (ex.: openai/gpt-oss-120b) gastam
# tokens antes da resposta; uma resposta cortada vira JSON inválido (502).


def modelo_ativo() -> str:
    """Modelo em uso (GROQ_MODEL); exposto nas respostas por transparência."""
    return os.environ.get("GROQ_MODEL", MODELO_PADRAO)

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


# ---------------------------------------------------------------- interpretação

class PedidoInterpretacao(BaseModel):
    mensagem: str = Field(min_length=1, max_length=500)


class LlamaRespostaInvalida(ValueError):
    pass


def prompt_interpretacao() -> str:
    nomes = grafo.ESTACOES + list(grafo.LOCAIS_CONHECIDOS)
    return (
        "Você extrai nomes de um pedido de viagem no metrô de São Paulo. "
        "Responda SOMENTE com um objeto JSON com exatamente estas chaves: "
        '{"origem": string ou null, "destino": string ou null, "bloqueadas": [string]}. '
        "'bloqueadas' são estações que o usuário quer evitar ou que estão fechadas. "
        "Se o usuário citar um nome desta lista, copie o nome exatamente como está na lista: "
        f"{json.dumps(nomes, ensure_ascii=False)}. "
        "Se citar um nome que NÃO está na lista, copie o nome como o usuário escreveu, sem "
        "trocar por outro parecido. Não calcule rota, não sugira estações, não adicione "
        "nomes que o usuário não disse. Use null para o que não foi dito."
    )


def validar_json_llama(texto: str) -> dict:
    """Aceita só o formato combinado; qualquer desvio é erro explícito."""
    try:
        dados = json.loads(texto)
    except (json.JSONDecodeError, TypeError) as erro:
        raise LlamaRespostaInvalida("resposta do Llama não é JSON") from erro
    if not isinstance(dados, dict) or set(dados) != {"origem", "destino", "bloqueadas"}:
        raise LlamaRespostaInvalida("JSON do Llama fora do formato {origem, destino, bloqueadas}")
    for chave in ("origem", "destino"):
        if dados[chave] is not None and not isinstance(dados[chave], str):
            raise LlamaRespostaInvalida(f"'{chave}' deve ser texto ou null")
    if not isinstance(dados["bloqueadas"], list) or not all(isinstance(b, str) for b in dados["bloqueadas"]):
        raise LlamaRespostaInvalida("'bloqueadas' deve ser uma lista de textos")
    return {
        "origem": (dados["origem"] or "").strip() or None,
        "destino": (dados["destino"] or "").strip() or None,
        "bloqueadas": [b.strip() for b in dados["bloqueadas"] if b.strip()],
    }


async def _extrair_llama(mensagem: str, chave: str) -> str:
    cliente = AsyncGroq(api_key=chave, timeout=15.0, max_retries=0)
    resposta = await cliente.chat.completions.create(
        model=modelo_ativo(),
        messages=[
            {"role": "system", "content": prompt_interpretacao()},
            {"role": "user", "content": mensagem},
        ],
        temperature=0,
        max_completion_tokens=600,
        response_format={"type": "json_object"},
    )
    return resposta.choices[0].message.content


@app.post("/api/interpretar")
async def interpretar(pedido: PedidoInterpretacao) -> dict:
    """Llama só extrai nomes; o core/ valida. Rota continua com /api/rota."""
    vazio = {"origem": None, "destino": None, "bloqueadas": []}
    chave = os.environ.get("GROQ_API_KEY", "").strip()
    if not chave:
        return {"offline": True, "motivo": "GROQ_API_KEY não configurada", **vazio, "extraido": None}
    try:
        extraido = validar_json_llama(await _extrair_llama(pedido.mensagem, chave))
    except GroqError as erro:
        return {"offline": True, "motivo": f"Llama indisponível ({type(erro).__name__})",
                **vazio, "extraido": None}
    except LlamaRespostaInvalida as erro:
        raise HTTPException(status_code=502, detail=str(erro)) from erro

    validado = validar_nomes(extraido["origem"], extraido["destino"], extraido["bloqueadas"])
    if validado["invalidos"]:
        raise HTTPException(status_code=422, detail={
            "erro": "nomes fora da rede",
            "invalidos": validado["invalidos"],
            "extraido": extraido,
        })
    return {
        "offline": False,
        "motivo": None,
        "modelo": modelo_ativo(),
        "origem": validado["origem"],
        "destino": validado["destino"],
        "bloqueadas": validado["bloqueadas"],
        "extraido": extraido,
    }


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
        model=modelo_ativo(),
        messages=[
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": json.dumps(fatos, ensure_ascii=False)},
        ],
        temperature=0.3,
        max_completion_tokens=800,
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
                    yield _sse("inicio", {"fonte": "llama", "modelo": modelo_ativo()})
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
