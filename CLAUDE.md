# MetrôBot SP — "Subsolo SP"

Projeto da matéria (entrega via GitHub público: README com nomes de TODOS
os alunos no topo). Desafio MetrôBot SP 2.0: 3 linhas de metrô
(1-Azul, 2-Verde, 3-Vermelha), integrações Sé/Paraíso/Ana Rosa, BFS/DFS
com estações bloqueadas, lógica proposicional e de 1ª ordem (fatos +
regras R1–R5 + encadeamento para frente com justificativa), Llama como
intérprete e narrador.

## REGRA DE OURO
"A lanterna ilumina, o algoritmo decide."
O LLM (Llama) interpreta linguagem natural e narra — NUNCA decide a rota.
Quem decide é o algoritmo (BFS/DFS) e a lógica (R1–R5), em Python.

## PERGUNTAS OBRIGATÓRIAS ANTES DE CODAR
Faça UMA POR VEZ, aguardando resposta em cada uma. Nunca pule.

1. Nomes completos de TODOS os integrantes do grupo (para o topo do README).
2. Chave da API Groq (para o Llama): o usuário fornece, ou deixamos
   placeholder via variável de ambiente GROQ_API_KEY com fallback offline?
3. Confirmar a lista de estações e nomes conforme o PDF do desafio:
   conferir contra o grafo (Shopping Metrô Tucuruvi e outros "locais
   conhecidos" citados no enunciado).
4. Regras R1–R5 exatas: pedir o texto delas do PDF (não inventar).
5. Onde roda a demo no dia: local (recomendado) ou deploy? (Vercel/Render
   são opcionais; a demo local nunca depende de internet.)
6. O notebook original (.ipynb) entra no repo como prova R1–R7? (Sim,
   recomendado.)

## Arquitetura (não mudar sem pedir)
- core/        -> código avaliado: grafo.py (LINHAS, CORES, hubs, locais
                  conhecidos), busca.py (BFS/DFS com registro de trace),
                  logica.py (fatos, R1–R8), planejador.py (lógica+busca),
                  interprete.py (intérprete offline da aula),
                  testes (6 casos exigidos pelo desafio)
- main.py      -> FastAPI. Endpoints: /api/rota, /api/inferencia,
                  /api/narrar (SSE com fallback offline), /api/estacoes,
                  /api/locais, /api/interpretar (LLM extrai nomes; core valida),
                  /api/tabela-verdade.
                  Serve static/ como app single-page (sem build).
- static/      -> front SEM build: index.html + style.css + app.js
                  + mapa.svg (já existentes conforme design system)
- notebook/    -> README sobre o formato de entrega (notebook a confirmar com o professor)
- README.md    -> nomes dos alunos no topo (obrigatório)

## Contrato de trace (formato imutável)
O front NUNCA recalcula nada. O core/ gera o trace (JSON) e o front só
reproduz. Trace define:
- BFS: ordem de expansão por nível, fila (FIFO), nós visitados, pai map
- DFS: ordem de exploração, pilha (LIFO), backtracking, nós visitados
- Inferência: regra disparada + fato(s) que a justificaram
- Final: caminho reconstruído (fio de Ariadne) e métricas de esforço

## Design system (front — "Modo Clean", tema claro)
Decisão do aluno (substitui o tema escuro "Despachante do Subsolo" da v1):
interface clara e intuitiva para usuário comum. A identidade antiga só
sobrevive como um toque (monoespaçada nos rótulos pequenos e nos dados).

Paleta (static/style.css):
--fundo:#F7F5F0  --cartao:#FFFFFF  --borda:#E3DFD6  --borda-forte:#CFC9BC
--tinta:#1F2328  --tinta-media:#5A6068  --tinta-fraca:#8A9099
--l1:#0054A6  --l2:#009640  --l3:#EF3A46  (cores das linhas = destaque da UI)
--aviso:#B45309  --erro:#C0262F  + sombras suaves e raio 12px.
SEM scanlines, vinheta ou textura de papel.

Layout (2 colunas; 1 coluna abaixo de 980px):
- Esquerda: mapa grande (~60%) com tooltip (#dossie) na estação.
- Direita: 4 passos numerados — 1 Origem (#busca), 2 Destino
  (#busca-destino), 3 Opções (<details>, avançado: fechada, elevador,
  lotada, acessibilidade, pico, linha paralisada, frase em linguagem
  natural), 4 botão grande "Traçar rota" (#btn-despachar).
- Resultado: "Resumo da rota" (#corrida + selo #selo) e o passo a passo
  (#passos) montado a partir de diagnostico.trechos/baldeacoes.
- Narração: painel de conversa (#radio) com "Ouvir de novo"/"Parar" e a
  fonte (nuvem/offline) em #radio-fonte.

Estados visuais (obrigatórios):
- Estação: repouso branco / hover tooltip (nome+linhas+locais) / origem
  verde --l2 / destino azul --l1 / fechada cruz --l3 (not-allowed).
- Dois fluxos convergem: clicar no mapa OU buscar → mesmos halos.
- Rota: fio de Ariadne âmbar (#F59E0B) com halo branco e stroke-dashoffset.
- "Mostrar detalhes da busca" (#btn-auditoria, body.modo-auditoria) revela
  #avancado: trace em texto puro (fila/pilha/ordem), regras disparadas e
  tabela-verdade — prova da matéria com um clique.
- Termos de nicho (DESPACHO, RASTRO, RÁDIO, CENTRAL) só no texto puro do
  modo avançado, nunca na interface padrão.
- Escopo: SEM áudio, SEM partículas, SEM drag/zoom.
- static/mapa.svg é congelado: geometria, data-* e rótulos não mudam; as
  cores do mapa são ajustadas por CSS (#mapa-svg-host ... tem prioridade).

## Ordem de fases
Fase 1: core/ + testes rodando (pytest verde)
Fase 2: main.py FastAPI + endpoints respondendo JSON/SSE
Fase 3: static/ integrado (index.html + app.js consumindo /api)
Fase 4: README.md + validação ponta a ponta + instruções de execução

## Restrições
- Backend = FastAPI (exigência do professor). Front = single-page
  HTML+JS+SVG servido pelo FastAPI. PROIBIDO React/build/node_modules.
- PROIBIDO duplicar lógica de busca/lógica no JavaScript.
- Llama nunca decide rota; narração nunca inventa fatos (fallback
  offline se a API cair).
- Testes do core/ devem passar antes de qualquer mudança de contrato.
- Nunca subir .env (chave da Groq fica em variável de ambiente).

## Fonte oficial
- desafio.pdf (raiz, fora do git: direitos autorais). R1–R5 = "As 5 regras do
  MetrôBot" (Passo 4.4); R6 integração e R7 do grupo = Desafio, requisito R3.
  Requisitos do desafio são R1–R6 (Modelagem, Busca, Lógica, Llama,
  Interface, Testes). Nomes das estações: exatamente os de "Dados das linhas"
  (Japão-Liberdade, Patriarca-Vila Ré).
- Decisões do aluno: cores reais do Metrô (não as CORES do PDF); regras do
  grupo R7 (linha paralisada) e R8 (horário de pico); locais extras
  Conjunto Nacional, Shopping Pátio Paulista, Beco do Batman, Memorial da
  América Latina.

## Convenção de vizinhos (define os traces e os testes)
- Ordem = ordem do percurso de cada linha: L1 norte→sul (Tucuruvi→Jabaquara),
  L2 Vila Madalena→Vila Prudente, L3 oeste→leste (Palmeiras-Barra Funda→
  Corinthians-Itaquera).
- Hubs: vizinhos da L1 primeiro, depois os da outra linha, REMOVENDO repetidos
  (mantém a primeira ocorrência):
  Sé → [São Bento, Japão-Liberdade, Anhangabaú, Pedro II]
  Paraíso → [Vergueiro, Ana Rosa, Brigadeiro]
  Ana Rosa → [Paraíso, Vila Mariana, Chácara Klabin]
- Aresta Paraíso–Ana Rosa pertence às linhas 1 e 2 (trace registra ambas).
- 52 estações (3 hubs contados uma vez); 21 locais (≥3 por linha).

## Propriedade da rede (relatório e apresentação)
- As 3 linhas não formam ciclo: existe caminho ÚNICO entre duas estações.
  BFS e DFS chegam à mesma rota; a diferença é só o esforço (nós visitados,
  backtracks). É isso que a "corrida BFS × DFS" deve evidenciar.
- Bloquear uma estação desse caminho único torna o destino inalcançável
  ("túnel obstruído"). Casos 5 × 6 explicados no README.

## Lógica (core/logica.py)
- Fatos de base: estacao(e), pertence(e, "Linha X-Cor"), proximo_de(local, e).
  integracao e bloqueada NUNCA são digitadas (vêm de R6 e de R3/R7).
- Cenário: usuario_esta_em / usuario_esta_na_estacao, usuario_quer_ir /
  usuario_quer_ir_estacao, precisa_acessibilidade, fechada, elevador_em_
  manutencao, paralisada(l), horario_pico, lotada.
- Encadeamento: rodadas como no PDF (regras veem os fatos do início da
  rodada); estratos para a negação da R7 (estrato 1, depois da R6).
- R4 não bloqueia; R5 só para papel ∈ {origem, destino}; R8 só alerta.

## Formato do trace (core/busca.py — inalterado desde a Fase 1)
Comum (BFS e DFS): algoritmo, estrutura, origem, destino, bloqueadas,
passos[], ordem[], visitados[], pai{no: pai|null}, encontrado, motivo,
caminho[], caminho_arestas[{de, para, linhas[]}], metricas{}.
- BFS: + niveis{no: nivel}. passo = {n, acao: expandir|objetivo, no, nivel,
  descobertos[{no, nivel, linhas[]}], ignorados[{no, motivo:
  bloqueada|visitado}], fila[] (após o passo)}. metricas = nos_expandidos,
  max_fronteira, paradas, passos, nos_visitados.
- DFS (pilha = caminho corrente): passo = {n, acao: empilhar|avancar|
  objetivo|backtrack, no, de, linhas[] (avancar/objetivo), volta_para
  (backtrack), profundidade, ignorados[], pilha[] (após o passo)}.
  metricas = backtracks, max_fronteira, profundidade_max, paradas, passos,
  nos_visitados.
- motivo (quando encontrado=false): "origem bloqueada" | "destino bloqueado"
  | "sem caminho (bloqueios isolam o destino)"; paradas = null.
- Inferência (v2): regras[{id, nome, formula, descricao, estrato, do_grupo}],
  regras_disparadas[], inferencias[{n, iteracao (=rodada), regra, fato,
  justificativa[]}], fatos_derivados[], origem[], destino[], bloqueadas[],
  integracoes[], inacessiveis[], alertas[{papel, estacao}], alertas_lotacao[],
  total_fatos (+ fatos_iniciais se incluir_base). Fato = {predicado, args[], texto}.
- Planejador (v2): {origem, destino (deduzidos por R1/R2), cenario{origem
  {tipo,nome}, destino, acessibilidade, fechadas, manutencao, paralisadas
  (ids), horario_pico, lotadas}, bloqueadas, alertas, alertas_lotacao,
  regras_disparadas, inferencia, buscas{BFS, DFS}, comparacao{ALG:
  {encontrado, motivo, caminho, tempo_min, ...metricas}}, diagnostico
  {obstrucoes[], trechos[{linha, de, ate, paradas}], baldeacoes[{estacao,
  de_linha, para_linha}], tempo_min}}. TEMPO_POR_TRECHO = 2 min.

## Contrato da API (main.py)
- GET  /api/estacoes → {linhas[{id, nome, nome_logico, cor, estacoes[]}],
  hubs[] (deduzidos pela R6), estacoes[dossiê]}
- GET  /api/locais → {locais[{nome, estacao, linhas[]}]}
- GET  /api/tabela-verdade → {formula, legenda, linhas[{P, Q, R, resultado}]}
- POST /api/rota {origem, destino, fechadas[], manutencao[], acessibilidade,
  paralisadas[], horario_pico, lotadas[], algoritmo: bfs|dfs|ambos}
  → planejador. 404 = estação/local/linha desconhecida (ou local usado como
  estação em cenário); 422 = entrada inválida.
- POST /api/inferencia {mesmo cenário, origem?, destino?, incluir_base}
- POST /api/interpretar {mensagem (1–500)} → {fonte: llm|offline, offline,
  modelo, motivo, origem, destino, fechadas[], acessibilidade, extraido}.
  LLM em JSON mode (temperatura 0) extrai SÓ {origem, destino, fechadas,
  acessibilidade}; validar_nomes confere (sem aproximação). Nome fora da
  rede → 422 {erro, invalidos[], extraido}; JSON fora do formato → 502.
  Sem chave ou GroqError → interpretar_offline (PDF). Front rejeita o pedido
  se faltar origem ou destino (como no PDF) e nunca despacha sozinho.
- GET  /api/narrar?(mesmos parâmetros de /api/rota) (SSE). Eventos: fatos →
  inicio{fonte: llama|offline, modelo?, motivo?, reiniciar?} → trecho* → fim.
  Queda no meio: segundo "inicio" offline com reiniciar=true.
- LLM recebe SOMENTE o evento "fatos". Env: GROQ_API_KEY, GROQ_MODEL
  (padrão llama-3.3-70b-versatile). Só GroqError cai no offline. Clientes
  AsyncGroq sempre em "async with".
- Conta Groq do projeto sem Llama de conversa: validação real feita com
  GROQ_MODEL=openai/gpt-oss-120b (JSON mode OK). Código segue pronto p/ Llama.
- Regra do front: /api/rota, /api/inferencia e /api/narrar recebem OS MESMOS
  parâmetros; o evento "fatos" ecoa "cenario" para o front conferir.
- Front: stream encerrado sem "fim" = erro de narração (não esperar para sempre).
- Rodar: .venv\Scripts\python -m uvicorn main:app --reload

## Pendências
- Formato de entrega: o PDF descreve notebook com ipywidgets; confirmar com
  o professor se o notebook é obrigatório (ver notebook/README.md).
