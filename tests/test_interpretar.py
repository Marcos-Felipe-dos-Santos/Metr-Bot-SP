"""/api/interpretar: o Llama só extrai nomes; o core/ valida; nada é inventado."""
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


def llama_responde(monkeypatch, conteudo):
    recebido = {}

    async def falso(mensagem, chave):
        recebido["mensagem"], recebido["chave"] = mensagem, chave
        return conteudo if isinstance(conteudo, str) else json.dumps(conteudo, ensure_ascii=False)

    monkeypatch.setattr(main, "_extrair_llama", falso)
    return recebido


def llama_falha(monkeypatch, erro):
    async def falso(mensagem, chave):
        raise erro

    monkeypatch.setattr(main, "_extrair_llama", falso)


def interpretar(mensagem):
    return cliente.post("/api/interpretar", json={"mensagem": mensagem})


# ---------- frase válida ----------

def test_frase_valida(com_chave, monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    recebido = llama_responde(monkeypatch, {
        "origem": "Shopping Metrô Tucuruvi", "destino": "se", "bloqueadas": ["Luz", " luz "],
    })
    r = interpretar("do shopping tucuruvi até a sé sem passar pela Luz")
    assert r.status_code == 200
    assert r.json() == {
        "offline": False,
        "motivo": None,
        "modelo": "openai/gpt-oss-120b",
        "origem": "Tucuruvi",
        "destino": "Sé",
        "bloqueadas": ["Luz"],
        "extraido": {"origem": "Shopping Metrô Tucuruvi", "destino": "se",
                     "bloqueadas": ["Luz", "luz"]},
    }
    assert recebido == {"mensagem": "do shopping tucuruvi até a sé sem passar pela Luz",
                        "chave": "chave-de-teste"}


def test_frase_parcial(com_chave, monkeypatch):
    llama_responde(monkeypatch, {"origem": None, "destino": "Paraíso", "bloqueadas": []})
    d = interpretar("quero chegar no Paraíso").json()
    assert (d["origem"], d["destino"], d["bloqueadas"]) == (None, "Paraíso", [])


def test_prompt_lista_so_nomes_da_rede():
    prompt = main.prompt_interpretacao()
    assert "Shopping Metrô Tucuruvi" in prompt and "Corinthians-Itaquera" in prompt
    assert "Atlântida" not in prompt


# ---------- estação inexistente ----------

def test_estacao_inexistente(com_chave, monkeypatch):
    llama_responde(monkeypatch, {"origem": "Luz", "destino": "Atlântida",
                                 "bloqueadas": ["Estação Fantasma"]})
    r = interpretar("da Luz até Atlântida sem a Estação Fantasma")
    assert r.status_code == 422
    assert r.json()["detail"] == {
        "erro": "nomes fora da rede",
        "invalidos": ["Atlântida", "Estação Fantasma"],
        "extraido": {"origem": "Luz", "destino": "Atlântida", "bloqueadas": ["Estação Fantasma"]},
    }


@pytest.mark.parametrize("conteudo", [
    "não é json",
    {"origem": "Luz", "destino": "Sé"},
    {"origem": "Luz", "destino": "Sé", "bloqueadas": [], "rota": ["Luz", "Sé"]},
    {"origem": 1, "destino": "Sé", "bloqueadas": []},
    {"origem": "Luz", "destino": "Sé", "bloqueadas": "Brás"},
    ["Luz", "Sé"],
])
def test_resposta_fora_do_formato(com_chave, monkeypatch, conteudo):
    llama_responde(monkeypatch, conteudo)
    r = interpretar("da Luz até a Sé")
    assert r.status_code == 502
    assert "Llama" in r.json()["detail"] or "deve ser" in r.json()["detail"]


# ---------- Llama fora do ar / sem chave ----------

VAZIO = {"origem": None, "destino": None, "bloqueadas": [], "extraido": None}


def test_sem_chave(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = interpretar("da Luz até a Sé")
    assert r.status_code == 200
    assert r.json() == {"offline": True, "motivo": "GROQ_API_KEY não configurada", **VAZIO}


@pytest.mark.parametrize("erro, nome", [
    (APIConnectionError(request=httpx.Request("POST", "https://api.groq.com")), "APIConnectionError"),
    (AuthenticationError("chave inválida",
                         response=httpx.Response(401, request=httpx.Request("POST", "https://api.groq.com")),
                         body=None), "AuthenticationError"),
])
def test_llama_fora_do_ar(com_chave, monkeypatch, erro, nome):
    llama_falha(monkeypatch, erro)
    r = interpretar("da Luz até a Sé")
    assert r.status_code == 200
    assert r.json() == {"offline": True, "motivo": f"Llama indisponível ({nome})", **VAZIO}


def test_erro_inesperado_nao_e_mascarado(com_chave, monkeypatch):
    llama_falha(monkeypatch, KeyError("bug"))
    with pytest.raises(KeyError):
        interpretar("da Luz até a Sé")


@pytest.mark.parametrize("mensagem", ["", "x" * 501])
def test_mensagem_invalida(mensagem):
    assert interpretar(mensagem).status_code == 422
