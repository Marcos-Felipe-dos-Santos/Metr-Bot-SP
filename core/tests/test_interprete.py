"""Intérprete offline com os pedidos da Célula 18 do desafio.pdf."""
import pytest

from core.interprete import interpretar_offline, normalizar


def test_normalizar():
    assert normalizar("São Bento") == "sao bento"


def test_catedral_da_se_ate_terminal_jabaquara():
    r = interpretar_offline("Estou na Catedral da Sé e quero ir ao Terminal Rodoviário Jabaquara")
    assert r == {"origem": "Catedral da Sé", "destino": "Terminal Rodoviário Jabaquara",
                 "fechadas": [], "acessibilidade": False}


def test_se_sem_acento_nao_e_reconhecido():
    # Limite do modo offline apontado pelo PDF: "se" sem acento (nome curto).
    r = interpretar_offline("to na se, bora pra pinacoteca, tô de cadeira de rodas")
    assert r["origem"] == "Pinacoteca" and r["destino"] is None
    assert r["acessibilidade"] is True


def test_mosteiro_ate_sao_judas():
    r = interpretar_offline("Preciso sair do Mosteiro de São Bento e chegar na São Judas")
    assert (r["origem"], r["destino"]) == ("Mosteiro de São Bento", "São Judas")


def test_avenida_paulista_nao_e_inventada():
    r = interpretar_offline("Quero ir da Sé até a Avenida Paulista")
    assert (r["origem"], r["destino"]) == ("Sé", None)


@pytest.mark.parametrize("texto, esperado", [
    ("da japao-liberdade ate patriarca-vila re", ("Japão-Liberdade", "Patriarca-Vila Ré")),
    ("Do MASP para a Neo Química Arena", ("MASP", "Neo Química Arena")),
    ("nenhum lugar conhecido", (None, None)),
])
def test_nomes_do_desafio(texto, esperado):
    r = interpretar_offline(texto)
    assert (r["origem"], r["destino"]) == esperado
