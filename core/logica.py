"""Motor lógico: fatos (1ª ordem) + regras R1–R5 + encadeamento para frente.

PENDENTE: o texto oficial de R1–R5 ainda não foi fornecido. As regras
existem apenas como interface (sem corpo) e não disparam. Não inventar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from core import grafo

PREDICADOS = ("Estacao", "Linha", "Integracao", "Conectada", "Bloqueada")


@dataclass(frozen=True)
class Fato:
    predicado: str
    args: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.predicado}({', '.join(self.args)})"

    def para_json(self) -> dict:
        return {"predicado": self.predicado, "args": list(self.args), "texto": str(self)}


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

    def __contains__(self, fato: object) -> bool:
        return fato in self._conjunto

    def __iter__(self):
        return iter(list(self._ordem))

    def __len__(self) -> int:
        return len(self._ordem)


# Uma regra recebe a base de fatos e devolve [(fato_novo, [fatos_justificativa])].
Aplicacao = Callable[[BaseFatos], list[tuple[Fato, list[Fato]]]]


@dataclass
class Regra:
    id: str
    texto_oficial: str | None = None
    aplicar: Aplicacao | None = None

    @property
    def pendente(self) -> bool:
        return self.aplicar is None

    def para_json(self) -> dict:
        return {"id": self.id, "texto_oficial": self.texto_oficial, "pendente": self.pendente}


REGRAS: list[Regra] = [Regra(id=f"R{i}") for i in range(1, 6)]


def fatos_da_rede(bloqueadas: Iterable[str] = ()) -> list[Fato]:
    fatos: list[Fato] = []
    for est in grafo.ESTACOES:
        fatos.append(Fato("Estacao", (est,)))
        for lid in grafo.LINHAS_DA_ESTACAO[est]:
            fatos.append(Fato("Linha", (est, lid)))
        if est in grafo.HUBS:
            fatos.append(Fato("Integracao", (est,)))
    for est in grafo.ESTACOES:
        for viz in grafo.vizinhos(est):
            fatos.append(Fato("Conectada", (est, viz)))
    for est in bloqueadas:
        if est not in grafo.ADJACENCIA:
            raise grafo.EstacaoDesconhecida(f"Estação desconhecida: {est!r}")
        fatos.append(Fato("Bloqueada", (est,)))
    return fatos


@dataclass
class ResultadoInferencia:
    fatos_iniciais: list[Fato]
    fatos_finais: list[Fato]
    inferencias: list[dict] = field(default_factory=list)
    regras: list[Regra] = field(default_factory=list)

    def consulta(self, predicado: str) -> list[Fato]:
        return [f for f in self.fatos_finais if f.predicado == predicado]

    def para_json(self, incluir_rede: bool = False) -> dict:
        dados = {
            "regras": [r.para_json() for r in self.regras],
            "regras_pendentes": [r.id for r in self.regras if r.pendente],
            "inferencias": self.inferencias,
            "fatos_derivados": [
                f.para_json() for f in self.fatos_finais[len(self.fatos_iniciais):]
            ],
            "bloqueadas": [f.args[0] for f in self.consulta("Bloqueada")],
            "total_fatos": len(self.fatos_finais),
        }
        if incluir_rede:
            dados["fatos_iniciais"] = [f.para_json() for f in self.fatos_iniciais]
        return dados


def encadear_para_frente(fatos: Iterable[Fato],
                         regras: list[Regra] | None = None) -> ResultadoInferencia:
    """Aplica as regras até o ponto fixo, registrando regra + justificativa."""
    regras = REGRAS if regras is None else regras
    base = BaseFatos(fatos)
    iniciais = list(base)
    inferencias: list[dict] = []
    iteracao = 0
    mudou = True
    while mudou:
        mudou = False
        iteracao += 1
        for regra in regras:
            if regra.pendente:
                continue
            for novo, justificativa in regra.aplicar(base):
                if not base.adicionar(novo):
                    continue
                mudou = True
                inferencias.append({
                    "n": len(inferencias) + 1,
                    "iteracao": iteracao,
                    "regra": regra.id,
                    "fato": novo.para_json(),
                    "justificativa": [f.para_json() for f in justificativa],
                })
    return ResultadoInferencia(iniciais, list(base), inferencias, list(regras))


def inferir(bloqueadas: Iterable[str] = (),
            regras: list[Regra] | None = None) -> ResultadoInferencia:
    return encadear_para_frente(fatos_da_rede(bloqueadas), regras)
