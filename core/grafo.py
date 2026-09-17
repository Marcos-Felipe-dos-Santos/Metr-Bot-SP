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
            "São Bento", "Sé", "Japão-Liberdade", "São Joaquim", "Vergueiro",
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
            "Vila Matilde", "Guilhermina-Esperança", "Patriarca-Vila Ré",
            "Artur Alvim", "Corinthians-Itaquera",
        ],
    },
}

CORES: dict[str, str] = {lid: dados["cor"] for lid, dados in LINHAS.items()}

# Nomes das estações exatamente como em "Dados das linhas" do desafio.

# Local -> estação mais próxima (proximo_de).
LOCAIS_CONHECIDOS: dict[str, str] = {
    # Linha 1 — dicionário LOCAIS da aula (desafio.pdf, Passo 2.4)
    "Shopping Metrô Tucuruvi": "Tucuruvi",
    "Terminal Rodoviário Tietê": "Portuguesa-Tietê",
    "Museu de Arte Sacra": "Tiradentes",
    "Pinacoteca": "Luz",
    "Museu da Língua Portuguesa": "Luz",
    "Mosteiro de São Bento": "São Bento",
    "Rua 25 de Março": "São Bento",
    "Catedral da Sé": "Sé",
    "Bairro da Liberdade": "Japão-Liberdade",
    "Centro Cultural São Paulo": "Vergueiro",
    "Shopping Metrô Santa Cruz": "Santa Cruz",
    "Universidade São Judas": "São Judas",
    "Terminal Rodoviário Jabaquara": "Jabaquara",
    # Linha 2 — exemplos do desafio (R3) + propostas aprovadas pelo aluno
    "MASP": "Trianon-Masp",
    "Hospital das Clínicas": "Clínicas",
    "Conjunto Nacional": "Consolação",
    "Shopping Pátio Paulista": "Brigadeiro",
    "Beco do Batman": "Vila Madalena",
    # Linha 3 — exemplos do desafio (R3) + proposta aprovada pelo aluno
    "Theatro Municipal": "Anhangabaú",
    "Neo Química Arena": "Corinthians-Itaquera",
    "Memorial da América Latina": "Palmeiras-Barra Funda",
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


class LinhaDesconhecida(ValueError):
    pass


def nome_linha(lid: str) -> str:
    """Nome usado nos fatos lógicos, como no desafio: 'Linha 1-Azul'."""
    return f"Linha {LINHAS[lid]['nome']}"


def resolver_linha(valor: str) -> str:
    """Aceita '1', '1-Azul' ou 'Linha 1-Azul' e devolve o id ('1')."""
    alvo = _normalizar(valor)
    for lid, dados in LINHAS.items():
        if alvo in {_normalizar(lid), _normalizar(dados["nome"]), _normalizar(nome_linha(lid))}:
            return lid
    raise LinhaDesconhecida(f"Linha desconhecida: {valor!r}")


def vizinhos(estacao: str) -> list[str]:
    return list(ADJACENCIA[estacao])


def linhas_da_aresta(a: str, b: str) -> list[str]:
    return list(_LINHAS_DA_ARESTA[frozenset((a, b))])


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.casefold().replace("-", " ").split())


def _montar_indice() -> dict[str, tuple[str, str]]:
    """nome normalizado -> (tipo, nome canônico); tipo é 'estacao' ou 'local'."""
    indice: dict[str, tuple[str, str]] = {}
    entradas = [("estacao", e) for e in ESTACOES] + [("local", l) for l in LOCAIS_CONHECIDOS]
    for tipo, nome in entradas:
        if tipo == "local" and LOCAIS_CONHECIDOS[nome] not in ADJACENCIA:
            raise ValueError(f"Local {nome!r} aponta para estação inexistente")
        chave = _normalizar(nome)
        if chave in indice:
            raise ValueError(f"Nome {nome!r} colide com {indice[chave][1]!r} no índice")
        indice[chave] = (tipo, nome)
    return indice


_INDICE = _montar_indice()


def identificar(nome: str) -> tuple[str, str]:
    """Nome digitado -> ('estacao'|'local', nome canônico). Sem aproximação."""
    try:
        return _INDICE[_normalizar(nome)]
    except KeyError:
        raise EstacaoDesconhecida(f"Estação ou local desconhecido: {nome!r}") from None


def resolver(nome: str) -> str:
    """Nome de estação ou local conhecido -> estação canônica."""
    tipo, canonico = identificar(nome)
    return canonico if tipo == "estacao" else LOCAIS_CONHECIDOS[canonico]


def resolver_estacao(nome: str) -> str:
    """Só aceita estação (cenários: fechada, manutenção, lotada)."""
    tipo, canonico = identificar(nome)
    if tipo != "estacao":
        raise EstacaoDesconhecida(f"{nome!r} é um local, não uma estação")
    return canonico


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
