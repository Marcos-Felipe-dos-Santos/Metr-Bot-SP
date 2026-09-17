import pytest

from core import grafo, logica
from core.logica import Fato, Regra, encadear_para_frente, inferir

PENDENTE = "aguardando texto oficial"


def test_fatos_da_rede():
    fatos = logica.fatos_da_rede()
    por_predicado = {}
    for f in fatos:
        por_predicado[f.predicado] = por_predicado.get(f.predicado, 0) + 1
    assert por_predicado == {
        "Estacao": 52,
        "Linha": 23 + 14 + 18,
        "Integracao": 3,
        "Conectada": 2 * 51,  # 52 arestas nas linhas, Paraíso–Ana Rosa compartilhada
    }
    assert Fato("Linha", ("Sé", "3")) in fatos
    assert Fato("Conectada", ("Paraíso", "Ana Rosa")) in fatos


def test_fatos_bloqueada():
    fatos = logica.fatos_da_rede(["Sé"])
    assert Fato("Bloqueada", ("Sé",)) in fatos
    with pytest.raises(grafo.EstacaoDesconhecida):
        logica.fatos_da_rede(["Atlântida"])


def test_regras_oficiais_estao_pendentes():
    assert [r.id for r in logica.REGRAS] == ["R1", "R2", "R3", "R4", "R5"]
    assert all(r.pendente and r.texto_oficial is None for r in logica.REGRAS)


def test_sem_regras_nada_e_inferido():
    res = inferir(["Luz"])
    assert res.inferencias == []
    assert res.fatos_finais == res.fatos_iniciais
    dados = res.para_json()
    assert dados["regras_pendentes"] == ["R1", "R2", "R3", "R4", "R5"]
    assert dados["bloqueadas"] == ["Luz"]
    assert dados["fatos_derivados"] == []


def test_motor_registra_regra_e_justificativa():
    # Regra de TESTE (não oficial): só valida o mecanismo do encadeamento.
    def vizinha_de_bloqueada(base):
        saida = []
        for f in base:
            if f.predicado == "Conectada" and Fato("Bloqueada", (f.args[0],)) in base:
                saida.append((Fato("VizinhaDeBloqueada", (f.args[1],)),
                              [Fato("Bloqueada", (f.args[0],)), f]))
        return saida

    def alerta(base):
        return [(Fato("Alerta", f.args), [f]) for f in base
                if f.predicado == "VizinhaDeBloqueada"]

    regras = [Regra("T2", aplicar=alerta), Regra("T1", aplicar=vizinha_de_bloqueada)]
    res = encadear_para_frente(logica.fatos_da_rede(["Sé"]), regras)

    derivados = {str(f) for f in res.fatos_finais[len(res.fatos_iniciais):]}
    assert derivados == {
        "VizinhaDeBloqueada(São Bento)", "VizinhaDeBloqueada(Liberdade)",
        "VizinhaDeBloqueada(Anhangabaú)", "VizinhaDeBloqueada(Pedro II)",
        "Alerta(São Bento)", "Alerta(Liberdade)", "Alerta(Anhangabaú)", "Alerta(Pedro II)",
    }
    primeira = res.inferencias[0]
    assert primeira["regra"] == "T1" and primeira["iteracao"] == 1
    assert [j["texto"] for j in primeira["justificativa"]][0] == "Bloqueada(Sé)"
    # T2 só dispara depois de T1 (ponto fixo em mais de uma iteração).
    assert {i["iteracao"] for i in res.inferencias if i["regra"] == "T2"} == {2}
    assert [i["n"] for i in res.inferencias] == list(range(1, 9))


@pytest.mark.skip(reason=PENDENTE)
@pytest.mark.parametrize("regra", ["R1", "R2", "R3", "R4", "R5"])
def test_regra_oficial(regra):
    """Implementar com o texto literal da regra no enunciado."""
