"""Planejador: a lógica decide o que está fechado, a busca decide a rota."""

from __future__ import annotations

from typing import Iterable

from core import busca, grafo, logica


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
    }
