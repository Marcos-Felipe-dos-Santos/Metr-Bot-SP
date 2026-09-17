import json

import httpx
import pytest
from fastapi.testclient import TestClient
from groq import APIConnectionError

import main

cliente = TestClient(main.app)


def eventos_sse(texto: str) -> list[tuple[str, dict]]:
    saida = []
    for bloco in texto.strip().split("\n\n"):
        linhas = dict(l.split(": ", 1) for l in bloco.splitlines())
        saida.append((linhas["event"], json.loads(linhas["data"])))
    return saida


def narrar(**params):
    r = cliente.get("/api/narrar", params=params)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return eventos_sse(r.text)


def texto(ev):
    return "".join(d["texto"] for t, d in ev if t == "trecho")


@pytest.fixture
def sem_chave(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


@pytest.fixture
def com_chave(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "chave-de-teste")
    monkeypatch.delenv("GROQ_MODEL", raising=False)


# ---------- dados ----------

def test_estacoes():
    d = cliente.get("/api/estacoes").json()
    assert len(d["estacoes"]) == 52
    assert d["hubs"] == ["Sé", "Paraíso", "Ana Rosa"]  # deduzidos pela R6
    assert [l["cor"] for l in d["linhas"]] == ["#0054A6", "#009640", "#EF3A46"]
    assert [l["nome_logico"] for l in d["linhas"]] == ["Linha 1-Azul", "Linha 2-Verde", "Linha 3-Vermelha"]


def test_locais():
    d = cliente.get("/api/locais").json()
    assert len(d["locais"]) == 21
    assert {"nome": "Pinacoteca", "estacao": "Luz", "linhas": ["1-Azul"]} in d["locais"]


def test_tabela_verdade():
    d = cliente.get("/api/tabela-verdade").json()
    assert d["formula"] == "pode_embarcar ≡ P ∧ (¬Q ∨ R)"
    assert len(d["linhas"]) == 8


# ---------- rota ----------

def test_rota_com_locais_e_alerta():
    r = cliente.post("/api/rota", json={
        "origem": "Catedral da Sé", "destino": "Pinacoteca",
        "acessibilidade": True, "manutencao": ["Luz"], "algoritmo": "bfs",
    })
    assert r.status_code == 200
    d = r.json()
    assert (d["origem"], d["destino"]) == ("Sé", "Luz")
    assert d["comparacao"]["BFS"]["caminho"] == ["Sé", "São Bento", "Luz"]
    assert d["alertas"] == [{"papel": "destino", "estacao": "Luz"}]
    assert d["diagnostico"]["tempo_min"] == 4
    assert d["regras_disparadas"] == ["R1", "R2", "R4", "R5", "R6"]


def test_rota_caso_6_desvio():
    d = cliente.post("/api/rota", json={
        "origem": "Vila Prudente", "destino": "Jabaquara", "fechadas": ["Paraíso"],
    }).json()
    assert set(d["buscas"]) == {"BFS", "DFS"}
    assert d["comparacao"]["BFS"]["paradas"] == 13
    assert d["diagnostico"]["baldeacoes"] == [
        {"estacao": "Ana Rosa", "de_linha": "2", "para_linha": "1"}]


def test_rota_linha_paralisada_e_pico():
    d = cliente.post("/api/rota", json={
        "origem": "Luz", "destino": "Sé", "paralisadas": ["Linha 3-Vermelha"],
        "horario_pico": True, "lotadas": ["São Bento"], "algoritmo": "dfs",
    }).json()
    assert list(d["buscas"]) == ["DFS"]
    assert "Brás" in d["bloqueadas"] and "Sé" not in d["bloqueadas"]
    assert d["alertas_lotacao"] == ["São Bento"]
    assert d["regras_disparadas"] == ["R1", "R2", "R6", "R7", "R8"]


@pytest.mark.parametrize("corpo, status", [
    ({"origem": "Luz", "destino": "Atlântida"}, 404),
    ({"origem": "Luz", "destino": "Sé", "fechadas": ["Pinacoteca"]}, 404),
    ({"origem": "Luz", "destino": "Sé", "paralisadas": ["4"]}, 404),
    ({"origem": "Luz", "destino": "Sé", "algoritmo": "a*"}, 422),
    ({"origem": "Luz"}, 422),
])
def test_rota_erros(corpo, status):
    r = cliente.post("/api/rota", json=corpo)
    assert r.status_code == status


# ---------- inferência ----------

def test_inferencia_domino_do_pdf():
    d = cliente.post("/api/inferencia", json={
        "destino": "Pinacoteca", "acessibilidade": True, "manutencao": ["Luz"],
    }).json()
    assert d["destino"] == ["Luz"]
    assert d["alertas"] == [{"papel": "destino", "estacao": "Luz"}]
    assert d["integracoes"] == ["Sé", "Paraíso", "Ana Rosa"]
    assert "fatos_iniciais" not in d
    assert [r["id"] for r in d["regras"]] == [f"R{i}" for i in range(1, 9)]


def test_inferencia_base_completa():
    d = cliente.post("/api/inferencia", json={"fechadas": ["se"], "incluir_base": True}).json()
    assert d["bloqueadas"] == ["Sé"]
    assert len(d["fatos_iniciais"]) == 52 + 55 + 21 + 1


def test_inferencia_estacao_desconhecida():
    assert cliente.post("/api/inferencia", json={"fechadas": ["X"]}).status_code == 404


# ---------- narração ----------

def test_narrar_offline_sem_chave(sem_chave):
    ev = narrar(origem="Vila Madalena", destino="Corinthians-Itaquera")
    tipos = [t for t, _ in ev]
    assert tipos[0] == "fatos" and tipos[1] == "inicio" and tipos[-1] == "fim"
    assert set(tipos[2:-1]) == {"trecho"}
    assert ev[1][1] == {"fonte": "offline", "motivo": "GROQ_API_KEY não configurada",
                        "reiniciar": False}
    t = texto(ev)
    assert "Na Paraíso, troque para a Linha 1-Azul" in t
    assert "Na Sé, troque para a Linha 3-Vermelha" in t
    assert "Total: 22 paradas, 2 baldeação(ões), cerca de 44 minutos" in t
    assert "DFS: 38 estações visitadas" in t


def test_narrar_com_local_e_alerta(sem_chave):
    ev = narrar(origem="Catedral da Sé", destino="Pinacoteca", acessibilidade="true",
                manutencao=["Luz"], algoritmo="bfs")
    fatos = ev[0][1]
    assert fatos["pedido"]["destino"] == {"tipo": "local", "nome": "Pinacoteca"}
    assert fatos["alertas"] == [{"papel": "destino", "estacao": "Luz"}]
    t = texto(ev)
    assert "pedido de Catedral da Sé (Sé) até Pinacoteca (Luz)" in t
    assert "Atenção: elevador em manutenção na Luz (destino)." in t


def test_narrar_tunel_obstruido(sem_chave):
    ev = narrar(origem="Luz", destino="República", fechadas=["Sé"])
    fatos = ev[0][1]
    assert fatos["encontrado"] is False and fatos["obstrucoes"] == ["Sé"]
    t = texto(ev)
    assert "Estações fechadas: Sé." in t
    assert "Túnel obstruído: Sé" in t
    assert "autorizada" not in t


def test_narrar_linha_paralisada_e_pico(sem_chave):
    ev = narrar(origem="Sé", destino="Brás", paralisadas=["3"], horario_pico="true",
                lotadas=["Sé"], algoritmo="bfs")
    t = texto(ev)
    assert "Linha paralisada: 3-Vermelha." in t
    assert "destino, Brás, está bloqueada" in t
    assert "Horário de pico: lotação em Sé." in t


def test_narrar_estacao_desconhecida():
    assert cliente.get("/api/narrar", params={"origem": "Luz", "destino": "X"}).status_code == 404


def test_narrar_com_llm(com_chave, monkeypatch):
    recebidos = {}

    async def falso_llama(fatos, chave):
        recebidos["fatos"], recebidos["chave"] = fatos, chave
        for pedaco in ["Rota ", "narrada."]:
            yield pedaco

    monkeypatch.setattr(main, "_trechos_llama", falso_llama)
    ev = narrar(origem="Luz", destino="Sé")
    assert ev[1] == ("inicio", {"fonte": "llama", "modelo": "llama-3.3-70b-versatile"})
    assert [d["texto"] for t, d in ev if t == "trecho"] == ["Rota ", "narrada."]
    assert ev[-1] == ("fim", {"fonte": "llama"})
    assert recebidos["chave"] == "chave-de-teste"
    assert recebidos["fatos"] == ev[0][1]  # o LLM só recebe os fatos do core


def _erro_groq():
    return APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))


