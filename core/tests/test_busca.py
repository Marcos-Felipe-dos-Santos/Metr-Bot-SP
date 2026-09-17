from collections import deque

import pytest

from core import grafo
from core.busca import bfs, buscar, dfs


def distancia_referencia(origem, destino, bloqueadas=()):
    """Menor nº de paradas, calculado de forma independente para conferência."""
    dist = {origem: 0}
    fila = deque([origem])
    while fila:
        atual = fila.popleft()
        for v in grafo.ADJACENCIA[atual]:
            if v not in dist and v not in bloqueadas:
                dist[v] = dist[atual] + 1
                fila.append(v)
    return dist.get(destino)


def assert_caminho_valido(trace):
    cam = trace["caminho"]
    assert cam[0] == trace["origem"]
    assert cam[-1] == trace["destino"]
    assert not set(cam) & set(trace["bloqueadas"])
    assert len(cam) == len(set(cam))
    for a, b in zip(cam, cam[1:]):
        assert b in grafo.ADJACENCIA[a]
    assert [(e["de"], e["para"]) for e in trace["caminho_arestas"]] == list(zip(cam, cam[1:]))


# ---------- BFS ----------

def test_bfs_luz_republica_menor_caminho():
    t = bfs("Luz", "República")
    assert t["encontrado"]
    assert t["caminho"] == ["Luz", "São Bento", "Sé", "Anhangabaú", "República"]
    assert t["metricas"]["paradas"] == 4
    assert t["ordem"][:5] == ["Luz", "Tiradentes", "São Bento", "Armênia", "Sé"]
    assert_caminho_valido(t)


def test_bfs_linha_inteira():
    t = bfs("Tucuruvi", "Jabaquara")
    assert t["caminho"] == grafo.LINHAS["1"]["estacoes"]
    assert t["metricas"]["paradas"] == 22


@pytest.mark.parametrize("origem, destino", [
    ("Vila Madalena", "Corinthians-Itaquera"),
    ("Vila Prudente", "Tucuruvi"),
    ("Palmeiras-Barra Funda", "Chácara Klabin"),
    ("Brigadeiro", "Vila Mariana"),
])
def test_bfs_e_otimo(origem, destino):
    t = bfs(origem, destino)
    assert_caminho_valido(t)
    assert t["metricas"]["paradas"] == distancia_referencia(origem, destino)


def test_bfs_trace_fila_fifo_e_niveis():
    t = bfs("Sé", "Jabaquara")
    passos = t["passos"]
    assert passos[0]["no"] == "Sé" and passos[0]["nivel"] == 0
    fila = ["Sé"]
    for p in passos:
        assert fila.pop(0) == p["no"]  # FIFO: sai sempre o primeiro
        fila += [d["no"] for d in p["descobertos"]]
        assert p["fila"] == fila
        for d in p["descobertos"]:
            assert d["nivel"] == p["nivel"] + 1
            assert d["linhas"]
    niveis = [p["nivel"] for p in passos]
    assert niveis == sorted(niveis)  # onda por níveis
    assert passos[-1]["acao"] == "objetivo"
    assert t["pai"]["Sé"] is None


def test_bfs_registra_bloqueada_ignorada():
    t = bfs("Sé", "Liberdade", bloqueadas=["São Bento"])
    assert t["caminho"] == ["Sé", "Liberdade"]
    assert {"no": "São Bento", "motivo": "bloqueada"} in t["passos"][0]["ignorados"]
    assert "São Bento" not in t["visitados"]


def test_bfs_bloqueio_isola_destino():
    # A rede é conectada à L3 apenas pela Sé.
    t = bfs("Luz", "República", bloqueadas=["Sé"])
    assert not t["encontrado"]
    assert t["caminho"] == []
    assert t["motivo"].startswith("sem caminho")
    assert t["metricas"]["paradas"] is None


# ---------- DFS ----------

