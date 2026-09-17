"""/api/interpretar: o LLM (ou o plano B offline) só extrai nomes; o core/ valida."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from groq import APIConnectionError, AuthenticationError

import main

cliente = TestClient(main.app)


@pytest.fixture
def com_chave(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "chave-de-teste")


def llm_responde(monkeypatch, conteudo):
    recebido = {}

    async def falso(mensagem, chave):
        recebido["mensagem"], recebido["chave"] = mensagem, chave
        return conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False)

    monkeypatch.setattr(main, "_extrair_llama", falso)
    return recebido


def llm_falha(monkeypatch, erro):
    async def falso(mensagem, chave):
        raise erro

    monkeypatch.setattr(main, "_extrair_llama", falso)


def interpretar(mensagem):
    return cliente.post("/api/interpretar", json={"mensagem": mensagem})


def json_llm(origem=None, destino=None, fechadas=(), acessibilidade=False):
    return {"origem": origem, "destino": destino, "fechadas": list(fechadas),
            "acessibilidade": acessibilidade}


# ---------- frase válida (LLM) ----------

def test_frase_valida(com_chave, monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    recebido = llm_responde(monkeypatch, json_llm(
        "Catedral da Sé", "pinacoteca", ["Luz", " luz "], acessibilidade=True))
    r = interpretar("to na se, bora pra pinacoteca, tô de cadeira de rodas, a Luz fechou")
    assert r.status_code == 200
    assert r.json() == {
        "fonte": "llm",
        "offline": False,
        "modelo": "openai/gpt-oss-120b",
        "motivo": None,
        "origem": "Catedral da Sé",
        "destino": "Pinacoteca",
        "fechadas": ["Luz"],
        "acessibilidade": True,
        "extraido": {"origem": "Catedral da Sé", "destino": "pinacoteca",
                     "fechadas": ["Luz", "luz"], "acessibilidade": True},
    }
    assert recebido["chave"] == "chave-de-teste"


def test_frase_parcial(com_chave, monkeypatch):
    llm_responde(monkeypatch, json_llm(destino="Paraíso"))
    d = interpretar("quero chegar no Paraíso").json()
    assert (d["origem"], d["destino"], d["fechadas"]) == (None, "Paraíso", [])


def test_prompt_lista_52_estacoes_e_locais():
    prompt = main.prompt_interpretacao()
    assert "Japão-Liberdade" in prompt and "Patriarca-Vila Ré" in prompt
    assert "Neo Química Arena" in prompt and "Pinacoteca" in prompt
    assert "Atlântida" not in prompt and "Avenida Paulista" not in prompt


# ---------- nome inexistente ----------

def test_estacao_inexistente(com_chave, monkeypatch):
    llm_responde(monkeypatch, json_llm("Sé", "Avenida Paulista", ["Estação Fantasma"]))
    r = interpretar("Quero ir da Sé até a Avenida Paulista")
    assert r.status_code == 422
    assert r.json()["detail"] == {
        "erro": "nomes fora da rede",
        "invalidos": ["Avenida Paulista", "Estação Fantasma"],
        "extraido": json_llm("Sé", "Avenida Paulista", ["Estação Fantasma"]),
    }


def test_local_nao_pode_ser_fechada(com_chave, monkeypatch):
    llm_responde(monkeypatch, json_llm("Sé", "Luz", ["Pinacoteca"]))
    assert interpretar("da Sé à Luz sem a Pinacoteca").status_code == 422


@pytest.mark.parametrize("conteudo", [
    "não é json",
    {"origem": "Luz", "destino": "Sé", "fechadas": []},
    {**json_llm("Luz", "Sé"), "rota": ["Luz", "Sé"]},
    {**json_llm("Luz", "Sé"), "origem": 1},
    {**json_llm("Luz", "Sé"), "fechadas": "Brás"},
    {**json_llm("Luz", "Sé"), "acessibilidade": "sim"},
    ["Luz", "Sé"],
])
def test_resposta_fora_do_formato(com_chave, monkeypatch, conteudo):
    llm_responde(monkeypatch, conteudo)
    r = interpretar("da Luz até a Sé")
    assert r.status_code == 502
    assert "LLM" in r.json()["detail"] or "deve ser" in r.json()["detail"]


# ---------- modo offline (sem chave ou LLM fora do ar) ----------

def test_sem_chave_usa_interprete_offline(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = interpretar("Estou na Catedral da Sé e quero ir ao Terminal Rodoviário Jabaquara, uso cadeira de rodas")
    assert r.status_code == 200
    d = r.json()
    assert (d["fonte"], d["offline"], d["modelo"], d["motivo"]) == (
        "offline", True, None, "GROQ_API_KEY não configurada")
    assert (d["origem"], d["destino"], d["acessibilidade"]) == (
        "Catedral da Sé", "Terminal Rodoviário Jabaquara", True)


def test_offline_nao_inventa(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    d = interpretar("Quero ir da Sé até a Avenida Paulista").json()
    assert (d["origem"], d["destino"]) == ("Sé", None)


@pytest.mark.parametrize("erro, nome", [
    (APIConnectionError(request=httpx.Request("POST", "https://api.groq.com")), "APIConnectionError"),
    (AuthenticationError("chave inválida",
                         response=httpx.Response(401, request=httpx.Request("POST", "https://api.groq.com")),
                         body=None), "AuthenticationError"),
])
def test_llm_fora_do_ar_cai_no_offline(com_chave, monkeypatch, erro, nome):
    llm_falha(monkeypatch, erro)
    r = interpretar("do Mosteiro de São Bento para a São Judas")
    assert r.status_code == 200
    d = r.json()
    assert (d["fonte"], d["motivo"]) == ("offline", f"LLM indisponível ({nome})")
    assert (d["origem"], d["destino"]) == ("Mosteiro de São Bento", "São Judas")


def test_erro_inesperado_nao_e_mascarado(com_chave, monkeypatch):
    llm_falha(monkeypatch, KeyError("bug"))
    with pytest.raises(KeyError):
        interpretar("da Luz até a Sé")


@pytest.mark.parametrize("mensagem", ["", "x" * 501])
def test_mensagem_invalida(mensagem):
    assert interpretar(mensagem).status_code == 422
