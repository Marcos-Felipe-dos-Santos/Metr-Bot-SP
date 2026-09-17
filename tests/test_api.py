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
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    return eventos_sse(r.text)


@pytest.fixture
def sem_chave(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


@pytest.fixture
def com_chave(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "chave-de-teste")


# ---------- dados ----------

def test_estacoes():
    d = cliente.get("/api/estacoes").json()
    assert len(d["estacoes"]) == 52
    assert d["hubs"] == ["Sé", "Paraíso", "Ana Rosa"]
    assert [l["cor"] for l in d["linhas"]] == ["#0054A6", "#009640", "#EF3A46"]


def test_locais():
    d = cliente.get("/api/locais").json()
    assert d["pendente"] is True
    assert d["locais"] == [{"nome": "Shopping Metrô Tucuruvi", "estacao": "Tucuruvi"}]


# ---------- rota ----------

def test_rota_ambos():
    r = cliente.post("/api/rota", json={"origem": "Shopping Metrô Tucuruvi", "destino": "República"})
    assert r.status_code == 200
    d = r.json()
    assert set(d["buscas"]) == {"BFS", "DFS"}
    assert d["buscas"]["BFS"]["caminho"][-1] == "República"
    assert d["diagnostico"]["baldeacoes"] == [
        {"estacao": "Sé", "de_linha": "1", "para_linha": "3"}
    ]


def test_rota_bloqueada():
    d = cliente.post("/api/rota", json={
        "origem": "Luz", "destino": "República", "bloqueadas": ["Sé"], "algoritmo": "dfs",
    }).json()
    assert list(d["buscas"]) == ["DFS"]
    assert d["comparacao"]["DFS"]["encontrado"] is False
    assert d["diagnostico"]["obstrucoes"] == ["Sé"]


def test_rota_erros():
    r = cliente.post("/api/rota", json={"origem": "Luz", "destino": "Atlântida"})
    assert r.status_code == 404
    assert "Atlântida" in r.json()["detail"]
    r = cliente.post("/api/rota", json={"origem": "Luz", "destino": "Sé", "algoritmo": "a*"})
    assert r.status_code == 422


# ---------- inferência ----------

def test_inferencia():
    d = cliente.post("/api/inferencia", json={"bloqueadas": ["se"]}).json()
    assert d["bloqueadas"] == ["Sé"]
    assert d["regras_pendentes"] == ["R1", "R2", "R3", "R4", "R5"]
    assert d["inferencias"] == []
    assert "fatos_iniciais" not in d
    d = cliente.post("/api/inferencia", json={"incluir_rede": True}).json()
    assert len(d["fatos_iniciais"]) == d["total_fatos"]


def test_inferencia_estacao_desconhecida():
    assert cliente.post("/api/inferencia", json={"bloqueadas": ["X"]}).status_code == 404


# ---------- narração ----------

def test_narrar_offline_sem_chave(sem_chave):
    ev = narrar(origem="Vila Madalena", destino="Corinthians-Itaquera")
    tipos = [t for t, _ in ev]
    assert tipos[0] == "fatos" and tipos[1] == "inicio" and tipos[-1] == "fim"
    assert set(tipos[2:-1]) == {"trecho"}
    assert ev[1][1] == {"fonte": "offline", "motivo": "GROQ_API_KEY não configurada",
                        "reiniciar": False}
    texto = "".join(d["texto"] for t, d in ev if t == "trecho")
    assert "Baldeação em Paraíso" in texto and "Baldeação em Sé" in texto
    assert "Total: 22 paradas." in texto
    assert "DFS: 38 estações visitadas" in texto


def test_narrar_tunel_obstruido(sem_chave):
    ev = narrar(origem="Luz", destino="República", bloqueadas=["Sé"])
    fatos = ev[0][1]
    assert fatos["encontrado"] is False and fatos["obstrucoes"] == ["Sé"]
    texto = "".join(d["texto"] for t, d in ev if t == "trecho")
    assert "Túnel obstruído: Sé" in texto
    assert "autorizada" not in texto


def test_narrar_destino_bloqueado(sem_chave):
    ev = narrar(origem="Luz", destino="Sé", bloqueadas=["Sé"], algoritmo="bfs")
    texto = "".join(d["texto"] for t, d in ev if t == "trecho")
    assert "destino, Sé, está bloqueada" in texto


def test_narrar_estacao_desconhecida():
    assert cliente.get("/api/narrar", params={"origem": "Luz", "destino": "X"}).status_code == 404


def test_narrar_com_llama(com_chave, monkeypatch):
    recebidos = {}

    async def falso_llama(fatos, chave):
        recebidos["fatos"], recebidos["chave"] = fatos, chave
        for pedaco in ["Rota ", "narrada."]:
            yield pedaco

    monkeypatch.setattr(main, "_trechos_llama", falso_llama)
    ev = narrar(origem="Luz", destino="Sé")
    assert ev[1] == ("inicio", {"fonte": "llama"})
    assert [d["texto"] for t, d in ev if t == "trecho"] == ["Rota ", "narrada."]
    assert ev[-1] == ("fim", {"fonte": "llama"})
    assert recebidos["chave"] == "chave-de-teste"
    assert recebidos["fatos"] == ev[0][1]  # o Llama só recebe os fatos do core


def _erro_groq():
    return APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))


def test_narrar_llama_fora_do_ar(com_chave, monkeypatch):
    async def falha(fatos, chave):
        raise _erro_groq()
        yield  # pragma: no cover

    monkeypatch.setattr(main, "_trechos_llama", falha)
    ev = narrar(origem="Luz", destino="Sé")
    assert ev[1] == ("inicio", {"fonte": "offline",
                                "motivo": "Llama indisponível (APIConnectionError)",
                                "reiniciar": False})
    assert ev[-1] == ("fim", {"fonte": "offline"})


def test_narrar_llama_cai_no_meio(com_chave, monkeypatch):
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


def test_narrar_llama_resposta_vazia(com_chave, monkeypatch):
    async def vazio(fatos, chave):
        return
        yield  # pragma: no cover

    monkeypatch.setattr(main, "_trechos_llama", vazio)
    ev = narrar(origem="Luz", destino="Sé")
    assert ev[1][1]["motivo"] == "resposta vazia do Llama"


def test_erro_inesperado_nao_e_mascarado(com_chave, monkeypatch):
    async def bug(fatos, chave):
        raise KeyError("bug")
        yield  # pragma: no cover

    monkeypatch.setattr(main, "_trechos_llama", bug)
    with pytest.raises(KeyError):
        cliente.get("/api/narrar", params={"origem": "Luz", "destino": "Sé"})