def test_dfs_explora_primeiro_vizinho_e_faz_backtracking():
    t = dfs("Sé", "Liberdade")
    assert t["encontrado"]
    assert t["caminho"] == ["Sé", "Liberdade"]
    # Primeiro vizinho de Sé é São Bento: desce até Tucuruvi e volta.
    assert t["ordem"][:3] == ["Sé", "São Bento", "Luz"]
    assert "Tucuruvi" in t["ordem"]
    assert t["metricas"]["backtracks"] == 10
    assert_caminho_valido(t)


def test_dfs_trace_pilha_lifo():
    t = dfs("Tucuruvi", "Vila Prudente")
    pilha = []
    for p in t["passos"]:
        if p["acao"] in ("empilhar", "avancar", "objetivo"):
            if pilha:
                assert p["de"] == pilha[-1]
            pilha.append(p["no"])
        else:
            assert p["acao"] == "backtrack"
            assert pilha.pop() == p["no"]  # LIFO: sai sempre o topo
            assert p["volta_para"] == (pilha[-1] if pilha else None)
        assert p["pilha"] == pilha
    assert t["caminho"] == pilha
    assert_caminho_valido(t)


@pytest.mark.parametrize("origem, destino", [
    ("Vila Madalena", "Corinthians-Itaquera"),
    ("Jabaquara", "Palmeiras-Barra Funda"),
])
def test_dfs_caminho_valido(origem, destino):
    assert_caminho_valido(dfs(origem, destino))


def test_dfs_bloqueio_isola_destino():
    t = dfs("Luz", "República", bloqueadas=["Sé"])
    assert not t["encontrado"]
    assert t["motivo"].startswith("sem caminho")
    assert t["passos"][-1]["acao"] == "backtrack"
    assert t["passos"][-1]["pilha"] == []


# ---------- comuns ----------

@pytest.mark.parametrize("func", [bfs, dfs])
def test_origem_ou_destino_bloqueados(func):
    assert func("Luz", "Sé", bloqueadas=["Luz"])["motivo"] == "origem bloqueada"
    t = func("Luz", "Sé", bloqueadas=["Sé"])
    assert t["motivo"] == "destino bloqueado"
    assert t["passos"] == []


@pytest.mark.parametrize("func", [bfs, dfs])
def test_origem_igual_destino(func):
    t = func("Sé", "Sé")
    assert t["encontrado"]
    assert t["caminho"] == ["Sé"]
    assert t["metricas"]["paradas"] == 0


@pytest.mark.parametrize("func", [bfs, dfs])
def test_estacao_desconhecida(func):
    with pytest.raises(grafo.EstacaoDesconhecida):
        func("Luz", "Atlântida")


CHAVES_TRACE = {
    "algoritmo", "estrutura", "origem", "destino", "bloqueadas", "passos",
    "ordem", "visitados", "pai", "encontrado", "motivo", "caminho",
    "caminho_arestas", "metricas",
}


@pytest.mark.parametrize("origem, destino, bloqueadas", [
    ("Luz", "Paraíso", []),           # encontrado
    ("Luz", "Paraíso", ["Luz"]),      # origem bloqueada
    ("Luz", "Paraíso", ["Paraíso"]),  # destino bloqueado
    ("Luz", "República", ["Sé"]),     # sem caminho
])
def test_formato_do_trace(origem, destino, bloqueadas):
    b = bfs(origem, destino, bloqueadas)
    d = dfs(origem, destino, bloqueadas)
    assert CHAVES_TRACE | {"niveis"} == set(b)
    assert CHAVES_TRACE == set(d)
    assert {"nos_expandidos", "max_fronteira", "paradas", "passos", "nos_visitados"} == set(b["metricas"])
    assert {"backtracks", "max_fronteira", "profundidade_max", "paradas", "passos",
            "nos_visitados"} == set(d["metricas"])


def test_buscar_despacha_e_valida():
    assert buscar("BFS", "Luz", "Sé")["algoritmo"] == "BFS"
    assert buscar("dfs", "Luz", "Sé")["algoritmo"] == "DFS"
    with pytest.raises(ValueError):
        buscar("a*", "Luz", "Sé")
