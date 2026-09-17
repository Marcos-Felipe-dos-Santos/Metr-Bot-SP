"""Motor lógico do MetrôBot SP (desafio.pdf, Parte 4 + Desafio R3).

Fatos de primeira ordem + regras R1–R8 + encadeamento para frente com
justificativa de cada disparo.

- R1–R5: "As 5 regras do MetrôBot" (Passo 4.4), como no PDF.
- R6: integração, obrigatória no desafio (deduzida, nunca digitada).
- R7 e R8: regras criadas pelo grupo (linha paralisada e horário de pico).

R7 usa negação (¬integracao). Para a negação ser segura, as regras são
estratificadas: o estrato 0 roda até o ponto fixo antes do estrato 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Callable, Iterable

from core import grafo

PAPEIS = ("origem", "destino")


@dataclass(frozen=True)
class Fato:
    predicado: str
    args: tuple[str, ...] = ()

    def __str__(self) -> str:
        return f"{self.predicado}({', '.join(self.args)})" if self.args else self.predicado

    def para_json(self) -> dict:
        return {"predicado": self.predicado, "args": list(self.args), "texto": str(self)}


def nao(fato: Fato) -> Fato:
    """Registro de negação por falha usado só em justificativas (¬p)."""
    return Fato(f"¬{fato.predicado}", fato.args)


class BaseFatos:
    """Base com ordem de inserção estável (trace determinístico) e busca O(1)."""

    def __init__(self, fatos: Iterable[Fato] = ()):
        self._ordem: list[Fato] = []
        self._conjunto: set[Fato] = set()
        for f in fatos:
            self.adicionar(f)

    def adicionar(self, fato: Fato) -> bool:
        if fato in self._conjunto:
            return False
        self._conjunto.add(fato)
        self._ordem.append(fato)
        return True

    def consultar(self, predicado: str) -> list[Fato]:
        return [f for f in self._ordem if f.predicado == predicado]

    def __contains__(self, fato: object) -> bool:
        return fato in self._conjunto

    def __iter__(self):
        return iter(list(self._ordem))

    def __len__(self) -> int:
        return len(self._ordem)


Disparos = list[tuple[Fato, list[Fato]]]


# ------------------------------------------------------------------ regras

def r1_origem(base: BaseFatos) -> Disparos:
    saida = []
    for quer in base.consultar("usuario_esta_em"):
        for prox in base.consultar("proximo_de"):
            if prox.args[0] == quer.args[0]:
                saida.append((Fato("origem", (prox.args[1],)), [quer, prox]))
    for esta in base.consultar("usuario_esta_na_estacao"):
        saida.append((Fato("origem", esta.args), [esta]))
    return saida


def r2_destino(base: BaseFatos) -> Disparos:
    saida = []
    for quer in base.consultar("usuario_quer_ir"):
        for prox in base.consultar("proximo_de"):
            if prox.args[0] == quer.args[0]:
                saida.append((Fato("destino", (prox.args[1],)), [quer, prox]))
    for quer in base.consultar("usuario_quer_ir_estacao"):
        saida.append((Fato("destino", quer.args), [quer]))
    return saida


def r3_bloqueio(base: BaseFatos) -> Disparos:
    return [(Fato("bloqueada", f.args), [f]) for f in base.consultar("fechada")]


def r4_acessibilidade(base: BaseFatos) -> Disparos:
    precisa = Fato("precisa_acessibilidade")
    if precisa not in base:
        return []
    return [(Fato("inacessivel", f.args), [precisa, f])
            for f in base.consultar("elevador_em_manutencao")]


def r5_alerta(base: BaseFatos) -> Disparos:
    saida = []
    for papel in PAPEIS:
        for f in base.consultar(papel):
            inacessivel = Fato("inacessivel", f.args)
            if inacessivel in base:
                saida.append((Fato("alerta", (papel, f.args[0])), [f, inacessivel]))
    return saida


def r6_integracao(base: BaseFatos) -> Disparos:
    saida = []
    pertence = base.consultar("pertence")
    for i, p1 in enumerate(pertence):
        for p2 in pertence[i + 1:]:
            if p1.args[0] == p2.args[0] and p1.args[1] != p2.args[1]:
                saida.append((Fato("integracao", (p1.args[0],)), [p1, p2]))
    return saida


def r7_linha_paralisada(base: BaseFatos) -> Disparos:
    saida = []
    for par in base.consultar("paralisada"):
        for pert in base.consultar("pertence"):
            integracao = Fato("integracao", (pert.args[0],))
            if pert.args[1] == par.args[0] and integracao not in base:
                saida.append((Fato("bloqueada", (pert.args[0],)), [par, pert, nao(integracao)]))
    return saida


def r8_horario_pico(base: BaseFatos) -> Disparos:
    pico = Fato("horario_pico")
    if pico not in base:
        return []
    return [(Fato("alerta_lotacao", f.args), [pico, f]) for f in base.consultar("lotada")]


@dataclass
class Regra:
    id: str
    nome: str
    formula: str
    descricao: str
    aplicar: Callable[[BaseFatos], Disparos]
    estrato: int = 0
    do_grupo: bool = False

    def para_json(self) -> dict:
        return {"id": self.id, "nome": self.nome, "formula": self.formula,
                "descricao": self.descricao, "estrato": self.estrato,
                "do_grupo": self.do_grupo}


REGRAS: list[Regra] = [
    Regra("R1", "origem",
          "∀l ∀e (usuario_esta_em(l) ∧ proximo_de(l,e) → origem(e))",
          "Se estou num local perto da estação e, então e é minha origem",
          r1_origem),
    Regra("R2", "destino",
          "∀l ∀e (usuario_quer_ir(l) ∧ proximo_de(l,e) → destino(e))",
          "Se quero ir a um local perto de e, então e é meu destino",
          r2_destino),
    Regra("R3", "bloqueio",
          "∀e (fechada(e) → bloqueada(e))",
          "Estação fechada não pode estar na rota",
          r3_bloqueio),
    Regra("R4", "acessibilidade",
          "∀e (precisa_acessibilidade ∧ elevador_em_manutencao(e) → inacessivel(e))",
          "Com elevador parado, a estação fica inacessível para embarque/desembarque",
          r4_acessibilidade),
    Regra("R5", "alerta",
          "∀p ∀e (papel(p,e) ∧ inacessivel(e) → alerta(p,e))",
          "Se minha origem ou destino é inacessível, emite alerta",
          r5_alerta),
    Regra("R6", "integração",
          "∀e ∀l1 ∀l2 (pertence(e,l1) ∧ pertence(e,l2) ∧ l1 ≠ l2 → integracao(e))",
          "Estação que pertence a duas linhas diferentes é integração",
          r6_integracao),
    Regra("R7", "linha paralisada",
          "∀e ∀l (paralisada(l) ∧ pertence(e,l) ∧ ¬integracao(e) → bloqueada(e))",
          "Linha paralisada bloqueia suas estações, exceto as integrações "
          "(que seguem atendidas pela outra linha)",
          r7_linha_paralisada, estrato=1, do_grupo=True),
    Regra("R8", "horário de pico",
          "∀e (horario_pico ∧ lotada(e) → alerta_lotacao(e))",
          "Em horário de pico, estação lotada gera alerta de lotação (não bloqueia)",
          r8_horario_pico, do_grupo=True),
]


# ------------------------------------------------------------------ fatos

def fatos_base() -> list[Fato]:
    """Fatos fixos do mundo: estações, a que linhas pertencem, locais próximos."""
    fatos = [Fato("estacao", (e,)) for e in grafo.ESTACOES]
    for lid, dados in grafo.LINHAS.items():
        fatos += [Fato("pertence", (e, grafo.nome_linha(lid))) for e in dados["estacoes"]]
    fatos += [Fato("proximo_de", (local, e)) for local, e in grafo.LOCAIS_CONHECIDOS.items()]
    return fatos


@dataclass
class Cenario:
    """Pedido do passageiro + situação simulada da rede (nomes já canônicos)."""
    origem: tuple[str, str] | None = None    # (tipo, nome); tipo = estacao|local
    destino: tuple[str, str] | None = None
    acessibilidade: bool = False
    fechadas: list[str] = field(default_factory=list)
    manutencao: list[str] = field(default_factory=list)
    paralisadas: list[str] = field(default_factory=list)   # ids de linha
    horario_pico: bool = False
    lotadas: list[str] = field(default_factory=list)

    def fatos(self) -> list[Fato]:
        fatos = []
        if self.origem:
            tipo, nome = self.origem
            fatos.append(Fato("usuario_esta_em" if tipo == "local" else "usuario_esta_na_estacao", (nome,)))
        if self.destino:
            tipo, nome = self.destino
            fatos.append(Fato("usuario_quer_ir" if tipo == "local" else "usuario_quer_ir_estacao", (nome,)))
        if self.acessibilidade:
            fatos.append(Fato("precisa_acessibilidade"))
        fatos += [Fato("fechada", (e,)) for e in self.fechadas]
        fatos += [Fato("elevador_em_manutencao", (e,)) for e in self.manutencao]
        fatos += [Fato("paralisada", (grafo.nome_linha(l),)) for l in self.paralisadas]
        if self.horario_pico:
            fatos.append(Fato("horario_pico"))
        fatos += [Fato("lotada", (e,)) for e in self.lotadas]
        return fatos

    def para_json(self) -> dict:
        def ponto(p):
            return None if p is None else {"tipo": p[0], "nome": p[1]}
        return {
            "origem": ponto(self.origem), "destino": ponto(self.destino),
            "acessibilidade": self.acessibilidade, "fechadas": self.fechadas,
            "manutencao": self.manutencao, "paralisadas": self.paralisadas,
            "horario_pico": self.horario_pico, "lotadas": self.lotadas,
        }


# ------------------------------------------------------------------ motor

@dataclass
class ResultadoInferencia:
    fatos_iniciais: list[Fato]
    fatos_finais: list[Fato]
    inferencias: list[dict] = field(default_factory=list)
    regras: list[Regra] = field(default_factory=list)

    def consulta(self, predicado: str) -> list[Fato]:
        return [f for f in self.fatos_finais if f.predicado == predicado]

    def valores(self, predicado: str) -> list[str]:
        return [f.args[0] for f in self.consulta(predicado)]

    @property
    def regras_disparadas(self) -> list[str]:
        return sorted({i["regra"] for i in self.inferencias}, key=lambda r: int(r[1:]))

    def para_json(self, incluir_base: bool = False) -> dict:
        dados = {
            "regras": [r.para_json() for r in self.regras],
            "regras_disparadas": self.regras_disparadas,
            "inferencias": self.inferencias,
            "fatos_derivados": [f.para_json() for f in self.fatos_finais[len(self.fatos_iniciais):]],
            "origem": self.valores("origem"),
            "destino": self.valores("destino"),
            "bloqueadas": self.valores("bloqueada"),
            "integracoes": self.valores("integracao"),
            "inacessiveis": self.valores("inacessivel"),
            "alertas": [{"papel": f.args[0], "estacao": f.args[1]} for f in self.consulta("alerta")],
            "alertas_lotacao": self.valores("alerta_lotacao"),
            "total_fatos": len(self.fatos_finais),
        }
        if incluir_base:
            dados["fatos_iniciais"] = [f.para_json() for f in self.fatos_iniciais]
        return dados


def encadear_para_frente(fatos: Iterable[Fato],
                         regras: list[Regra] | None = None) -> ResultadoInferencia:
    """Aplica as regras em rodadas até o ponto fixo, estrato por estrato.

    Como no PDF, todas as regras de uma rodada enxergam os fatos do início
    da rodada; os fatos novos só entram na base ao fim dela. Cada inferência
    registra a rodada, a regra e os fatos que a justificam.
    """
    regras = REGRAS if regras is None else regras
    base = BaseFatos(fatos)
    iniciais = list(base)
    inferencias: list[dict] = []
    rodada = 0
    for estrato in sorted({r.estrato for r in regras}):
        do_estrato = [r for r in regras if r.estrato == estrato]
        mudou = True
        while mudou:
            mudou = False
            rodada += 1
            inicio_da_rodada = BaseFatos(base)
            for regra in do_estrato:
                for novo, justificativa in regra.aplicar(inicio_da_rodada):
                    if not base.adicionar(novo):
                        continue
                    mudou = True
                    inferencias.append({
                        "n": len(inferencias) + 1,
                        "iteracao": rodada,
                        "regra": regra.id,
                        "fato": novo.para_json(),
                        "justificativa": [f.para_json() for f in justificativa],
                    })
    return ResultadoInferencia(iniciais, list(base), inferencias, list(regras))


def inferir(cenario: Cenario | None = None,
            regras: list[Regra] | None = None) -> ResultadoInferencia:
    cenario = cenario or Cenario()
    return encadear_para_frente(fatos_base() + cenario.fatos(), regras)


# ------------------------------------------------------------------ lógica proposicional

FORMULA_EMBARQUE = "pode_embarcar ≡ P ∧ (¬Q ∨ R)"
LEGENDA_EMBARQUE = {
    "P": "a estação está aberta",
    "Q": "o passageiro precisa de acessibilidade",
    "R": "o elevador da estação está funcionando",
}


def pode_embarcar(P: bool, Q: bool, R: bool) -> bool:
    """P: estação aberta | Q: precisa de acessibilidade | R: elevador funcionando."""
    return P and ((not Q) or R)


def tabela_verdade() -> dict:
    """Tabela-verdade gerada por código (desafio R3), na ordem do PDF."""
    return {
        "formula": FORMULA_EMBARQUE,
        "legenda": LEGENDA_EMBARQUE,
        "linhas": [{"P": P, "Q": Q, "R": R, "resultado": pode_embarcar(P, Q, R)}
                   for P, Q, R in product([True, False], repeat=3)],
    }
