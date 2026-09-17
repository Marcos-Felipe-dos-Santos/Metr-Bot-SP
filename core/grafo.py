"""Rede do MetrôBot SP: linhas, cores, hubs, adjacência e locais conhecidos.

Convenção de vizinhos (define os traces de BFS/DFS):
- ordem do percurso de cada linha (anterior, próxima);
- linhas processadas na ordem L1, L2, L3, então nos hubs vêm primeiro os
  vizinhos da L1 e depois os da outra linha, sem repetidos.
"""

from __future__ import annotations

import unicodedata

LINHAS: dict[str, dict] = {
    "1": {
        "nome": "1-Azul",
        "cor": "#0054A6",
        "estacoes": [
            "Tucuruvi", "Parada Inglesa", "Jardim São Paulo", "Santana",
            "Carandiru", "Portuguesa-Tietê", "Armênia", "Tiradentes", "Luz",
            "São Bento", "Sé", "Liberdade", "São Joaquim", "Vergueiro",
            "Paraíso", "Ana Rosa", "Vila Mariana", "Santa Cruz",
            "Praça da Árvore", "Saúde", "São Judas", "Conceição", "Jabaquara",
        ],
    },
    "2": {
        "nome": "2-Verde",
        "cor": "#009640",
        "estacoes": [
            "Vila Madalena", "Sumaré", "Clínicas", "Consolação",
            "Trianon-Masp", "Brigadeiro", "Paraíso", "Ana Rosa",
            "Chácara Klabin", "Santos-Imigrantes", "Alto do Ipiranga",
            "Sacomã", "Tamanduateí", "Vila Prudente",
        ],
    },
    "3": {
        "nome": "3-Vermelha",
        "cor": "#EF3A46",
        "estacoes": [
            "Palmeiras-Barra Funda", "Marechal Deodoro", "Santa Cecília",
            "República", "Anhangabaú", "Sé", "Pedro II", "Brás",
            "Bresser-Mooca", "Belém", "Tatuapé", "Carrão", "Penha",
            "Vila Matilde", "Guilhermina-Esperança", "Patriarca",
            "Artur Alvim", "Corinthians-Itaquera",
        ],
    },
}

CORES: dict[str, str] = {lid: dados["cor"] for lid, dados in LINHAS.items()}

# Pendente: lista oficial do enunciado. Por ora só o local citado explicitamente.
LOCAIS_CONHECIDOS: dict[str, str] = {
    "Shopping Metrô Tucuruvi": "Tucuruvi",
}


def _montar_rede():
    adjacencia: dict[str, list[str]] = {}
    linhas_da_estacao: dict[str, list[str]] = {}
    linhas_da_aresta: dict[frozenset, list[str]] = {}
    for lid, dados in LINHAS.items():
        seq = dados["estacoes"]
        for i, est in enumerate(seq):
            adjacencia.setdefault(est, [])
            linhas_da_estacao.setdefault(est, []).append(lid)
            vizinhos = seq[max(i - 1, 0):i] + seq[i + 1:i + 2]
            for viz in vizinhos:
                if viz not in adjacencia[est]:
                    adjacencia[est].append(viz)
                linhas = linhas_da_aresta.setdefault(frozenset((est, viz)), [])
                if lid not in linhas:
                    linhas.append(lid)
    return adjacencia, linhas_da_estacao, linhas_da_aresta


ADJACENCIA, LINHAS_DA_ESTACAO, _LINHAS_DA_ARESTA = _montar_rede()
ESTACOES: list[str] = list(ADJACENCIA)
HUBS: list[str] = [e for e in ESTACOES if len(LINHAS_DA_ESTACAO[e]) > 1]


class EstacaoDesconhecida(ValueError):
    pass


def vizinhos(estacao: str) -> list[str]:
    return list(ADJACENCIA[estacao])


def linhas_da_aresta(a: str, b: str) -> list[str]:
    return list(_LINHAS_DA_ARESTA[frozenset((a, b))])


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.casefold().replace("-", " ").split())


def _montar_indice() -> dict[str, str]:
    indice: dict[str, str] = {}
    for nome, estacao in [(e, e) for e in ESTACOES] + list(LOCAIS_CONHECIDOS.items()):
        if estacao not in ADJACENCIA:
            raise ValueError(f"Local {nome!r} aponta para estação inexistente {estacao!r}")
        chave = _normalizar(nome)
        if chave in indice:
            raise ValueError(f"Nome {nome!r} colide com {indice[chave]!r} no índice")
        indice[chave] = estacao
    return indice


_INDICE = _montar_indice()


def resolver(nome: str) -> str:
    """Nome de estação ou local conhecido -> estação canônica."""
    try:
        return _INDICE[_normalizar(nome)]
    except KeyError:
        raise EstacaoDesconhecida(f"Estação ou local desconhecido: {nome!r}") from None


def dossie(estacao: str) -> dict:
    return {
        "nome": estacao,
        "linhas": [
            {"id": l, "nome": LINHAS[l]["nome"], "cor": CORES[l]}
            for l in LINHAS_DA_ESTACAO[estacao]
        ],
        "hub": estacao in HUBS,
        "vizinhos": vizinhos(estacao),
    }
