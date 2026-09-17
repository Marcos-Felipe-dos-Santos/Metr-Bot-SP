import pytest

from core import grafo
from core.planejador import planejar


def test_planejar_resolve_locais_e_roda_as_duas_buscas():
    p = planejar("Shopping Metrô Tucuruvi", "se")
    assert (p["origem"], p["destino"]) == ("Tucuruvi", "Sé")
    assert set(p["buscas"]) == {"BFS", "DFS"}
    assert p["comparacao"]["BFS"]["paradas"] == 10
    assert p["inferencia"]["regras_pendentes"] == ["R1", "R2", "R3", "R4", "R5"]


def test_planejar_bloqueio_vem_da_base_logica():
    p = planejar("Luz", "República", bloqueadas=["sé"], algoritmo="bfs")
    assert p["bloqueadas"] == ["Sé"]
    assert list(p["buscas"]) == ["BFS"]
    assert p["buscas"]["BFS"]["bloqueadas"] == ["Sé"]
    assert p["comparacao"]["BFS"]["encontrado"] is False


def test_diagnostico_baldeacoes():
    d = planejar("Vila Madalena", "Corinthians-Itaquera", algoritmo="bfs")["diagnostico"]
    assert d["obstrucoes"] == []
    assert d["trechos"] == [
        {"linha": "2", "de": "Vila Madalena", "ate": "Paraíso", "paradas": 6},
        {"linha": "1", "de": "Paraíso", "ate": "Sé", "paradas": 4},
        {"linha": "3", "de": "Sé", "ate": "Corinthians-Itaquera", "paradas": 12},
    ]
    assert d["baldeacoes"] == [
        {"estacao": "Paraíso", "de_linha": "2", "para_linha": "1"},
        {"estacao": "Sé", "de_linha": "1", "para_linha": "3"},
    ]


def test_diagnostico_aresta_de_duas_linhas():
    # Brigadeiro→Paraíso→Ana Rosa→Vila Mariana: segue na L2 até Ana Rosa.
    d = planejar("Brigadeiro", "Vila Mariana")["diagnostico"]
    assert [t["linha"] for t in d["trechos"]] == ["2", "1"]
    assert d["baldeacoes"] == [{"estacao": "Ana Rosa", "de_linha": "2", "para_linha": "1"}]
    assert planejar("Paraíso", "Ana Rosa")["diagnostico"]["trechos"] == [
        {"linha": "1", "de": "Paraíso", "ate": "Ana Rosa", "paradas": 1}
    ]


def test_diagnostico_tunel_obstruido():
    p = planejar("Luz", "República", bloqueadas=["Sé", "Jabaquara"])
    d = p["diagnostico"]
    assert d["obstrucoes"] == ["Sé"]
    assert d["trechos"] == [] and d["baldeacoes"] == []
    assert not p["comparacao"]["DFS"]["encontrado"]


def test_bfs_e_dfs_mesma_rota_esforco_diferente():
    # Rede sem ciclos: caminho único; muda só o esforço.
    c = planejar("Vila Madalena", "Corinthians-Itaquera")["comparacao"]
    assert c["BFS"]["caminho"] == c["DFS"]["caminho"]
    assert c["BFS"]["nos_visitados"] != c["DFS"]["nos_visitados"]


def test_planejar_erros():
    with pytest.raises(grafo.EstacaoDesconhecida):
        planejar("Luz", "Atlântida")
    with pytest.raises(ValueError):
        planejar("Luz", "Sé", algoritmo="a*")


# ---------- 6 casos exigidos pelo desafio ----------

@pytest.mark.skip(reason="aguardando texto oficial")
@pytest.mark.parametrize("caso", range(1, 7))
def test_caso_oficial(caso):
    """Preencher origem, destino, bloqueios e resultado esperado do enunciado."""
