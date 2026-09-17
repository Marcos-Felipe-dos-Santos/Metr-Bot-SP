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
