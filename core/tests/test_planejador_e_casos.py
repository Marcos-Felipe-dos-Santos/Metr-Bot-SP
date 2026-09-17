import pytest

from core import grafo
from core.planejador import PedidoIncompleto, TEMPO_POR_TRECHO, planejar, validar_nomes


def resumo(p, alg="BFS"):
    c = p["comparacao"][alg]
    return c["paradas"], [b["estacao"] for b in p["diagnostico"]["baldeacoes"]], c["caminho"]


# ---------- 6 casos obrigatórios do desafio (BFS) ----------

def test_caso_1_tucuruvi_corinthians():
    paradas, baldeacoes, _ = resumo(planejar("Tucuruvi", "Corinthians-Itaquera", algoritmo="bfs"))
    assert paradas == 22
    assert baldeacoes == ["Sé"]


def test_caso_2_vila_madalena_jabaquara():
    paradas, baldeacoes, _ = resumo(planejar("Vila Madalena", "Jabaquara", algoritmo="bfs"))
    assert paradas == 14
    assert len(baldeacoes) == 1 and baldeacoes[0] in {"Paraíso", "Ana Rosa"}


def test_caso_3_palmeiras_vila_prudente():
    paradas, baldeacoes, _ = resumo(planejar("Palmeiras-Barra Funda", "Vila Prudente", algoritmo="bfs"))
    assert paradas == 16
    assert len(baldeacoes) == 2
    assert baldeacoes[0] == "Sé" and baldeacoes[1] in {"Paraíso", "Ana Rosa"}


def test_caso_4_tucuruvi_bras_se_fechada():
    p = planejar("Tucuruvi", "Brás", fechadas=["Sé"], algoritmo="bfs")
    assert p["comparacao"]["BFS"]["encontrado"] is False
    assert p["comparacao"]["BFS"]["caminho"] == []


def test_caso_5_vila_madalena_jabaquara_paraiso_fechada():
    p = planejar("Vila Madalena", "Jabaquara", fechadas=["Paraíso"], algoritmo="bfs")
    assert p["comparacao"]["BFS"]["encontrado"] is False
    assert p["diagnostico"]["obstrucoes"] == ["Paraíso"]


def test_caso_6_vila_prudente_jabaquara_paraiso_fechada():
    paradas, baldeacoes, caminho = resumo(
        planejar("Vila Prudente", "Jabaquara", fechadas=["Paraíso"], algoritmo="bfs"))
    assert paradas == 13
    assert "Ana Rosa" in caminho and "Paraíso" not in caminho
    assert baldeacoes == ["Ana Rosa"]


# ---------- exemplos da aula (rodar_testes do PDF) ----------

def test_r2_local_conhecido_vira_destino():
    p = planejar("Catedral da Sé", "Pinacoteca", algoritmo="bfs")
    assert p["destino"] == "Luz" and p["comparacao"]["BFS"]["paradas"] == 2
    assert p["diagnostico"]["tempo_min"] == 2 * TEMPO_POR_TRECHO


def test_r4_r5_alerta_no_destino():
    p = planejar("Sé", "Luz", acessibilidade=True, manutencao=["Luz"], algoritmo="bfs")
    assert p["alertas"] == [{"papel": "destino", "estacao": "Luz"}]
    assert p["regras_disparadas"] == ["R1", "R2", "R4", "R5", "R6"]


def test_passar_pela_estacao_sem_elevador_nao_gera_alerta():
    p = planejar("Sé", "Tiradentes", acessibilidade=True, manutencao=["Luz"], algoritmo="bfs")
    assert p["alertas"] == [] and "Luz" in p["comparacao"]["BFS"]["caminho"]
    assert p["bloqueadas"] == []


def test_estacao_fechada_no_meio_sem_rota():
    p = planejar("Sé", "Jabaquara", fechadas=["Paraíso"], algoritmo="bfs")
    assert p["comparacao"]["BFS"]["caminho"] == []


# ---------- R7 / R8 no planejador ----------

