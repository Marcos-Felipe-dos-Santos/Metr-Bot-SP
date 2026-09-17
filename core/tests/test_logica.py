"""Regras R1–R8 com os exemplos do desafio.pdf (Parte 4 e Desafio)."""
import pytest

from core import grafo, logica
from core.logica import Cenario, Fato, encadear_para_frente, inferir


def derivados(res):
    return {str(f) for f in res.fatos_finais[len(res.fatos_iniciais):]}


def justificativa(res, fato_texto):
    for i in res.inferencias:
        if i["fato"]["texto"] == fato_texto:
            return i["regra"], [j["texto"] for j in i["justificativa"]]
    raise AssertionError(f"{fato_texto} não foi inferido")


# ---------- base de fatos ----------

def test_fatos_base():
    fatos = logica.fatos_base()
    contagem = {}
    for f in fatos:
        contagem[f.predicado] = contagem.get(f.predicado, 0) + 1
    assert contagem == {"estacao": 52, "pertence": 23 + 14 + 18, "proximo_de": 21}
    assert Fato("pertence", ("Sé", "Linha 3-Vermelha")) in fatos
    assert Fato("proximo_de", ("Pinacoteca", "Luz")) in fatos


def test_integracao_nunca_e_digitada():
    predicados = {f.predicado for f in logica.fatos_base()}
    assert "integracao" not in predicados and "bloqueada" not in predicados


def test_cenario_vira_fatos():
    c = Cenario(origem=("local", "Catedral da Sé"), destino=("estacao", "Luz"),
                acessibilidade=True, fechadas=["Brás"], manutencao=["Luz"],
                paralisadas=["3"], horario_pico=True, lotadas=["Sé"])
    assert {str(f) for f in c.fatos()} == {
        "usuario_esta_em(Catedral da Sé)", "usuario_quer_ir_estacao(Luz)",
        "precisa_acessibilidade", "fechada(Brás)", "elevador_em_manutencao(Luz)",
        "paralisada(Linha 3-Vermelha)", "horario_pico", "lotada(Sé)",
    }


def test_regras_catalogadas():
    assert [r.id for r in logica.REGRAS] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]
    formulas = {r.id: r.formula for r in logica.REGRAS}
    assert formulas["R1"] == "∀l ∀e (usuario_esta_em(l) ∧ proximo_de(l,e) → origem(e))"
    assert formulas["R2"] == "∀l ∀e (usuario_quer_ir(l) ∧ proximo_de(l,e) → destino(e))"
    assert formulas["R3"] == "∀e (fechada(e) → bloqueada(e))"
    assert formulas["R4"] == "∀e (precisa_acessibilidade ∧ elevador_em_manutencao(e) → inacessivel(e))"
    assert formulas["R5"] == "∀p ∀e (papel(p,e) ∧ inacessivel(e) → alerta(p,e))"
    assert formulas["R6"] == "∀e ∀l1 ∀l2 (pertence(e,l1) ∧ pertence(e,l2) ∧ l1 ≠ l2 → integracao(e))"
    assert [r.id for r in logica.REGRAS if r.do_grupo] == ["R7", "R8"]


# ---------- R1–R5 ----------

def test_r1_local_vira_origem():
    res = inferir(Cenario(origem=("local", "Catedral da Sé")))
    assert res.valores("origem") == ["Sé"]
    assert justificativa(res, "origem(Sé)") == (
        "R1", ["usuario_esta_em(Catedral da Sé)", "proximo_de(Catedral da Sé, Sé)"])


def test_r1_estacao_vira_origem():
    res = inferir(Cenario(origem=("estacao", "Luz")))
    assert justificativa(res, "origem(Luz)") == ("R1", ["usuario_esta_na_estacao(Luz)"])


def test_r2_pinacoteca_vira_destino_luz():
    # "Akinator mode" do PDF: ninguém disse que o destino é Luz.
    res = inferir(Cenario(destino=("local", "Pinacoteca")))
    assert res.valores("destino") == ["Luz"]
    assert justificativa(res, "destino(Luz)") == (
        "R2", ["usuario_quer_ir(Pinacoteca)", "proximo_de(Pinacoteca, Luz)"])


def test_r3_fechada_vira_bloqueada():
    res = inferir(Cenario(fechadas=["Paraíso"]))
    assert res.valores("bloqueada") == ["Paraíso"]
    assert justificativa(res, "bloqueada(Paraíso)") == ("R3", ["fechada(Paraíso)"])


def test_r4_exige_acessibilidade():
    sem = inferir(Cenario(manutencao=["Luz"]))
    assert sem.valores("inacessivel") == []
    com = inferir(Cenario(acessibilidade=True, manutencao=["Luz"]))
    assert com.valores("inacessivel") == ["Luz"]
    assert com.valores("bloqueada") == []  # sutileza da R4: não vira bloqueada


