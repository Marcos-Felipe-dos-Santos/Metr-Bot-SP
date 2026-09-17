"""BFS e DFS com estações bloqueadas, registrando o trace completo.

O trace é o contrato com o front: o front só reproduz.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable

from core import grafo


def _preparar(algoritmo: str, origem: str, destino: str, bloqueadas: list[str]):
    for est in (origem, destino, *bloqueadas):
        if est not in grafo.ADJACENCIA:
            raise grafo.EstacaoDesconhecida(f"Estação desconhecida: {est!r}")
    bloq = set(bloqueadas)
    trace = {
        "algoritmo": algoritmo,
        "estrutura": "fila (FIFO)" if algoritmo == "BFS" else "pilha (LIFO)",
        "origem": origem,
        "destino": destino,
        "bloqueadas": sorted(bloq),
        "passos": [],
        "ordem": [],
        "visitados": [],
        "pai": {},
        "encontrado": False,
        "motivo": None,
        "caminho": [],
        "caminho_arestas": [],
    }
    if origem in bloq:
        trace["motivo"] = "origem bloqueada"
    elif destino in bloq:
        trace["motivo"] = "destino bloqueado"
    return trace, bloq


def _reconstruir(pai: dict, destino: str) -> list[str]:
    """Fio de Ariadne: volta pelo mapa de pais até a origem."""
    caminho = [destino]
    while pai[caminho[-1]] is not None:
        caminho.append(pai[caminho[-1]])
    return caminho[::-1]


def _finalizar(trace: dict, metricas: dict) -> dict:
    if trace["encontrado"]:
        cam = trace["caminho"]
        trace["caminho_arestas"] = [
            {"de": a, "para": b, "linhas": grafo.linhas_da_aresta(a, b)}
            for a, b in zip(cam, cam[1:])
        ]
    elif not trace["motivo"]:
        trace["motivo"] = "sem caminho (bloqueios isolam o destino)"
    metricas["paradas"] = len(trace["caminho"]) - 1 if trace["encontrado"] else None
    metricas["passos"] = len(trace["passos"])
    metricas["nos_visitados"] = len(trace["visitados"])
    trace["metricas"] = metricas
    return trace


def bfs(origem: str, destino: str, bloqueadas: Iterable[str] = ()) -> dict:
    trace, bloq = _preparar("BFS", origem, destino, list(bloqueadas))
    metricas = {"nos_expandidos": 0, "max_fronteira": 0}
    trace["niveis"] = {}
    if trace["motivo"]:
        return _finalizar(trace, metricas)

    fila = deque([origem])
    trace["pai"][origem] = None
    trace["niveis"][origem] = 0
    trace["visitados"].append(origem)
    metricas["max_fronteira"] = 1

    while fila:
        atual = fila.popleft()
        nivel = trace["niveis"][atual]
        trace["ordem"].append(atual)
        passo = {
            "n": len(trace["passos"]) + 1,
            "acao": "expandir",
            "no": atual,
            "nivel": nivel,
            "descobertos": [],
            "ignorados": [],
        }
        if atual == destino:
            passo["acao"] = "objetivo"
            passo["fila"] = list(fila)
            trace["passos"].append(passo)
            trace["encontrado"] = True
            trace["caminho"] = _reconstruir(trace["pai"], destino)
            break
        metricas["nos_expandidos"] += 1
        for viz in grafo.vizinhos(atual):
            if viz in bloq:
                passo["ignorados"].append({"no": viz, "motivo": "bloqueada"})
            elif viz in trace["pai"]:
                passo["ignorados"].append({"no": viz, "motivo": "visitado"})
            else:
                trace["pai"][viz] = atual
                trace["niveis"][viz] = nivel + 1
                trace["visitados"].append(viz)
                fila.append(viz)
                passo["descobertos"].append({
                    "no": viz,
                    "nivel": nivel + 1,
                    "linhas": grafo.linhas_da_aresta(atual, viz),
                })
        passo["fila"] = list(fila)
        metricas["max_fronteira"] = max(metricas["max_fronteira"], len(fila))
        trace["passos"].append(passo)

    return _finalizar(trace, metricas)


def dfs(origem: str, destino: str, bloqueadas: Iterable[str] = ()) -> dict:
    """DFS iterativa: a pilha é o caminho corrente; backtracking explícito."""
    trace, bloq = _preparar("DFS", origem, destino, list(bloqueadas))
    metricas = {"backtracks": 0, "max_fronteira": 0, "profundidade_max": 0}
    if trace["motivo"]:
        return _finalizar(trace, metricas)

    pilha = [origem]
    pendentes = {origem: iter(grafo.vizinhos(origem))}
    trace["pai"][origem] = None
    trace["visitados"].append(origem)
    trace["ordem"].append(origem)
    trace["passos"].append({
        "n": 1,
        "acao": "objetivo" if origem == destino else "empilhar",
        "no": origem,
        "profundidade": 0,
        "ignorados": [],
        "pilha": list(pilha),
    })
    metricas["max_fronteira"] = 1

    chegou = origem == destino
    while pilha and not chegou:
        topo = pilha[-1]
        ignorados = []
        proximo = None
        for viz in pendentes[topo]:
            if viz in bloq:
                ignorados.append({"no": viz, "motivo": "bloqueada"})
            elif viz in trace["pai"]:
                ignorados.append({"no": viz, "motivo": "visitado"})
            else:
                proximo = viz
                break
        passo = {"n": len(trace["passos"]) + 1}
        if proximo is None:
            pilha.pop()
            metricas["backtracks"] += 1
            passo.update(
                acao="backtrack",
                no=topo,
                volta_para=pilha[-1] if pilha else None,
                profundidade=len(pilha),
            )
        else:
            pilha.append(proximo)
            pendentes[proximo] = iter(grafo.vizinhos(proximo))
            trace["pai"][proximo] = topo
            trace["visitados"].append(proximo)
            trace["ordem"].append(proximo)
            chegou = proximo == destino
            passo.update(
                acao="objetivo" if chegou else "avancar",
                de=topo,
                no=proximo,
                linhas=grafo.linhas_da_aresta(topo, proximo),
                profundidade=len(pilha) - 1,
            )
            metricas["max_fronteira"] = max(metricas["max_fronteira"], len(pilha))
            metricas["profundidade_max"] = max(metricas["profundidade_max"], len(pilha) - 1)
        passo["ignorados"] = ignorados
        passo["pilha"] = list(pilha)
        trace["passos"].append(passo)

    if chegou:
        trace["encontrado"] = True
        trace["caminho"] = list(pilha)
    return _finalizar(trace, metricas)


ALGORITMOS = {"bfs": bfs, "dfs": dfs}


def buscar(algoritmo: str, origem: str, destino: str,
           bloqueadas: Iterable[str] = ()) -> dict:
    try:
        func = ALGORITMOS[algoritmo.lower()]
    except KeyError:
        raise ValueError(f"Algoritmo inválido: {algoritmo!r} (use bfs ou dfs)") from None
    return func(origem, destino, bloqueadas)
