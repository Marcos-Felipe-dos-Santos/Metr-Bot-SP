"""Planejador: a lógica decide o que está fechado, a busca decide a rota."""

from __future__ import annotations

from typing import Iterable

from core import busca, grafo, logica


def trechos_da_rota(caminho_arestas: list[dict]) -> tuple[list[dict], list[dict]]:
    """Agrupa as arestas por linha; troca de linha = baldeação.

    Uma aresta pode pertencer a duas linhas (Paraíso–Ana Rosa): a linha do
    trecho é mantida enquanto for possível e só muda quando obrigatório.
    """
    grupos: list[dict] = []
    for aresta in caminho_arestas:
        linhas = set(aresta["linhas"])
        if grupos and grupos[-1]["linhas"] & linhas:
            grupos[-1]["linhas"] &= linhas
            grupos[-1]["ate"] = aresta["para"]
            grupos[-1]["paradas"] += 1
        else:
            grupos.append({"linhas": linhas, "de": aresta["de"],
                           "ate": aresta["para"], "paradas": 1})
    trechos = [
        {"linha": min(g["linhas"]), "de": g["de"], "ate": g["ate"], "paradas": g["paradas"]}
        for g in grupos
    ]
    baldeacoes = [
        {"estacao": b["de"], "de_linha": a["linha"], "para_linha": b["linha"]}
        for a, b in zip(trechos, trechos[1:])
    ]
    return trechos, baldeacoes


def diagnosticar(origem: str, destino: str, bloqueadas: list[str], trace: dict) -> dict:
    livre = busca.bfs(origem, destino)
    obstrucoes = [e for e in livre["caminho"] if e in set(bloqueadas)]
    trechos, baldeacoes = trechos_da_rota(trace["caminho_arestas"])
    return {"obstrucoes": obstrucoes, "trechos": trechos, "baldeacoes": baldeacoes}


def validar_nomes(origem: str | None, destino: str | None,
                  bloqueadas: Iterable[str] = ()) -> dict:
    """Confere nomes extraídos de linguagem natural contra a rede.

    Devolve as estações canônicas e a lista de nomes que não existem.
    Nenhum nome é corrigido por aproximação: ou resolve, ou é inválido.
    """
    invalidos: list[str] = []

    def resolver(nome: str | None) -> str | None:
        if nome is None:
            return None
        try:
            return grafo.resolver(nome)
        except grafo.EstacaoDesconhecida:
            invalidos.append(nome)
            return None

    org = resolver(origem)
    dst = resolver(destino)
    bloq = [b for b in (resolver(n) for n in bloqueadas) if b is not None]
    return {
        "origem": org,
        "destino": dst,
        "bloqueadas": list(dict.fromkeys(bloq)),
        "invalidos": invalidos,
    }


def planejar(origem: str, destino: str, bloqueadas: Iterable[str] = (),
             algoritmo: str = "ambos") -> dict:
    """origem/destino/bloqueadas aceitam nome de estação ou local conhecido."""
    org = grafo.resolver(origem)
    dst = grafo.resolver(destino)
    bloq = list(dict.fromkeys(grafo.resolver(b) for b in bloqueadas))

    inferencia = logica.inferir(bloq)
    # A busca usa o que a base lógica concluiu como Bloqueada(x).
    fechadas = [f.args[0] for f in inferencia.consulta("Bloqueada")]

    nomes = ["bfs", "dfs"] if algoritmo == "ambos" else [algoritmo]
    buscas = {n.upper(): busca.buscar(n, org, dst, fechadas) for n in nomes}

    return {
        "origem": org,
        "destino": dst,
        "bloqueadas": fechadas,
        "inferencia": inferencia.para_json(),
        "buscas": buscas,
        "comparacao": {
            nome: {
                "encontrado": t["encontrado"],
                "motivo": t["motivo"],
                "caminho": t["caminho"],
                **t["metricas"],
            }
            for nome, t in buscas.items()
        },
        "diagnostico": diagnosticar(org, dst, fechadas, next(iter(buscas.values()))),
    }
