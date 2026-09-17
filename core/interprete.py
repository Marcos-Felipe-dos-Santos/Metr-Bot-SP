"""Intérprete offline (plano B sem LLM), portado do desafio.pdf (Célula 17).

Procura nomes conhecidos (52 estações + locais) no texto, na ordem em que
aparecem: o primeiro vira origem, o segundo destino. Nomes longos são
procurados primeiro; sem acento, só nomes com mais de 4 letras (como no PDF,
"se" sem acento não é reconhecido).
"""

from __future__ import annotations

import re
import unicodedata

from core import grafo

PALAVRAS_ACESSIBILIDADE = ["cadeira de rodas", "acessibilidade", "mobilidade",
                           "muleta", "carrinho de bebe", "elevador"]


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos: 'São Bento' → 'sao bento'."""
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def interpretar_offline(texto: str) -> dict:
    texto_min = texto.lower()
    texto_sem = normalizar(texto)  # mesmo tamanho, só sem acentos
    candidatos = list(grafo.ESTACOES) + list(grafo.LOCAIS_CONHECIDOS)
    candidatos.sort(key=len, reverse=True)  # nomes longos primeiro
    ocupado = [False] * len(texto_min)
    encontrados: list[tuple[int, str]] = []
    for nome in candidatos:
        buscas = [(texto_min, nome.lower())]
        if len(nome) > 4 and len(texto_sem) == len(texto_min):
            buscas.append((texto_sem, normalizar(nome)))
        for base, padrao in buscas:
            for m in re.finditer(r"(?<!\w)" + re.escape(padrao) + r"(?!\w)", base):
                if not any(ocupado[m.start():m.end()]):
                    encontrados.append((m.start(), nome))
                    for i in range(m.start(), m.end()):
                        ocupado[i] = True
    encontrados.sort()
    return {
        "origem": encontrados[0][1] if len(encontrados) > 0 else None,
        "destino": encontrados[1][1] if len(encontrados) > 1 else None,
        "fechadas": [],
        "acessibilidade": any(p in texto_sem for p in PALAVRAS_ACESSIBILIDADE),
    }
