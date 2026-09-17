"""Planejador: a lógica decide origem, destino e bloqueios; a busca decide a rota."""

from __future__ import annotations

from typing import Iterable

from core import busca, grafo, logica

TEMPO_POR_TRECHO = 2  # minutos por trecho (valor simulado, didático — desafio.pdf)


class PedidoIncompleto(ValueError):
    pass


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
    paradas = trace["metricas"]["paradas"]
    return {
        "obstrucoes": obstrucoes,
        "trechos": trechos,
        "baldeacoes": baldeacoes,
        "tempo_min": None if paradas is None else paradas * TEMPO_POR_TRECHO,
    }


def validar_nomes(origem: str | None, destino: str | None,
                  fechadas: Iterable[str] = ()) -> dict:
    """Confere nomes extraídos de linguagem natural contra a rede.

    Origem/destino podem ser estação ou local (nome canônico preservado);
    fechadas precisam ser estações. Nenhum nome é corrigido por aproximação.
    """
    invalidos: list[str] = []

    def ponto(nome: str | None) -> str | None:
        if nome is None:
            return None
        try:
            return grafo.identificar(nome)[1]
        except grafo.EstacaoDesconhecida:
            invalidos.append(nome)
            return None

    def estacao(nome: str) -> str | None:
        try:
            return grafo.resolver_estacao(nome)
        except grafo.EstacaoDesconhecida:
            invalidos.append(nome)
            return None

    org = ponto(origem)
    dst = ponto(destino)
    fech = [e for e in (estacao(n) for n in fechadas) if e is not None]
    return {
        "origem": org,
        "destino": dst,
        "fechadas": list(dict.fromkeys(fech)),
        "invalidos": invalidos,
    }


def montar_cenario(origem: str | None = None, destino: str | None = None, *,
                   fechadas: Iterable[str] = (), manutencao: Iterable[str] = (),
                   acessibilidade: bool = False, paralisadas: Iterable[str] = (),
                   horario_pico: bool = False, lotadas: Iterable[str] = ()) -> logica.Cenario:
    """Nomes digitados -> cenário canônico. Nome desconhecido = erro explícito."""
    def estacoes(nomes):
        return list(dict.fromkeys(grafo.resolver_estacao(n) for n in nomes))

    return logica.Cenario(
        origem=None if origem is None else grafo.identificar(origem),
        destino=None if destino is None else grafo.identificar(destino),
        acessibilidade=acessibilidade,
        fechadas=estacoes(fechadas),
        manutencao=estacoes(manutencao),
        paralisadas=list(dict.fromkeys(grafo.resolver_linha(l) for l in paralisadas)),
        horario_pico=horario_pico,
        lotadas=estacoes(lotadas),
    )


def planejar(origem: str, destino: str, *, fechadas: Iterable[str] = (),
             manutencao: Iterable[str] = (), acessibilidade: bool = False,
             paralisadas: Iterable[str] = (), horario_pico: bool = False,
             lotadas: Iterable[str] = (), algoritmo: str = "ambos") -> dict:
    """origem/destino: estação ou local conhecido (R1/R2 deduzem a estação)."""
    nomes = ["bfs", "dfs"] if algoritmo == "ambos" else [algoritmo.lower()]
    for nome in nomes:
        if nome not in busca.ALGORITMOS:
            raise ValueError(f"Algoritmo inválido: {algoritmo!r} (use bfs, dfs ou ambos)")

    cenario = montar_cenario(origem, destino, fechadas=fechadas, manutencao=manutencao,
                             acessibilidade=acessibilidade, paralisadas=paralisadas,
                             horario_pico=horario_pico, lotadas=lotadas)
    inferencia = logica.inferir(cenario)

    # Tudo o que a busca usa vem da base lógica.
    origens, destinos = inferencia.valores("origem"), inferencia.valores("destino")
    if len(origens) != 1 or len(destinos) != 1:
        raise PedidoIncompleto(f"A lógica não deduziu origem/destino únicos: {origens} / {destinos}")
    org, dst = origens[0], destinos[0]
    bloqueadas = inferencia.valores("bloqueada")

    buscas = {n.upper(): busca.buscar(n, org, dst, bloqueadas) for n in nomes}
    comparacao = {
        nome: {"encontrado": t["encontrado"], "motivo": t["motivo"], "caminho": t["caminho"],
               "tempo_min": None if t["metricas"]["paradas"] is None
               else t["metricas"]["paradas"] * TEMPO_POR_TRECHO,
               **t["metricas"]}
        for nome, t in buscas.items()
    }
    principal = next(iter(buscas.values()))
    return {
        "origem": org,
        "destino": dst,
        "cenario": cenario.para_json(),
        "bloqueadas": bloqueadas,
        "alertas": [{"papel": f.args[0], "estacao": f.args[1]} for f in inferencia.consulta("alerta")],
        "alertas_lotacao": inferencia.valores("alerta_lotacao"),
        "regras_disparadas": inferencia.regras_disparadas,
        "inferencia": inferencia.para_json(),
        "buscas": buscas,
        "comparacao": comparacao,
        "diagnostico": diagnosticar(org, dst, bloqueadas, principal),
    }