def test_narrar_llm_fora_do_ar(com_chave, monkeypatch):
    async def falha(fatos, chave):
        raise _erro_groq()
        yield  # pragma: no cover

    monkeypatch.setattr(main, "_trechos_llama", falha)
    ev = narrar(origem="Luz", destino="Sé")
    assert ev[1] == ("inicio", {"fonte": "offline",
                                "motivo": "LLM indisponível (APIConnectionError)",
                                "reiniciar": False})
    assert ev[-1] == ("fim", {"fonte": "offline"})


def test_narrar_llm_cai_no_meio(com_chave, monkeypatch):
    async def cai(fatos, chave):
        yield "Começo "
        raise _erro_groq()

    monkeypatch.setattr(main, "_trechos_llama", cai)
    ev = narrar(origem="Luz", destino="Sé")
    tipos = [t for t, _ in ev]
    assert tipos[:3] == ["fatos", "inicio", "trecho"]
    reinicio = ev[3]
    assert reinicio[0] == "inicio" and reinicio[1]["fonte"] == "offline"
    assert reinicio[1]["reiniciar"] is True
    assert ev[-1] == ("fim", {"fonte": "offline"})


def test_narrar_llm_resposta_vazia(com_chave, monkeypatch):
    async def vazio(fatos, chave):
        return
        yield  # pragma: no cover

    monkeypatch.setattr(main, "_trechos_llama", vazio)
    ev = narrar(origem="Luz", destino="Sé")
    assert ev[1][1]["motivo"] == "resposta vazia do LLM"


def test_erro_inesperado_nao_e_mascarado(com_chave, monkeypatch):
    async def bug(fatos, chave):
        raise KeyError("bug")
        yield  # pragma: no cover

    monkeypatch.setattr(main, "_trechos_llama", bug)
    with pytest.raises(KeyError):
        cliente.get("/api/narrar", params={"origem": "Luz", "destino": "Sé"})
