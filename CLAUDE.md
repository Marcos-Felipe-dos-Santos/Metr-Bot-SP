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
                  logica.py (fatos, R1–R5), planejador.py (lógica+busca),
                  testes (6 casos exigidos pelo desafio)
- main.py      -> FastAPI. Endpoints: /api/rota, /api/inferencia,
                  /api/narrar (SSE com fallback offline), /api/estacoes,
                  /api/locais, /api/interpretar (Llama extrai nomes; core valida).
                  Serve static/ como app single-page (sem build).
- static/      -> front SEM build: index.html + style.css + app.js
                  + mapa.svg (já existentes conforme design system)
- notebook/    -> .ipynb original mantido como prova dos requisitos R1–R7
- README.md    -> nomes dos alunos no topo (obrigatório)

## Contrato de trace (formato imutável)
O front NUNCA recalcula nada. O core/ gera o trace (JSON) e o front só
reproduz. Trace define:
- BFS: ordem de expansão por nível, fila (FIFO), nós visitados, pai map
- DFS: ordem de exploração, pilha (LIFO), backtracking, nós visitados
- Inferência: regra disparada + fato(s) que a justificaram
- Final: caminho reconstruído (fio de Ariadne) e métricas de esforço

## Design system (front — identidade "Despachante do Subsolo")
Paleta (tokens fixos, não mudar):
--carvao:#0B0A08  --tunel:#1A1815  --tunel-2:#262219  --ferrugem:#8A6B4A
--osso:#D8CFBC    --papel:#C9B896  --papel-claro:#E4D8B8  --fantasma:#6E675A
--fosfo:#7CFF3F   --fosfo-dim:#3E7A24  (HUD/BFS/contadores — só estados curtos)
--ambar:#FFB000   --ambar-dim:#8A5E14  (DFS/avisos/destino)
--alerta:#E62020  (bloqueada)  --radio:#F2C14E  (narrador/selos/lore)

