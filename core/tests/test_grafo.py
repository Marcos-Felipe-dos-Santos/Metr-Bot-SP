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
    ("Sé", ["São Bento", "Japão-Liberdade", "Anhangabaú", "Pedro II"]),
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


def test_nomes_exatos_do_desafio():
    assert "Japão-Liberdade" in grafo.ESTACOES and "Liberdade" not in grafo.ESTACOES
    assert "Patriarca-Vila Ré" in grafo.ESTACOES and "Patriarca" not in grafo.ESTACOES


def test_locais_minimo_tres_por_linha():
    por_linha = {lid: 0 for lid in grafo.LINHAS}
    for estacao in grafo.LOCAIS_CONHECIDOS.values():
        for lid in grafo.LINHAS_DA_ESTACAO[estacao]:
            por_linha[lid] += 1
    assert all(n >= 3 for n in por_linha.values()), por_linha
    assert len(grafo.LOCAIS_CONHECIDOS) == 21
    assert grafo.LOCAIS_CONHECIDOS["Pinacoteca"] == "Luz"
    assert grafo.LOCAIS_CONHECIDOS["Bairro da Liberdade"] == "Japão-Liberdade"
    assert grafo.LOCAIS_CONHECIDOS["Neo Química Arena"] == "Corinthians-Itaquera"


def test_identificar_estacao_ou_local():
    assert grafo.identificar("catedral da se") == ("local", "Catedral da Sé")
    assert grafo.identificar("SÉ") == ("estacao", "Sé")
    assert grafo.resolver("masp") == "Trianon-Masp"
    assert grafo.resolver_estacao("japao liberdade") == "Japão-Liberdade"
    with pytest.raises(grafo.EstacaoDesconhecida):
        grafo.resolver_estacao("Pinacoteca")


@pytest.mark.parametrize("valor", ["2", "2-Verde", "Linha 2-Verde", "linha 2 verde"])
def test_resolver_linha(valor):
    assert grafo.resolver_linha(valor) == "2"
    assert grafo.nome_linha("2") == "Linha 2-Verde"


def test_resolver_linha_desconhecida():
    with pytest.raises(grafo.LinhaDesconhecida):
        grafo.resolver_linha("Linha 4-Amarela")


def test_indice_sem_colisao():
    assert len(grafo._INDICE) == len(grafo.ESTACOES) + len(grafo.LOCAIS_CONHECIDOS)


def test_resolver_desconhecido():
    with pytest.raises(grafo.EstacaoDesconhecida):
        grafo.resolver("Estação Inexistente")


def test_dossie_hub():
    d = grafo.dossie("Sé")
    assert d["hub"] is True
    assert [l["nome"] for l in d["linhas"]] == ["1-Azul", "3-Vermelha"]
