import pytest

from core import grafo


def test_total_de_estacoes_e_linhas():
    assert len(grafo.ESTACOES) == 52
    assert len(set(grafo.ESTACOES)) == 52
    tamanhos = {lid: len(d["estacoes"]) for lid, d in grafo.LINHAS.items()}
    assert tamanhos == {"1": 23, "2": 14, "3": 18}


def test_hubs_sao_se_paraiso_ana_rosa():
    assert set(grafo.HUBS) == {"Sé", "Paraíso", "Ana Rosa"}
    assert grafo.LINHAS_DA_ESTACAO["Sé"] == ["1", "3"]
    assert grafo.LINHAS_DA_ESTACAO["Paraíso"] == ["1", "2"]
    assert grafo.LINHAS_DA_ESTACAO["Ana Rosa"] == ["1", "2"]


@pytest.mark.parametrize("estacao, esperado", [
    ("Sé", ["São Bento", "Liberdade", "Anhangabaú", "Pedro II"]),
    ("Paraíso", ["Vergueiro", "Ana Rosa", "Brigadeiro"]),
    ("Ana Rosa", ["Paraíso", "Vila Mariana", "Chácara Klabin"]),
    ("Tucuruvi", ["Parada Inglesa"]),
    ("Vila Prudente", ["Tamanduateí"]),
    ("Brás", ["Pedro II", "Bresser-Mooca"]),
])
def test_convencao_de_vizinhos(estacao, esperado):
    assert grafo.vizinhos(estacao) == esperado


def test_adjacencia_simetrica_e_sem_lacos():
    for est, viz in grafo.ADJACENCIA.items():
        assert est not in viz
        assert len(viz) == len(set(viz))
        for v in viz:
            assert est in grafo.ADJACENCIA[v]


def test_linhas_da_aresta():
    assert grafo.linhas_da_aresta("Paraíso", "Ana Rosa") == ["1", "2"]
    assert grafo.linhas_da_aresta("Sé", "Pedro II") == ["3"]
    assert grafo.linhas_da_aresta("Luz", "São Bento") == ["1"]


def test_cores_oficiais():
    assert grafo.CORES == {"1": "#0054A6", "2": "#009640", "3": "#EF3A46"}


@pytest.mark.parametrize("entrada, esperado", [
    ("Shopping Metrô Tucuruvi", "Tucuruvi"),
    ("shopping metro tucuruvi", "Tucuruvi"),
    ("se", "Sé"),
    ("TRIANON MASP", "Trianon-Masp"),
    ("Paraíso", "Paraíso"),
])
def test_resolver_nomes_e_locais(entrada, esperado):
    assert grafo.resolver(entrada) == esperado


def test_indice_sem_colisao():
    assert len(grafo._INDICE) == len(grafo.ESTACOES) + len(grafo.LOCAIS_CONHECIDOS)


def test_resolver_desconhecido():
    with pytest.raises(grafo.EstacaoDesconhecida):
        grafo.resolver("Estação Inexistente")


def test_dossie_hub():
    d = grafo.dossie("Sé")
    assert d["hub"] is True
    assert [l["nome"] for l in d["linhas"]] == ["1-Azul", "3-Vermelha"]
