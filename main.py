"""MetrôBot SP — API FastAPI.

"O LLM conversa, o algoritmo decide." Toda rota e toda inferência vêm de
core/. O LLM (Groq) só interpreta o pedido (extrai nomes) e narra os fatos
já calculados; sem chave ou com a API fora do ar, intérprete e narrador usam
o modo offline determinístico.
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
from core.interprete import interpretar_offline
from core.planejador import PedidoIncompleto, TEMPO_POR_TRECHO, montar_cenario, planejar, validar_nomes

load_dotenv()

RAIZ = Path(__file__).parent
MODELO_PADRAO = "llama-3.3-70b-versatile"
# Limites folgados: modelos com raciocínio (ex.: openai/gpt-oss-120b) gastam
# tokens antes da resposta; uma resposta cortada vira JSON inválido (502).


def modelo_ativo() -> str:
    """Modelo em uso (GROQ_MODEL); exposto nas respostas por transparência."""
    return os.environ.get("GROQ_MODEL", MODELO_PADRAO)


app = FastAPI(title="MetrôBot SP — Subsolo SP", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

Algoritmo = Literal["bfs", "dfs", "ambos"]
ERROS_DE_NOME = (grafo.EstacaoDesconhecida, grafo.LinhaDesconhecida)


class CenarioIn(BaseModel):
    """Situação simulada da rede (desafio: interface R5)."""
    fechadas: list[str] = Field(default_factory=list)
    manutencao: list[str] = Field(default_factory=list)
    acessibilidade: bool = False
    paralisadas: list[str] = Field(default_factory=list)
    horario_pico: bool = False
    lotadas: list[str] = Field(default_factory=list)


class PedidoRota(CenarioIn):
    origem: str
    destino: str
    algoritmo: Algoritmo = "ambos"


class PedidoInferencia(CenarioIn):
    origem: str | None = None
    destino: str | None = None
    incluir_base: bool = False


def _planejar(origem: str, destino: str, cenario: CenarioIn, algoritmo: str) -> dict:
    try:
        return planejar(origem, destino, algoritmo=algoritmo, **cenario.model_dump(
            include=set(CenarioIn.model_fields)))
    except ERROS_DE_NOME as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    except PedidoIncompleto as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro


# ---------------------------------------------------------------- dados

@app.get("/api/estacoes")
def estacoes() -> dict:
    return {
        "linhas": [
            {"id": lid, "nome": d["nome"], "nome_logico": grafo.nome_linha(lid),
             "cor": d["cor"], "estacoes": d["estacoes"]}
            for lid, d in grafo.LINHAS.items()
        ],
        # Integrações deduzidas pela R6 (nunca digitadas).
        "hubs": logica.inferir().valores("integracao"),
        "estacoes": [grafo.dossie(e) for e in grafo.ESTACOES],
    }


@app.get("/api/locais")
def locais() -> dict:
    return {
        "locais": [
            {"nome": nome, "estacao": estacao,
             "linhas": [grafo.LINHAS[l]["nome"] for l in grafo.LINHAS_DA_ESTACAO[estacao]]}
            for nome, estacao in grafo.LOCAIS_CONHECIDOS.items()
        ],
    }


@app.get("/api/tabela-verdade")
def tabela_verdade() -> dict:
    return logica.tabela_verdade()


@app.post("/api/rota")
def rota(pedido: PedidoRota) -> dict:
    return _planejar(pedido.origem, pedido.destino, pedido, pedido.algoritmo)


@app.post("/api/inferencia")
def inferencia(pedido: PedidoInferencia) -> dict:
    try:
        cenario = montar_cenario(pedido.origem, pedido.destino,
                                 **pedido.model_dump(include=set(CenarioIn.model_fields)))
    except ERROS_DE_NOME as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro
    return logica.inferir(cenario).para_json(incluir_base=pedido.incluir_base)


# ---------------------------------------------------------------- interpretação

class PedidoInterpretacao(BaseModel):
    mensagem: str = Field(min_length=1, max_length=500)


class LlamaRespostaInvalida(ValueError):
    pass


CHAVES_INTERPRETACAO = {"origem", "destino", "fechadas", "acessibilidade"}


def prompt_interpretacao() -> str:
    """Prompt do intérprete (desafio.pdf, Passo 5.2) com a lista fechada de nomes."""
    return (
        "Você é o módulo de INTERPRETAÇÃO do MetrôBot SP.\n"
        "Sua única tarefa é transformar o pedido do passageiro em JSON.\n\n"
        f"Estações válidas: {', '.join(grafo.ESTACOES)}\n"
        f"Locais válidos: {', '.join(grafo.LOCAIS_CONHECIDOS)}\n\n"
        "Responda APENAS com um JSON neste formato:\n"
        '{"origem": "<nome exato de estação ou local, ou null>",\n'
        ' "destino": "<nome exato de estação ou local, ou null>",\n'
        ' "fechadas": ["<estações que o passageiro disse estarem fechadas ou que quer evitar>"],\n'
        ' "acessibilidade": <true ou false>}\n\n'
        "Regras:\n"
        "- Use os nomes das listas acima, escritos exatamente como aparecem.\n"
        "- Se o passageiro citar um nome que não está nas listas, copie-o como foi escrito, "
        "sem trocar por outro parecido.\n"
        '- "acessibilidade" é true se o passageiro mencionar cadeira de rodas, '
        "mobilidade reduzida, muletas, carrinho de bebê ou precisar de elevador.\n"
        "- Não calcule rota. Se não souber algum campo, use null. Nunca invente nomes."
    )


def validar_json_llama(texto: str) -> dict:
    """Aceita só o formato combinado; qualquer desvio é erro explícito."""
    try:
        dados = json.loads(texto)
    except (json.JSONDecodeError, TypeError) as erro:
        raise LlamaRespostaInvalida("resposta do LLM não é JSON") from erro
    if not isinstance(dados, dict) or set(dados) != CHAVES_INTERPRETACAO:
        raise LlamaRespostaInvalida(
            "JSON do LLM fora do formato {origem, destino, fechadas, acessibilidade}")
    for chave in ("origem", "destino"):
        if dados[chave] is not None and not isinstance(dados[chave], str):
            raise LlamaRespostaInvalida(f"'{chave}' deve ser texto ou null")
    if not isinstance(dados["fechadas"], list) or not all(isinstance(b, str) for b in dados["fechadas"]):
        raise LlamaRespostaInvalida("'fechadas' deve ser uma lista de textos")
    if not isinstance(dados["acessibilidade"], bool):
        raise LlamaRespostaInvalida("'acessibilidade' deve ser true ou false")
    return {
        "origem": (dados["origem"] or "").strip() or None,
        "destino": (dados["destino"] or "").strip() or None,
        "fechadas": [b.strip() for b in dados["fechadas"] if b.strip()],
        "acessibilidade": dados["acessibilidade"],
    }


async def _extrair_llama(mensagem: str, chave: str) -> str:
    async with AsyncGroq(api_key=chave, timeout=15.0, max_retries=0) as cliente:
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
    """LLM (ou plano B offline) só extrai nomes; o core/ valida. Rota: /api/rota."""
    chave = os.environ.get("GROQ_API_KEY", "").strip()
    fonte, motivo = "llm", None
    if not chave:
        fonte, motivo = "offline", "GROQ_API_KEY não configurada"
    else:
        try:
            extraido = validar_json_llama(await _extrair_llama(pedido.mensagem, chave))
        except GroqError as erro:  # rede, timeout, chave inválida, limite, modelo
            fonte, motivo = "offline", f"LLM indisponível ({type(erro).__name__})"
        except LlamaRespostaInvalida as erro:
            raise HTTPException(status_code=502, detail=str(erro)) from erro
    if fonte == "offline":
        extraido = interpretar_offline(pedido.mensagem)

    validado = validar_nomes(extraido["origem"], extraido["destino"], extraido["fechadas"])
    if validado["invalidos"]:
        raise HTTPException(status_code=422, detail={
            "erro": "nomes fora da rede",
            "invalidos": validado["invalidos"],
            "extraido": extraido,
        })
    return {
        "fonte": fonte,
        "offline": fonte == "offline",
        "modelo": modelo_ativo() if fonte == "llm" else None,
        "motivo": motivo,
        "origem": validado["origem"],
        "destino": validado["destino"],
        "fechadas": validado["fechadas"],
        "acessibilidade": extraido["acessibilidade"],
        "extraido": extraido,
    }


# ---------------------------------------------------------------- narração

def fatos_para_narrar(plano: dict) -> dict:
    """Recorte dos fatos calculados pelo core/ — única fonte do narrador."""
    comp, diag = plano["comparacao"], plano["diagnostico"]
    principal = next(iter(comp.values()))

    def nome(lid: str) -> str:
        return grafo.LINHAS[lid]["nome"]

    return {
        "pedido": {"origem": plano["cenario"]["origem"], "destino": plano["cenario"]["destino"]},
        "cenario": plano["cenario"],
        "origem": plano["origem"],
        "destino": plano["destino"],
        "fechadas": plano["cenario"]["fechadas"],
        "linhas_paralisadas": [nome(l) for l in plano["cenario"]["paralisadas"]],
        "bloqueadas": plano["bloqueadas"],
        "encontrado": principal["encontrado"],
        "motivo": principal["motivo"],
        "paradas": principal["paradas"],
        "tempo_min": diag["tempo_min"],
        "caminho": principal["caminho"],
        "trechos": [{**t, "linha": nome(t["linha"])} for t in diag["trechos"]],
        "baldeacoes": [
            {"estacao": b["estacao"], "de_linha": nome(b["de_linha"]), "para_linha": nome(b["para_linha"])}
            for b in diag["baldeacoes"]
        ],
        "obstrucoes": diag["obstrucoes"],
        "alertas": plano["alertas"],
        "alertas_lotacao": plano["alertas_lotacao"],
        "regras_disparadas": plano["regras_disparadas"],
        "esforco": {
            alg: {k: c[k] for k in ("nos_visitados", "passos", "backtracks") if k in c}
            for alg, c in comp.items()
        },
    }


def narracao_offline(f: dict) -> str:
    def rotulo(ponto: dict, estacao: str) -> str:
        return estacao if ponto["tipo"] == "estacao" else f"{ponto['nome']} ({estacao})"

    partes = [f"Central do Subsolo para viajante: pedido de {rotulo(f['pedido']['origem'], f['origem'])} "
              f"até {rotulo(f['pedido']['destino'], f['destino'])}."]
    if f["fechadas"]:
        partes.append(f"Estações fechadas: {', '.join(f['fechadas'])}.")
    if f["linhas_paralisadas"]:
        partes.append(f"Linha paralisada: {', '.join(f['linhas_paralisadas'])}.")
    if not f["encontrado"]:
        if f["motivo"] == "origem bloqueada":
            partes.append(f"A estação de origem, {f['origem']}, está bloqueada. Nenhuma partida autorizada.")
        elif f["motivo"] == "destino bloqueado":
            partes.append(f"A estação de destino, {f['destino']}, está bloqueada. Nenhuma chegada autorizada.")
        else:
            partes.append(f"Túnel obstruído: {', '.join(f['obstrucoes'])} interrompe o único caminho. "
                          "Destino inalcançável.")
    else:
        if f["paradas"] == 0:
            partes.append("Origem e destino são a mesma estação. Nenhum deslocamento necessário.")
        for t in f["trechos"]:
            partes.append(f"Siga pela Linha {t['linha']} de {t['de']} até {t['ate']} ({t['paradas']} paradas).")
        for b in f["baldeacoes"]:
            partes.append(f"Na {b['estacao']}, troque para a Linha {b['para_linha']}.")
        if f["paradas"]:
            partes.append(f"Total: {f['paradas']} paradas, {len(f['baldeacoes'])} baldeação(ões), "
                          f"cerca de {f['tempo_min']} minutos ({TEMPO_POR_TRECHO} min por trecho).")
    for a in f["alertas"]:
        partes.append(f"Atenção: elevador em manutenção na {a['estacao']} ({a['papel']}).")
    if f["alertas_lotacao"]:
        partes.append(f"Horário de pico: lotação em {', '.join(f['alertas_lotacao'])}.")
    for alg, e in f["esforco"].items():
        extra = f", {e['backtracks']} backtracks" if "backtracks" in e else ""
        partes.append(f"{alg}: {e['nos_visitados']} estações visitadas em {e['passos']} passos{extra}.")
    if f["encontrado"]:
        partes.append("Rota autorizada pela Central.")
    return " ".join(partes)


PROMPT_SISTEMA = (
    "Você é o NARRADOR do MetrôBot SP ('Despachante do Subsolo'). Explique a rota ao "
    "passageiro em português do Brasil, em no máximo 5 frases curtas. Use SOMENTE os "
    "dados do JSON. Não invente horários, linhas, estações ou atrações. Não sugira outra "
    "rota: ela já foi decidida pelo algoritmo. Cite as baldeações (ex.: 'Na Sé, troque "
    "para a Linha 3-Vermelha') e o tempo estimado. Se 'encontrado' for false, explique "
    "que não há rota usando apenas 'motivo', 'obstrucoes' e as estações fechadas. Se "
    "houver 'alertas' ou 'alertas_lotacao', destaque-os."
)


def _sse(evento: str, dados: dict) -> str:
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


async def _trechos_offline(texto: str) -> AsyncIterator[str]:
    for palavra in texto.split(" "):
        yield palavra + " "


async def _trechos_llama(fatos: dict, chave: str) -> AsyncIterator[str]:
    async with AsyncGroq(api_key=chave, timeout=15.0, max_retries=0) as cliente:
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
            motivo = "resposta vazia do LLM"
        except GroqError as erro:  # rede, timeout, chave inválida, limite, modelo
            motivo = f"LLM indisponível ({type(erro).__name__})"
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
    fechadas: list[str] = Query(default_factory=list),
    manutencao: list[str] = Query(default_factory=list),
    acessibilidade: bool = False,
    paralisadas: list[str] = Query(default_factory=list),
    horario_pico: bool = False,
    lotadas: list[str] = Query(default_factory=list),
    algoritmo: Algoritmo = "ambos",
) -> StreamingResponse:
    """SSE (compatível com EventSource): fatos → inicio → trecho* → fim."""
    cenario = CenarioIn(fechadas=fechadas, manutencao=manutencao, acessibilidade=acessibilidade,
                        paralisadas=paralisadas, horario_pico=horario_pico, lotadas=lotadas)
    plano = _planejar(origem, destino, cenario, algoritmo)
    return StreamingResponse(
        _narrar(fatos_para_narrar(plano)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------- front

app.mount("/", StaticFiles(directory=RAIZ / "static", html=True), name="static")