Tipografia: VT323 (HUD/selos), IBM Plex Mono (terminal/dados), Special
Elite (narrador/lore). SEMPRE com fallback monospace. Cores oficiais das
linhas (#0054A6, #009640, #EF3A46) vivem apenas dentro do mapa-carta
(papel envelhecido), não no chrome da UI. Texturas 100% CSS.

Estados visuais (obrigatórios):
- Estação: repouso papel / hover dossiê (nome+linha+facção) / origem halo
  --fosfo / destino halo --ambar / bloqueada cruz --alerta (not-allowed)
- Dois fluxos convergem: clicar no mapa OU busca de locais → mesmos halos
- Rota: trilho de luz com stroke-dashoffset (fio de Ariadne) + selo
  "AUTORIZADO PELA CENTRAL" (--radio, glow âmbar, rotação 2–3deg)
- Modo Auditoria: botão que derruba scanlines/vinheta/ruído e mostra o
  trace em texto puro (fila/pilha/ordem) — prova da matéria com um clique.
- Escopo v1: paleta + design APENAS. SEM áudio, SEM partículas,
  SEM drag/zoom.

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

## Convenção de vizinhos (define os traces e os testes)
- Ordem = ordem do percurso de cada linha: L1 norte→sul (Tucuruvi→Jabaquara),
  L2 Vila Madalena→Vila Prudente, L3 oeste→leste (Palmeiras-Barra Funda→
  Corinthians-Itaquera).
- Hubs: vizinhos da L1 primeiro, depois os da outra linha, REMOVENDO repetidos
  (mantém a primeira ocorrência):
  Sé → [São Bento, Liberdade, Anhangabaú, Pedro II]
  Paraíso → [Vergueiro, Ana Rosa, Brigadeiro]
  Ana Rosa → [Paraíso, Vila Mariana, Chácara Klabin]
- Aresta Paraíso–Ana Rosa pertence às linhas 1 e 2 (trace registra ambas).
- 52 estações (3 hubs contados uma vez). Locais conhecidos: por ora só
  "Shopping Metrô Tucuruvi" → Tucuruvi (aguardando texto oficial).

## Propriedade da rede (relatório e apresentação)
- As 3 linhas não formam ciclo: existe caminho ÚNICO entre duas estações.
  BFS e DFS chegam à mesma rota; a diferença é só o esforço (nós visitados,
  backtracks). É isso que a "corrida BFS × DFS" deve evidenciar.
- Bloquear uma estação desse caminho único torna o destino inalcançável
  ("túnel obstruído"): coberto por teste e pela narração.
- Os 11 testes pulados ("aguardando texto oficial") permanecem até o grupo
  fornecer R1–R5, R1–R7 e os 6 casos.

## Formato do trace (v1 — core/busca.py e core/logica.py)
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
- Inferência: regras[{id, texto_oficial, pendente}], regras_pendentes[],
  inferencias[{n, iteracao, regra, fato, justificativa[]}], fatos_derivados[],
  bloqueadas[], total_fatos. Fato = {predicado, args[], texto}.
- Planejador: {origem, destino, bloqueadas, inferencia, buscas{BFS, DFS},
  comparacao{ALG: {encontrado, motivo, caminho, ...metricas}},
  diagnostico{obstrucoes[], trechos[{linha, de, ate, paradas}],
  baldeacoes[{estacao, de_linha, para_linha}]}}.
  obstrucoes = bloqueadas que estão no caminho único sem bloqueio.

## Contrato da API (Fase 2 — main.py)
- GET  /api/estacoes → {linhas[{id, nome, cor, estacoes[]}], hubs[], estacoes[dossiê]}
- GET  /api/locais → {pendente, aviso, locais[{nome, estacao}]}
- POST /api/rota {origem, destino, bloqueadas[], algoritmo: bfs|dfs|ambos}
  → saída do planejador. 404 = estação/local desconhecido; 422 = algoritmo inválido.
- POST /api/inferencia {bloqueadas[], incluir_rede} → inferência (JSON acima).
- GET  /api/narrar?origem&destino&bloqueadas=A&bloqueadas=B&algoritmo (SSE,
  compatível com EventSource). Eventos em ordem: fatos → inicio{fonte:
  llama|offline, motivo?, reiniciar?} → trecho{texto}* → fim{fonte}.
  Se o Llama cair no meio, vem um segundo "inicio" com fonte offline e
  reiniciar=true: o front descarta o texto parcial.
- POST /api/interpretar {mensagem (1–500)} → {offline, motivo, modelo?, origem,
  destino, bloqueadas[], extraido}. O Llama (JSON mode, temperatura 0) só
  EXTRAI nomes {origem, destino, bloqueadas}; core.planejador.validar_nomes
  confere cada um contra a rede, sem aproximação. Nome fora da rede → 422
  {erro, invalidos[], extraido}. JSON fora do formato → 502. Sem chave ou
  GroqError → 200 com offline=true e campos vazios (front usa clique/busca).
  Não calcula rota: o front aplica os nomes e o usuário DESPACHA (/api/rota).
- "inicio" com fonte llama traz também "modelo" (GROQ_MODEL em uso).
- Conta Groq do projeto sem Llama de conversa: validação real feita com
  GROQ_MODEL=openai/gpt-oss-120b (JSON mode OK). Código segue pronto p/ Llama.
- Llama recebe SOMENTE o evento "fatos". Env: GROQ_API_KEY, GROQ_MODEL
  (padrão llama-3.3-70b-versatile). Só erros GroqError caem no offline.
- Regra do front: /api/rota e /api/narrar recebem OS MESMOS parâmetros
  (origem, destino, bloqueadas, algoritmo); o evento "fatos" ecoa origem,
  destino, bloqueadas e esforco{ALG} para o front conferir.
- Front: stream encerrado sem "fim" = erro de narração (não esperar para sempre).
- "/" serve static/ (index.html pendente da Fase 3).
- Rodar: .venv\Scripts\python -m uvicorn main:app --reload

## Pendências (NÃO inventar)
- Texto literal de R1–R5, requisitos R1–R7 e os 6 casos oficiais: aguardando
  PDF/notebook. Regras ficam sem corpo; testes oficiais ficam como skip
  "aguardando texto oficial".
