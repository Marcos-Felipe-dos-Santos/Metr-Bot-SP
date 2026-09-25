# MetrôBot SP 2.0 — Intérprete e Narrador de Rotas do Metrô de São Paulo

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Testes](https://img.shields.io/badge/testes-146%20passando-brightgreen)
![Offline](https://img.shields.io/badge/funciona-sem%20internet-blue)

Aplicação web que planeja rotas nas linhas 1-Azul, 2-Verde e 3-Vermelha do
Metrô de São Paulo: um LLM interpreta o pedido em linguagem natural e narra o
resultado, enquanto a rota é decidida em Python por busca em grafo (BFS e DFS)
e por uma base lógica de primeira ordem com encadeamento para frente.

**Autores:**

- Marcos Felipe dos Santos — RA 2403903
- Leandro Silva Ferreira — RA 2397191

Disciplina de Inteligência Artificial e Machine Learning — Prof. Hercules
Ramos. Desafio MetrôBot SP 2.0.

O LLM não decide rota: ele só extrai nomes do pedido e narra os fatos já
calculados. A origem, o destino e os bloqueios saem das regras R1–R8; o
caminho sai do BFS/DFS. A interface apenas reproduz os traces gerados pelo
backend, sem recalcular busca ou lógica em JavaScript.

**Sumário:** [Como rodar](#como-rodar) ·
[Estrutura](#estrutura-do-projeto) ·
[Funcionalidades](#funcionalidades) ·
[Regras R1–R8](#regras-de-inferência-r1r8) ·
[6 casos obrigatórios](#os-6-casos-obrigatórios) ·
[Rede e locais](#rede-e-locais-conhecidos) ·
[Tabela-verdade](#tabela-verdade-de-pode_embarcar) ·
[Modelo LLM](#transparência-sobre-o-modelo)

---

## Como rodar

Requisitos: Python 3.13 (testado com 3.13.14) e um navegador moderno.

Crie e ative o ambiente virtual:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux e macOS
```

Instale as dependências e suba o servidor:

```bash
pip install -r requirements.txt
uvicorn main:app
```

Abra **http://localhost:8000**.

### Chave da API (opcional)

Para usar o LLM, copie o arquivo de exemplo e preencha sua chave da Groq:

```bash
copy .env.example .env          # Windows
cp .env.example .env            # Linux e macOS
```

```
GROQ_API_KEY=sua_chave_groq
GROQ_MODEL=openai/gpt-oss-120b
```

O `.env` está no `.gitignore` e não vai para o repositório.

Sem chave, com chave inválida, sem internet ou com o limite de uso esgotado, a
aplicação continua funcionando: a interpretação usa o analisador offline em
`core/interprete.py` e a narração usa um texto determinístico montado apenas
com os fatos do trace. **A demonstração não depende de internet.**

### Testes

Com o ambiente virtual ativado:

```bash
python -m pytest
```

Resultado esperado: **146 testes passando, nenhum pulado**. Os 6 casos
obrigatórios estão em `core/tests/test_planejador_e_casos.py`.

---

## Estrutura do projeto

```
core/                        # código avaliado, sem dependência de web
├── grafo.py                 # linhas, estações, hubs, adjacência, locais
├── busca.py                 # BFS e DFS com registro do trace
├── logica.py                # fatos, regras R1–R8, encadeamento para frente
├── planejador.py            # une lógica e busca, diagnostica a rota
├── interprete.py            # intérprete offline (sem LLM)
└── tests/                   # grafo, busca, lógica, intérprete, 6 casos
main.py                      # FastAPI: endpoints /api/* e arquivos estáticos
static/                      # front sem build
├── index.html
├── style.css
├── app.js                   # só reproduz traces; nenhuma busca em JS
└── mapa.svg                 # mapa da rede
tests/                       # testes dos endpoints e do intérprete
notebook/                    # notebook do desafio (ver notebook/README.md)
.env.example                 # modelo das variáveis de ambiente
requirements.txt             # versões fixadas
```

O notebook em `notebook/` reaproveita o pacote `core/`, sem duplicar código:
a lógica avaliada existe em um único lugar e é a mesma usada pela aplicação
web e pelos testes.

---

## Funcionalidades

### Busca de rota com BFS e DFS

Os dois algoritmos rodam sobre o mesmo grafo e registram um trace completo:
ordem de expansão, fila (FIFO) ou pilha (LIFO) a cada passo, nós visitados,
mapa de pais, backtracking, caminho final e métricas de esforço.

Como as três linhas não formam ciclo, existe um caminho único entre duas
estações: BFS e DFS chegam sempre à mesma rota e o que muda é o esforço. De
Luz a República, por exemplo, o BFS visita 15 estações e o DFS visita 37, com
32 backtracks; os dois fazem 4 paradas.

O tempo estimado usa 2 minutos por trecho, valor didático adotado no desafio.

### Regras de inferência R1–R8

O motor aplica as regras em rodadas até o ponto fixo. Cada rodada enxerga os
fatos existentes no início dela, e todo fato derivado guarda a regra e os
fatos que o justificaram. A R7 usa negação e roda em um estrato posterior,
depois que a R6 já deduziu as integrações.

| Regra | Fórmula | Predicados usados | Fato gerado |
|---|---|---|---|
| R1 origem | ∀l ∀e (usuario_esta_em(l) ∧ proximo_de(l,e) → origem(e)) | usuario_esta_em, proximo_de | origem(e) |
| R2 destino | ∀l ∀e (usuario_quer_ir(l) ∧ proximo_de(l,e) → destino(e)) | usuario_quer_ir, proximo_de | destino(e) |
| R3 bloqueio | ∀e (fechada(e) → bloqueada(e)) | fechada | bloqueada(e) |
| R4 acessibilidade | ∀e (precisa_acessibilidade ∧ elevador_em_manutencao(e) → inacessivel(e)) | precisa_acessibilidade, elevador_em_manutencao | inacessivel(e) |
| R5 alerta | ∀p ∀e (papel(p,e) ∧ inacessivel(e) → alerta(p,e)) | origem, destino, inacessivel | alerta(papel, e) |
| R6 integração | ∀e ∀l1 ∀l2 (pertence(e,l1) ∧ pertence(e,l2) ∧ l1 ≠ l2 → integracao(e)) | pertence | integracao(e) |
| R7 linha paralisada | ∀e ∀l (paralisada(l) ∧ pertence(e,l) ∧ ¬integracao(e) → bloqueada(e)) | paralisada, pertence, ¬integracao | bloqueada(e) |
| R8 horário de pico | ∀e (horario_pico ∧ lotada(e) → alerta_lotacao(e)) | horario_pico, lotada | alerta_lotacao(e) |

R1–R6 vêm do enunciado. R7 (linha paralisada) e R8 (horário de pico) são as
regras próprias exigidas pelo desafio. A R4 não bloqueia a estação, apenas a
marca como inacessível; a R5 só emite alerta para origem ou destino; a R8
alerta sem bloquear. A R7 poupa as integrações, porque elas continuam
atendidas pela outra linha.

### Interpretação de linguagem natural

`POST /api/interpretar` recebe uma frase como "estou na Catedral da Sé e quero
ir à Pinacoteca, uso cadeira de rodas". O LLM responde em modo JSON e só pode
devolver `{origem, destino, fechadas, acessibilidade}`. Cada nome é conferido
contra a rede por `core.planejador.validar_nomes`, sem correspondência
aproximada:

- nome fora da rede, como "Avenida Paulista": **422** com a lista de inválidos;
- JSON fora do formato combinado: **502**;
- sem chave ou com erro da Groq: cai no intérprete offline.

Sem origem e destino válidos, o pedido é rejeitado inteiro. O intérprete
apenas preenche os campos; quem traça a rota é o algoritmo, depois da
confirmação do passageiro.

### Narração com LLM e modo offline

`GET /api/narrar` transmite por SSE na ordem `fatos → inicio → trecho* → fim`.
O LLM recebe somente o evento `fatos`, isto é, o recorte já calculado pelo
core: trechos, baldeações, tempo estimado, alertas e obstruções. Se a API do
LLM cair no meio da transmissão, o servidor envia um novo `inicio` com
`reiniciar: true`, a interface descarta o texto parcial e o modo offline
assume. Uma transmissão encerrada sem o evento `fim`, ou parada por mais de
30 segundos, é tratada como erro pela interface.

### Demais endpoints

| Método e rota | Função |
|---|---|
| `GET /api/estacoes` | linhas, estações e hubs deduzidos pela R6 |
| `GET /api/locais` | locais conhecidos e a estação de cada um |
| `GET /api/tabela-verdade` | tabela-verdade de `pode_embarcar` |
| `POST /api/rota` | inferência e busca; devolve traces, comparação e diagnóstico |
| `POST /api/inferencia` | só a base lógica, com todas as justificativas |

A documentação interativa gerada pelo FastAPI fica em
**http://localhost:8000/docs** com o servidor rodando.

### Modo Auditoria

O botão "Mostrar detalhes da busca" derruba as texturas da interface e exibe,
em texto puro: as regras aplicadas com fórmula e justificativa de cada
disparo, o registro passo a passo da busca, a tabela-verdade e o trace
completo, com fila, pilha, ordem, visitados, mapa de pais e métricas.

---

## Os 6 casos obrigatórios

| # | Origem | Destino | Restrição | Resultado esperado |
|---|---|---|---|---|
| 1 | Tucuruvi | Corinthians-Itaquera | nenhuma | 22 paradas, baldeação na Sé |
| 2 | Vila Madalena | Jabaquara | nenhuma | 14 paradas, baldeação na Ana Rosa |
| 3 | Palmeiras-Barra Funda | Vila Prudente | nenhuma | 16 paradas, baldeações na Sé e na Ana Rosa |
| 4 | Tucuruvi | Brás | Sé fechada | sem rota |
| 5 | Vila Madalena | Jabaquara | Paraíso fechada | sem rota |
| 6 | Vila Prudente | Jabaquara | Paraíso fechada | 13 paradas, baldeação na Ana Rosa |

Os seis rodam como testes automatizados em
`core/tests/test_planejador_e_casos.py`.

### Por que o caso 5 não tem rota e o caso 6 tem

As duas viagens vão para Jabaquara com a mesma estação fechada, mas só uma
precisa atravessar Paraíso.

- **Caso 5 — Vila Madalena → Jabaquara.** Vila Madalena está no trecho oeste
  da Linha 2. Esse trecho (Vila Madalena … Brigadeiro) se liga ao resto da
  rede apenas por **Paraíso**. Com Paraíso fechada, o trecho fica isolado: não
  existe outro trilho para sair dele, e o destino se torna inalcançável.
- **Caso 6 — Vila Prudente → Jabaquara.** Vila Prudente está no trecho leste
  da mesma Linha 2, que alcança a Linha 1 por **Ana Rosa**
  (Chácara Klabin → Ana Rosa), sem passar por Paraíso. São 6 paradas na
  Linha 2 e 7 na Linha 1, com baldeação na Ana Rosa: 13 paradas no total.

---

## Rede e locais conhecidos

São 52 estações, com os nomes exatamente como no enunciado, incluindo
**Japão-Liberdade** e **Patriarca-Vila Ré**. As integrações Sé (linhas 1 e 3),
Paraíso (1 e 2) e Ana Rosa (1 e 2) contam uma vez cada.

A ordem dos vizinhos define os traces: cada linha é percorrida na ordem do
trajeto (L1 de Tucuruvi a Jabaquara, L2 de Vila Madalena a Vila Prudente, L3
de Palmeiras-Barra Funda a Corinthians-Itaquera) e, nos hubs, vêm primeiro os
vizinhos da Linha 1 e depois os da outra linha, sem repetidos.

O dicionário `proximo_de` tem 21 locais, com pelo menos 3 em cada linha.

| Local | Estação | Linha |
|---|---|---|
| Shopping Metrô Tucuruvi | Tucuruvi | 1-Azul |
| Terminal Rodoviário Tietê | Portuguesa-Tietê | 1-Azul |
| Museu de Arte Sacra | Tiradentes | 1-Azul |
| Pinacoteca | Luz | 1-Azul |
| Museu da Língua Portuguesa | Luz | 1-Azul |
| Mosteiro de São Bento | São Bento | 1-Azul |
| Rua 25 de Março | São Bento | 1-Azul |
| Catedral da Sé | Sé | 1-Azul e 3-Vermelha |
| Bairro da Liberdade | Japão-Liberdade | 1-Azul |
| Centro Cultural São Paulo | Vergueiro | 1-Azul |
| Shopping Metrô Santa Cruz | Santa Cruz | 1-Azul |
| Universidade São Judas | São Judas | 1-Azul |
| Terminal Rodoviário Jabaquara | Jabaquara | 1-Azul |
| MASP | Trianon-Masp | 2-Verde |
| Hospital das Clínicas | Clínicas | 2-Verde |
| Conjunto Nacional | Consolação | 2-Verde |
| Shopping Pátio Paulista | Brigadeiro | 2-Verde |
| Beco do Batman | Vila Madalena | 2-Verde |
| Theatro Municipal | Anhangabaú | 3-Vermelha |
| Neo Química Arena | Corinthians-Itaquera | 3-Vermelha |
| Memorial da América Latina | Palmeiras-Barra Funda | 3-Vermelha |

O mapa usa as cores reais do Metrô (`#0054A6`, `#009640` e `#EF3A46`), em vez
das cores do dicionário do enunciado.

---

## Tabela-verdade de `pode_embarcar`

Fórmula: **pode_embarcar ≡ P ∧ (¬Q ∨ R)**

- **P:** a estação está aberta
- **Q:** o passageiro precisa de acessibilidade
- **R:** o elevador da estação está funcionando

| P | Q | R | pode_embarcar |
|:---:|:---:|:---:|:---:|
| V | V | V | V |
| V | V | F | F |
| V | F | V | V |
| V | F | F | V |
| F | V | V | F |
| F | V | F | F |
| F | F | V | F |
| F | F | F | F |

A tabela é gerada por código em `core/logica.py`, servida por
`GET /api/tabela-verdade` e exibida no Modo Auditoria.

---

## Cenários simulados

Além das estações fechadas, a interface permite simular elevador em
manutenção, necessidade de acessibilidade, horário de pico, estação lotada e
linha inteira paralisada. Esses cenários alimentam as regras R4, R5, R7 e R8.

---

## Transparência sobre o modelo

O código foi escrito para o Llama e o padrão continua sendo
`llama-3.3-70b-versatile`. A conta Groq usada no desenvolvimento não tem
nenhum modelo Llama de conversa disponível: os únicos listados são os
classificadores `llama-prompt-guard-2`. Por isso a validação com modelo real
foi feita com `GROQ_MODEL=openai/gpt-oss-120b`, que aceita o modo JSON exigido
pelo intérprete. O modelo em uso aparece na interface e no campo `modelo` das
respostas da API. Com uma chave que tenha acesso ao Llama, basta alterar a
variável `GROQ_MODEL`.