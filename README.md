# MetrôBot SP — "Subsolo SP"

**Aluno:** Marcos Felipe dos Santos — RA 2403903

> README provisório (Fase 1). Versão completa com instruções de execução na Fase 4.

## Convenção de vizinhos

A ordem dos vizinhos define os traces de BFS/DFS e os casos de teste:

- Cada linha segue a ordem do seu percurso: **L1** norte→sul (Tucuruvi→Jabaquara),
  **L2** Vila Madalena→Vila Prudente, **L3** oeste→leste
  (Palmeiras-Barra Funda→Corinthians-Itaquera).
- Nos hubs, vêm primeiro os vizinhos da L1 e depois os da outra linha,
  **removendo repetidos** (fica a primeira ocorrência):
  - Sé → [São Bento, Liberdade, Anhangabaú, Pedro II]
  - Paraíso → [Vergueiro, Ana Rosa, Brigadeiro]
  - Ana Rosa → [Paraíso, Vila Mariana, Chácara Klabin]