def test_dominó_do_pdf_r2_r4_r5():
    """Célula 14 do PDF: destino(Luz) e inacessivel(Luz) na rodada 1, alerta na 2."""
    res = inferir(Cenario(destino=("local", "Pinacoteca"), acessibilidade=True, manutencao=["Luz"]))
    rodadas = {i["fato"]["texto"]: (i["regra"], i["iteracao"]) for i in res.inferencias
               if i["regra"] in ("R2", "R4", "R5")}
    assert rodadas == {
        "destino(Luz)": ("R2", 1),
        "inacessivel(Luz)": ("R4", 1),
        "alerta(destino, Luz)": ("R5", 2),
    }
    assert justificativa(res, "alerta(destino, Luz)") == ("R5", ["destino(Luz)", "inacessivel(Luz)"])


def test_r5_so_para_origem_ou_destino():
    res = inferir(Cenario(origem=("estacao", "Sé"), destino=("estacao", "Tiradentes"),
                          acessibilidade=True, manutencao=["Luz", "Sé"]))
    assert res.valores("inacessivel") == ["Luz", "Sé"]
    assert [str(f) for f in res.consulta("alerta")] == ["alerta(origem, Sé)"]


# ---------- R6 ----------

def test_r6_deduz_as_tres_integracoes():
    res = inferir()
    assert res.valores("integracao") == ["Sé", "Paraíso", "Ana Rosa"]
    assert justificativa(res, "integracao(Sé)") == (
        "R6", ["pertence(Sé, Linha 1-Azul)", "pertence(Sé, Linha 3-Vermelha)"])


def test_r6_bate_com_a_estrutura_do_grafo():
    assert inferir().valores("integracao") == grafo.HUBS


# ---------- R7 (grupo) ----------

def test_r7_linha_paralisada_poupa_integracoes():
    res = inferir(Cenario(paralisadas=["3"]))
    bloqueadas = res.valores("bloqueada")
    assert len(bloqueadas) == 17 and "Sé" not in bloqueadas
    assert set(bloqueadas) == set(grafo.LINHAS["3"]["estacoes"]) - {"Sé"}
    assert justificativa(res, "bloqueada(Brás)") == (
        "R7", ["paralisada(Linha 3-Vermelha)", "pertence(Brás, Linha 3-Vermelha)", "¬integracao(Brás)"])


def test_r7_roda_depois_da_r6():
    """Estratificação: a negação só é avaliada com as integrações já deduzidas."""
    res = inferir(Cenario(paralisadas=["2"]))
    it = {i["fato"]["texto"]: i["iteracao"] for i in res.inferencias}
    assert max(it[f"integracao({h})"] for h in grafo.HUBS) < min(
        v for k, v in it.items() if k.startswith("bloqueada("))
    assert "Paraíso" not in res.valores("bloqueada")
    assert "Ana Rosa" not in res.valores("bloqueada")


# ---------- R8 (grupo) ----------

def test_r8_horario_de_pico():
    assert inferir(Cenario(lotadas=["Sé"])).valores("alerta_lotacao") == []
    res = inferir(Cenario(horario_pico=True, lotadas=["Sé", "Brás"]))
    assert res.valores("alerta_lotacao") == ["Sé", "Brás"]
    assert res.valores("bloqueada") == []
    assert justificativa(res, "alerta_lotacao(Sé)") == ("R8", ["horario_pico", "lotada(Sé)"])


# ---------- motor ----------

def test_motor_para_no_ponto_fixo_e_numera():
    res = inferir(Cenario(origem=("local", "Catedral da Sé"), destino=("local", "Pinacoteca"),
                          acessibilidade=True, manutencao=["Luz"]))
    assert [i["n"] for i in res.inferencias] == list(range(1, len(res.inferencias) + 1))
    assert res.regras_disparadas == ["R1", "R2", "R4", "R5", "R6"]
    assert derivados(res) >= {"origem(Sé)", "destino(Luz)", "alerta(destino, Luz)"}


def test_motor_aceita_regras_customizadas():
    regra = logica.Regra("T1", "teste", "p → q", "regra de teste (não oficial)",
                         lambda base: [(Fato("q"), [Fato("p")])] if Fato("p") in base else [])
    res = encadear_para_frente([Fato("p")], [regra])
    assert derivados(res) == {"q"}


def test_para_json():
    dados = inferir(Cenario(origem=("estacao", "Sé"), destino=("estacao", "Luz"),
                            acessibilidade=True, manutencao=["Luz"])).para_json()
    assert dados["alertas"] == [{"papel": "destino", "estacao": "Luz"}]
    assert dados["integracoes"] == ["Sé", "Paraíso", "Ana Rosa"]
    assert "fatos_iniciais" not in dados
    assert len(dados["regras"]) == 8


# ---------- lógica proposicional ----------

def test_tabela_verdade_do_pdf():
    t = logica.tabela_verdade()
    assert t["formula"] == "pode_embarcar ≡ P ∧ (¬Q ∨ R)"
    assert [l["resultado"] for l in t["linhas"]] == [True, False, True, True, False, False, False, False]
    assert (t["linhas"][1]["P"], t["linhas"][1]["Q"], t["linhas"][1]["R"]) == (True, True, False)


@pytest.mark.parametrize("P, Q, R, esperado", [
    (True, True, False, False),   # aberta, precisa, elevador quebrado
    (True, False, False, True),   # aberta, não precisa (usa a escada)
    (False, False, True, False),  # fechada: nunca pode
])
def test_pode_embarcar(P, Q, R, esperado):
    assert logica.pode_embarcar(P, Q, R) is esperado