def test_r7_linha_2_paralisada_mantem_integracoes():
    p = planejar("Tucuruvi", "Jabaquara", paralisadas=["Linha 2-Verde"], algoritmo="bfs")
    assert p["comparacao"]["BFS"]["paradas"] == 22  # a L1 passa por Paraíso e Ana Rosa
    assert "Paraíso" not in p["bloqueadas"] and "Brigadeiro" in p["bloqueadas"]
    assert "R7" in p["regras_disparadas"]


def test_r7_linha_paralisada_isola_destino():
    p = planejar("Sé", "Brás", paralisadas=["3"], algoritmo="bfs")
    assert p["comparacao"]["BFS"]["motivo"] == "destino bloqueado"


def test_r8_alerta_de_lotacao_sem_bloquear():
    p = planejar("Luz", "Sé", horario_pico=True, lotadas=["São Bento"], algoritmo="bfs")
    assert p["alertas_lotacao"] == ["São Bento"]
    assert "São Bento" in p["comparacao"]["BFS"]["caminho"]


# ---------- estrutura da saída ----------

def test_planejar_ambos_mesma_rota_esforco_diferente():
    c = planejar("Vila Madalena", "Corinthians-Itaquera")["comparacao"]
    assert c["BFS"]["caminho"] == c["DFS"]["caminho"]
    assert c["BFS"]["nos_visitados"] != c["DFS"]["nos_visitados"]
    assert c["BFS"]["tempo_min"] == c["DFS"]["tempo_min"] == 22 * TEMPO_POR_TRECHO


def test_planejar_cenario_canonico():
    p = planejar("shopping metrô tucuruvi", "se", fechadas=["BRÁS"], lotadas=["luz"],
                 paralisadas=["3-vermelha"], algoritmo="dfs")
    assert p["cenario"] == {
        "origem": {"tipo": "local", "nome": "Shopping Metrô Tucuruvi"},
        "destino": {"tipo": "estacao", "nome": "Sé"},
        "acessibilidade": False, "fechadas": ["Brás"], "manutencao": [],
        "paralisadas": ["3"], "horario_pico": False, "lotadas": ["Luz"],
    }
    assert (p["origem"], p["destino"]) == ("Tucuruvi", "Sé")
    assert list(p["buscas"]) == ["DFS"]


def test_diagnostico_trechos():
    d = planejar("Vila Madalena", "Corinthians-Itaquera", algoritmo="bfs")["diagnostico"]
    assert d["trechos"] == [
        {"linha": "2", "de": "Vila Madalena", "ate": "Paraíso", "paradas": 6},
        {"linha": "1", "de": "Paraíso", "ate": "Sé", "paradas": 4},
        {"linha": "3", "de": "Sé", "ate": "Corinthians-Itaquera", "paradas": 12},
    ]
    assert d["tempo_min"] == 44


def test_diagnostico_sem_rota():
    d = planejar("Luz", "República", fechadas=["Sé", "Jabaquara"])["diagnostico"]
    assert d["obstrucoes"] == ["Sé"]
    assert d["trechos"] == [] and d["baldeacoes"] == [] and d["tempo_min"] is None


def test_planejar_erros():
    with pytest.raises(grafo.EstacaoDesconhecida):
        planejar("Luz", "Atlântida")
    with pytest.raises(grafo.EstacaoDesconhecida):
        planejar("Luz", "Sé", fechadas=["Pinacoteca"])  # fechada precisa ser estação
    with pytest.raises(grafo.LinhaDesconhecida):
        planejar("Luz", "Sé", paralisadas=["4"])
    with pytest.raises(ValueError):
        planejar("Luz", "Sé", algoritmo="a*")
    assert issubclass(PedidoIncompleto, ValueError)


# ---------- validação de nomes (intérprete) ----------

def test_validar_nomes_preserva_local_e_aponta_invalidos():
    v = validar_nomes("shopping metrô tucuruvi", "se", ["LUZ", "Atlântida", "luz", "Pinacoteca"])
    assert v == {
        "origem": "Shopping Metrô Tucuruvi",
        "destino": "Sé",
        "fechadas": ["Luz"],
        "invalidos": ["Atlântida", "Pinacoteca"],
    }


def test_validar_nomes_nao_aproxima():
    v = validar_nomes("Shopping Tucuruvi", None)
    assert v["origem"] is None and v["destino"] is None
    assert v["invalidos"] == ["Shopping Tucuruvi"]
