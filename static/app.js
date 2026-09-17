/* MetrôBot SP — Despachante do Subsolo (front v1)
 *
 * Regra de ouro: este arquivo NÃO calcula rota nem inferência.
 * Ele só reproduz os traces vindos de /api (core/ em Python).
 */
"use strict";

const NARRACAO_TIMEOUT_MS = 30000;
const RAIO_ESTACAO = 5;
const RAIO_HUB = 6.5;

const estado = {
  modo: "origem",
  origem: null,
  destino: null,
  bloqueadas: [],
  rede: null,          // /api/estacoes
  locais: [],          // /api/locais
  noSvg: new Map(),    // nome -> <g.estacao>
  execucao: 0,         // id da reprodução atual (cancela a anterior)
  pular: false,
  plano: null,
  radio: null,         // EventSource ativo
};

const $ = (sel) => document.querySelector(sel);
const SVG_NS = "http://www.w3.org/2000/svg";

// ------------------------------------------------------------ utilidades

function normalizar(txt) {
  return txt.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/-/g, " ").replace(/\s+/g, " ").trim();
}

function el(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto !== undefined) e.textContent = texto;
  return e;
}

function log(texto, tipo = "") {
  const box = $("#log");
  box.appendChild(el("p", `linha-log ${tipo}`.trim(), texto));
  while (box.childElementCount > 200) box.firstChild.remove();
  box.scrollTop = box.scrollHeight;
}

function hud({ visitados, passo, total, paradas } = {}) {
  const pad = (n, w) => (n === undefined || n === null ? "-".repeat(w) : String(n).padStart(w, "0"));
  const passoTxt = total ? `${pad(passo, 3)}/${pad(total, 3)}` : pad(passo, 3);
  $("#hud-contador").textContent =
    `VISIT ${pad(visitados, 2)} · PASSO ${passoTxt} · PARADAS ${pad(paradas, 2)}`;
}

function esperar(ms) {
  if (estado.pular) return Promise.resolve();
  const ritmo = Number($("#ritmo").value) || 1;
  return new Promise((ok) => setTimeout(ok, ms * ritmo));
}

class Cancelado extends Error {}

function conferir(execucao) {
  if (execucao !== estado.execucao) throw new Cancelado();
}

async function api(caminho, corpo) {
  const opcoes = corpo === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  };
  const resp = await fetch(caminho, opcoes);
  const dados = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detalhe = typeof dados.detail === "string" ? dados.detail : JSON.stringify(dados.detail);
    throw new Error(`${resp.status} em ${caminho}: ${detalhe}`);
  }
  return dados;
}

// ------------------------------------------------------------ mapa

async function carregarMapa() {
  const resp = await fetch("/mapa.svg", { cache: "no-cache" });
  if (!resp.ok) throw new Error(`mapa.svg indisponível (${resp.status})`);
  $("#mapa-svg-host").innerHTML = await resp.text();
  const svg = $("#mapa-svg-host svg");

  // Camadas de reprodução (só visual, criadas em memória — o arquivo não muda).
  const rota = svg.querySelector(".rota");
  const camada = document.createElementNS(SVG_NS, "g");
  camada.setAttribute("class", "camada-trace");
  const explorador = document.createElementNS(SVG_NS, "circle");
  explorador.setAttribute("class", "explorador");
  explorador.setAttribute("r", "9");
  explorador.setAttribute("opacity", "0");
  camada.appendChild(explorador);
  svg.insertBefore(camada, rota);

  for (const g of svg.querySelectorAll(".estacao")) {
    const bolha = g.querySelector(".bolha");
    if (!bolha.hasAttribute("r")) {
      bolha.setAttribute("r", g.dataset.hub === "true" ? RAIO_HUB : RAIO_ESTACAO);
    }
    const cx = Number(bolha.getAttribute("cx"));
    const cy = Number(bolha.getAttribute("cy"));
    const cruz = document.createElementNS(SVG_NS, "path");
    cruz.setAttribute("class", "cruz");
    cruz.setAttribute("d", `M${cx - 6} ${cy - 6} L${cx + 6} ${cy + 6} M${cx + 6} ${cy - 6} L${cx - 6} ${cy + 6}`);
    g.appendChild(cruz);
    g.setAttribute("tabindex", "0");
    g.setAttribute("role", "button");
    g.setAttribute("aria-label", g.dataset.nome);
    estado.noSvg.set(g.dataset.nome, g);
  }
  return svg;
}

function posicao(nome) {
  const g = estado.noSvg.get(nome);
  if (!g) return null;
  const b = g.querySelector(".bolha");
  return { x: Number(b.getAttribute("cx")), y: Number(b.getAttribute("cy")) };
}

/** Confere SVG × backend. Divergência: vale o backend, só registramos. */
function conferirMapa() {
  const doBack = new Map(estado.rede.estacoes.map((e) => [e.nome, e]));
  const divergencias = [];
  for (const [nome, g] of estado.noSvg) {
    const back = doBack.get(nome);
    if (!back) {
      divergencias.push(`SVG tem "${nome}", backend não (estação ignorada no mapa)`);
      g.classList.add("desconhecida");
      continue;
    }
    const linhas = back.linhas.map((l) => l.id);
    if (!linhas.includes(g.dataset.linha)) {
      divergencias.push(`"${nome}": SVG diz linha ${g.dataset.linha}, backend diz ${linhas.join("/")}`);
    }
    if ((g.dataset.hub === "true") !== back.hub) {
      divergencias.push(`"${nome}": hub no SVG=${g.dataset.hub === "true"}, backend=${back.hub}`);
    }
  }
  for (const nome of doBack.keys()) {
    if (!estado.noSvg.has(nome)) {
      divergencias.push(`backend tem "${nome}", SVG não (só disponível pela busca)`);
    }
  }
  if (divergencias.length) {
    console.warn("[MetrôBot] divergências SVG × /api/estacoes:", divergencias);
    divergencias.forEach((d) => log(`mapa: ${d}`, "erro"));
  } else {
    log(`mapa conferido: ${estado.noSvg.size} estações batem com o backend`, "trace");
  }
}

function limparReproducao() {
  for (const g of estado.noSvg.values()) {
    g.classList.remove("onda", "fronteira", "explorada", "recuada", "no-caminho");
  }
  const svg = $("#mapa-svg-host svg");
  if (!svg) return;
  const rota = svg.querySelector(".rota");
  rota.setAttribute("d", "");
  rota.setAttribute("opacity", "0");
  rota.classList.remove("desenhando", "negada");
  rota.style.strokeDasharray = "";
  rota.style.strokeDashoffset = "";
  svg.querySelector(".explorador").setAttribute("opacity", "0");
  const selo = $("#selo");
  selo.hidden = true;
  selo.classList.remove("negado");
}

// ------------------------------------------------------------ seleção (dois fluxos, um só destino)

function definirModo(modo) {
  estado.modo = modo;
  for (const b of document.querySelectorAll(".modo")) {
    b.setAttribute("aria-pressed", String(b.dataset.modo === modo));
  }
}

/** Único ponto de entrada: clique no mapa e busca chamam esta função. */
function escolher(nome) {
  if (!estado.rede.estacoes.some((e) => e.nome === nome)) {
    log(`"${nome}" não existe no backend`, "erro");
    return;
  }
  if (estado.modo === "bloquear") {
    if (nome === estado.origem || nome === estado.destino) {
      log(`${nome} é origem/destino: bloqueio registrado mesmo assim (o core decide)`, "erro");
    }
    const i = estado.bloqueadas.indexOf(nome);
    if (i >= 0) estado.bloqueadas.splice(i, 1);
    else estado.bloqueadas.push(nome);
  } else if (estado.bloqueadas.includes(nome)) {
    log(`${nome} está bloqueada — desbloqueie antes (modo BLOQUEAR)`, "erro");
    return;
  } else if (estado.modo === "origem") {
    estado.origem = nome;
    definirModo("destino");
  } else {
    estado.destino = nome;
  }
  atualizarSelecao();
}

function atualizarSelecao() {
  for (const [nome, g] of estado.noSvg) {
    g.classList.toggle("origem", nome === estado.origem);
    g.classList.toggle("destino", nome === estado.destino);
    g.classList.toggle("bloqueada", estado.bloqueadas.includes(nome));
  }
  $("#sel-origem").textContent = estado.origem || "—";
  $("#sel-destino").textContent = estado.destino || "—";
  $("#sel-bloqueadas").textContent = estado.bloqueadas.join(", ") || "nenhuma";
  $("#btn-despachar").disabled = !(estado.origem && estado.destino);
}

function mostrarDossie(g) {
  const info = estado.rede.estacoes.find((e) => e.nome === g.dataset.nome);
  const box = $("#dossie");
  box.replaceChildren();
  box.appendChild(el("strong", "", g.dataset.nome));
  if (info) {
    const faccao = info.linhas.map((l) => `Linha ${l.nome}`).join(" + ");
    box.appendChild(el("span", "", `facção: ${faccao}`));
    box.appendChild(el("br"));
    if (info.hub) box.appendChild(el("span", "", "integração (hub)"));
  } else {
    box.appendChild(el("span", "", "fora da base do backend"));
  }
  if (estado.bloqueadas.includes(g.dataset.nome)) {
    box.appendChild(el("br"));
    box.appendChild(el("span", "dossie-alerta", "BLOQUEADA"));
  }
  const mapa = $("#mapa").getBoundingClientRect();
  const r = g.querySelector(".bolha").getBoundingClientRect();
  box.style.left = `${r.right - mapa.left + 8}px`;
  box.style.top = `${r.top - mapa.top - 8}px`;
  box.style.display = "block";
}

function ligarMapa(svg) {
  svg.addEventListener("click", (ev) => {
    const g = ev.target.closest(".estacao");
    if (g && !g.classList.contains("desconhecida")) escolher(g.dataset.nome);
  });
  svg.addEventListener("keydown", (ev) => {
    const g = ev.target.closest(".estacao");
    if (g && (ev.key === "Enter" || ev.key === " ")) {
      ev.preventDefault();
      escolher(g.dataset.nome);
    }
  });
  const sobre = (ev) => {
    const g = ev.target.closest(".estacao");
    if (g) mostrarDossie(g);
  };
  svg.addEventListener("mouseover", sobre);
  svg.addEventListener("focusin", sobre);
  const sair = () => { $("#dossie").style.display = "none"; };
  svg.addEventListener("mouseleave", sair);
  svg.addEventListener("focusout", sair);
}

// Busca de locais: só filtra texto para o dropdown. Quem resolve é o backend.
function opcoesBusca() {
  const estacoes = estado.rede.estacoes.map((e) => ({
    rotulo: e.nome, estacao: e.nome,
    detalhe: e.linhas.map((l) => l.nome).join(" + "),
  }));
  const locais = estado.locais.map((l) => ({
    rotulo: l.nome, estacao: l.estacao, detalhe: `local → ${l.estacao}`,
  }));
  return [...locais, ...estacoes];
}

function ligarBusca() {
  const input = $("#busca");
  const drop = $("#dropdown");
  let itens = [];
  let ativo = -1;

  const fechar = () => {
    drop.hidden = true;
    input.setAttribute("aria-expanded", "false");
    ativo = -1;
  };
  const marcar = () => {
    [...drop.children].forEach((c, i) => c.classList.toggle("ativo", i === ativo));
  };
  const aplicar = (item) => {
    escolher(item.estacao);
    input.value = "";
    fechar();
  };

  input.addEventListener("input", () => {
    const termo = normalizar(input.value);
    drop.replaceChildren();
    if (!termo) return fechar();
    itens = opcoesBusca().filter((o) => normalizar(o.rotulo).includes(termo)).slice(0, 12);
    if (!itens.length) {
      drop.appendChild(el("div", "dropdown-item vazio", "sem sinal para esse nome"));
    }
    itens.forEach((item) => {
      const d = el("div", "dropdown-item");
      d.setAttribute("role", "option");
      d.appendChild(el("span", "", item.rotulo));
      d.appendChild(el("small", "dropdown-detalhe", ` ${item.detalhe}`));
      d.addEventListener("mousedown", (ev) => { ev.preventDefault(); aplicar(item); });
      drop.appendChild(d);
    });
    ativo = itens.length ? 0 : -1;
    marcar();
    drop.hidden = false;
    input.setAttribute("aria-expanded", "true");
  });
  input.addEventListener("keydown", (ev) => {
    if (drop.hidden || !itens.length) return;
    if (ev.key === "ArrowDown") { ativo = (ativo + 1) % itens.length; marcar(); ev.preventDefault(); }
    else if (ev.key === "ArrowUp") { ativo = (ativo - 1 + itens.length) % itens.length; marcar(); ev.preventDefault(); }
    else if (ev.key === "Enter" && ativo >= 0) { aplicar(itens[ativo]); ev.preventDefault(); }
    else if (ev.key === "Escape") fechar();
  });
  input.addEventListener("blur", fechar);
}

// Linguagem natural: o Llama só extrai nomes, o backend valida, nós só aplicamos.
function ligarInterpretacao() {
  const form = $("#form-interpretar");
  const status = $("#interpretar-status");
  const botao = $("#btn-interpretar");
  const avisar = (texto, tipo) => {
    status.textContent = texto;
    status.className = `linha-log interpretar-status ${tipo}`;
  };

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const mensagem = $("#mensagem").value.trim();
    if (!mensagem) return;
    botao.disabled = true;
    avisar("Central ouvindo…", "");
    try {
      const resp = await fetch("/api/interpretar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mensagem }),
      });
      const dados = await resp.json().catch(() => ({}));
      if (resp.status === 422 && dados.detail?.invalidos) {
        avisar(`Fora da rede: ${dados.detail.invalidos.join(", ")}. Nada foi alterado.`, "erro");
        log(`interpretar: nomes fora da rede ${listar(dados.detail.invalidos)}`, "erro");
        return;
      }
      if (!resp.ok) {
        const detalhe = typeof dados.detail === "string" ? dados.detail : `HTTP ${resp.status}`;
        avisar(`Central não entendeu: ${detalhe}`, "erro");
        log(`interpretar: ${detalhe}`, "erro");
        return;
      }
      if (dados.offline) {
        avisar(`Intérprete offline (${dados.motivo}). Escolha pelo mapa ou pela busca.`, "erro");
        $("#busca").focus();
        return;
      }
      if (dados.origem) estado.origem = dados.origem;
      if (dados.destino) estado.destino = dados.destino;
      estado.bloqueadas = [...dados.bloqueadas];
      definirModo(estado.destino ? "bloquear" : "destino");
      atualizarSelecao();
      const partes = [
        dados.origem && `origem ${dados.origem}`,
        dados.destino && `destino ${dados.destino}`,
        `bloqueadas ${listar(dados.bloqueadas)}`,
      ].filter(Boolean);
      avisar(`Entendido: ${partes.join(" · ")}. Confira e DESPACHE.`, "trace");
      log(`interpretar (Llama): ${JSON.stringify(dados.extraido)} → ${partes.join(" · ")}`, "trace");
    } catch (erro) {
      avisar(`Sem contato com a Central: ${erro.message}`, "erro");
    } finally {
      botao.disabled = false;
    }
  });
}

// ------------------------------------------------------------ reprodução dos traces

function listar(nos) {
  return `[${nos.join(", ")}]`;
}

async function reproduzirBFS(trace, execucao) {
  log(`BFS · ${trace.estrutura} · ${trace.origem} → ${trace.destino}`, "trace");
  const porNivel = new Map();
  for (const p of trace.passos) {
    if (!porNivel.has(p.nivel)) porNivel.set(p.nivel, []);
    porNivel.get(p.nivel).push(p);
  }
  let visitados = trace.passos.length ? 1 : 0;
  for (const [nivel, passos] of porNivel) {
    conferir(execucao);
    for (const p of passos) {
      const g = estado.noSvg.get(p.no);
      if (g) { g.classList.remove("fronteira"); g.classList.add("onda"); }
      for (const d of p.descobertos) estado.noSvg.get(d.no)?.classList.add("fronteira");
      visitados += p.descobertos.length;
      const ign = p.ignorados.length
        ? ` · ignorados ${p.ignorados.map((i) => `${i.no}(${i.motivo})`).join(", ")}` : "";
      log(`#${p.n} N${nivel} ${p.acao} ${p.no} · fila ${listar(p.fila)}${ign}`,
        p.acao === "objetivo" ? "radio" : "trace");
      hud({ visitados, passo: p.n, total: trace.passos.length });
    }
    await esperar(420);
  }
}

async function reproduzirDFS(trace, execucao) {
  log(`DFS · ${trace.estrutura} · ${trace.origem} → ${trace.destino}`, "trace");
  const explorador = $("#mapa-svg-host .explorador");
  const mover = (nome) => {
    const pos = posicao(nome);
    if (!pos) return;
    explorador.setAttribute("cx", pos.x);
    explorador.setAttribute("cy", pos.y);
    explorador.setAttribute("opacity", "1");
  };
  let visitados = 0;
  for (const p of trace.passos) {
    conferir(execucao);
    const g = estado.noSvg.get(p.no);
    if (p.acao === "backtrack") {
      g?.classList.add("recuada");
      if (p.volta_para) mover(p.volta_para);
      log(`#${p.n} backtrack ${p.no} → ${p.volta_para ?? "(pilha vazia)"} · pilha ${listar(p.pilha)}`, "trace");
    } else {
      visitados += 1;
      g?.classList.add("explorada");
      mover(p.no);
      const de = p.de ? `${p.de} → ` : "";
      log(`#${p.n} ${p.acao} ${de}${p.no} · pilha ${listar(p.pilha)}`,
        p.acao === "objetivo" ? "radio" : "trace");
    }
    hud({ visitados, passo: p.n, total: trace.passos.length });
    await esperar(p.acao === "backtrack" ? 70 : 110);
  }
  explorador.setAttribute("opacity", "0");
}

async function desenharRota(trace, execucao) {
  conferir(execucao);
  const svg = $("#mapa-svg-host svg");
  const rota = svg.querySelector(".rota");
  const pontos = trace.caminho.map(posicao).filter(Boolean);
  trace.caminho.forEach((n) => estado.noSvg.get(n)?.classList.add("no-caminho"));
  if (pontos.length < 2) return;
  rota.setAttribute("d", pontos.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" "));
  rota.setAttribute("opacity", "1");
  if (estado.pular) return;
  // Fio de Ariadne: o traço aparece do começo ao fim via stroke-dashoffset.
  const comprimento = rota.getTotalLength();
  rota.classList.add("desenhando");
  rota.style.strokeDasharray = `${comprimento}`;
  rota.style.strokeDashoffset = `${comprimento}`;
  rota.getBoundingClientRect();
  rota.style.strokeDashoffset = "0";
  await esperar(1400);
  conferir(execucao);
  rota.classList.remove("desenhando");
  rota.style.strokeDasharray = "";
  rota.style.strokeDashoffset = "";
}

function carimbar(plano) {
  const principal = Object.values(plano.comparacao)[0];
  const selo = $("#selo");
  if (principal.encontrado) {
    selo.textContent = "AUTORIZADO PELA CENTRAL";
    selo.classList.remove("negado");
  } else {
    selo.textContent = principal.motivo.startsWith("sem caminho") ? "TÚNEL OBSTRUÍDO" : "DESPACHO NEGADO";
    selo.classList.add("negado");
  }
  selo.hidden = false;
  // reinicia a animação do carimbo
  selo.style.animation = "none";
  selo.getBoundingClientRect();
  selo.style.animation = "";
}

function mostrarCorrida(plano) {
  const box = $("#corrida");
  box.replaceChildren();
  const tabela = el("table", "tabela-corrida");
  const cab = el("tr");
  ["", "visitados", "passos", "backtracks", "máx. fronteira", "paradas"].forEach((t) => cab.appendChild(el("th", "", t)));
  tabela.appendChild(cab);
  for (const [nome, c] of Object.entries(plano.comparacao)) {
    const tr = el("tr", `alg-${nome.toLowerCase()}`);
    [nome, c.nos_visitados, c.passos, c.backtracks ?? "—", c.max_fronteira, c.paradas ?? "—"]
      .forEach((v) => tr.appendChild(el("td", "", String(v))));
    tabela.appendChild(tr);
  }
  box.appendChild(tabela);
  const c = Object.values(plano.comparacao);
  if (c.length === 2 && c[0].encontrado && c[1].encontrado) {
    const iguais = c[0].caminho.join("|") === c[1].caminho.join("|");
    box.appendChild(el("p", "linha-log", iguais
      ? "Mesma rota (rede sem ciclos: caminho único). A diferença está no esforço."
      : "Rotas diferentes."));
  }
  const d = plano.diagnostico;
  if (d.baldeacoes.length) {
    box.appendChild(el("p", "linha-log radio",
      `Baldeações: ${d.baldeacoes.map((b) => `${b.estacao} (L${b.de_linha}→L${b.para_linha})`).join(", ")}`));
  }
  if (d.obstrucoes.length) {
    box.appendChild(el("p", "linha-log erro", `Obstruções no caminho único: ${d.obstrucoes.join(", ")}`));
  }
}

function rastroPuro(plano, inferencia) {
  const L = [];
  L.push(`DESPACHO ${plano.origem} -> ${plano.destino}`);
  L.push(`bloqueadas (base lógica): ${listar(plano.bloqueadas)}`);
  for (const [nome, t] of Object.entries(plano.buscas)) {
    L.push("", `==== ${nome} · ${t.estrutura} ====`);
    for (const p of t.passos) {
      const ign = p.ignorados.length ? `  ignorados=${listar(p.ignorados.map((i) => `${i.no}:${i.motivo}`))}` : "";
      if (nome === "BFS") {
        L.push(`#${String(p.n).padStart(3)} nivel=${p.nivel} ${p.acao.padEnd(8)} ${p.no}` +
          `  descobertos=${listar(p.descobertos.map((d) => d.no))}  fila=${listar(p.fila)}${ign}`);
      } else if (p.acao === "backtrack") {
        L.push(`#${String(p.n).padStart(3)} prof=${p.profundidade} backtrack ${p.no} -> ${p.volta_para}  pilha=${listar(p.pilha)}${ign}`);
      } else {
        L.push(`#${String(p.n).padStart(3)} prof=${p.profundidade} ${p.acao.padEnd(9)} ${p.de ? p.de + " -> " : ""}${p.no}` +
          `${p.linhas ? "  linhas=" + p.linhas.join("/") : ""}  pilha=${listar(p.pilha)}${ign}`);
      }
    }
    L.push(`ordem:     ${listar(t.ordem)}`);
    L.push(`visitados: ${listar(t.visitados)}`);
    L.push(`pai:       ${Object.entries(t.pai).map(([k, v]) => `${k}<-${v ?? "∅"}`).join(", ")}`);
    L.push(`encontrado=${t.encontrado}  motivo=${t.motivo ?? "-"}`);
    L.push(`caminho:   ${listar(t.caminho)}`);
    L.push(`metricas:  ${JSON.stringify(t.metricas)}`);
  }
  L.push("", "==== INFERÊNCIA (encadeamento para frente) ====");
  L.push(`regras pendentes: ${listar(inferencia.regras_pendentes)}`);
  L.push(`total de fatos: ${inferencia.total_fatos}  derivados: ${inferencia.fatos_derivados.length}`);
  if (!inferencia.inferencias.length) L.push("nenhuma regra disparou");
  for (const i of inferencia.inferencias) {
    L.push(`#${i.n} it=${i.iteracao} ${i.regra}: ${i.fato.texto}  <=  ${i.justificativa.map((j) => j.texto).join(" ∧ ")}`);
  }
  $("#rastro-puro").textContent = L.join("\n");
}

// ------------------------------------------------------------ teatro de inferência

function mostrarInferencia(inf) {
  const box = $("#regras");
  box.replaceChildren();
  const todasPendentes = inf.regras.length > 0 && inf.regras_pendentes.length === inf.regras.length;
  $("#inferencia-resumo").textContent =
    `Base: ${inf.total_fatos} fatos · ${inf.fatos_derivados.length} derivados · ` +
    `bloqueadas: ${inf.bloqueadas.join(", ") || "nenhuma"}`;
  if (todasPendentes) {
    const aviso = el("div", "regras-aguardando");
    aviso.appendChild(el("strong", "", `${inf.regras[0].id}–${inf.regras.at(-1).id} aguardando texto oficial`));
    aviso.appendChild(el("span", "justificativa",
      "O motor de encadeamento está pronto; as regras entram quando o enunciado for fornecido. Nada é inventado."));
    box.appendChild(aviso);
  }
  const disparos = new Map();
  for (const i of inf.inferencias) {
    if (!disparos.has(i.regra)) disparos.set(i.regra, []);
    disparos.get(i.regra).push(i);
  }
  for (const r of inf.regras) {
    const d = disparos.get(r.id) || [];
    const div = el("div", `regra${d.length ? " disparada" : ""}${r.pendente ? " pendente" : ""}`);
    div.appendChild(el("span", "", `${r.id} · ${r.pendente ? "pendente" : r.texto_oficial || ""}`));
    for (const i of d) {
      div.appendChild(el("span", "justificativa",
        `${i.fato.texto} ⇐ ${i.justificativa.map((j) => j.texto).join(" ∧ ")}`));
    }
    if (!r.pendente && !d.length) div.appendChild(el("span", "justificativa", "não disparou"));
    box.appendChild(div);
  }
}

// ------------------------------------------------------------ rádio (SSE)

function pararRadio() {
  if (estado.radio) {
    estado.radio.fonte.close();
    clearTimeout(estado.radio.relogio);
    estado.radio = null;
  }
}

function narrar(params) {
  pararRadio();
  const radio = $("#radio");
  const fonte = $("#radio-fonte");
  radio.textContent = "";
  radio.classList.add("cursor-blink");
  radio.classList.remove("erro");
  fonte.textContent = "· sintonizando";

  const qs = new URLSearchParams({ origem: params.origem, destino: params.destino, algoritmo: params.algoritmo });
  params.bloqueadas.forEach((b) => qs.append("bloqueadas", b));
  const es = new EventSource(`/api/narrar?${qs}`);
  const sessao = { fonte: es, relogio: null, terminou: false };
  estado.radio = sessao;

  const falhar = (msg) => {
    if (sessao.terminou) return;
    sessao.terminou = true;
    es.close();
    clearTimeout(sessao.relogio);
    radio.classList.remove("cursor-blink");
    radio.classList.add("erro");
    radio.textContent += (radio.textContent ? "\n" : "") + `[SINAL PERDIDO] ${msg}`;
    fonte.textContent = "· erro";
    log(`rádio: ${msg}`, "erro");
  };
  const vigiar = () => {
    clearTimeout(sessao.relogio);
    sessao.relogio = setTimeout(() => falhar("sem resposta da Central (timeout)"), NARRACAO_TIMEOUT_MS);
  };
  const dados = (ev) => JSON.parse(ev.data);
  vigiar();

  es.addEventListener("fatos", (ev) => {
    vigiar();
    const f = dados(ev);
    const confere = f.origem === params.origem && f.destino === params.destino &&
      f.bloqueadas.join("|") === params.bloqueadas.join("|") &&
      Object.keys(f.esforco).join("|") === Object.keys(estado.plano.comparacao).join("|");
    if (!confere) falhar("narração não corresponde ao despacho exibido (parâmetros divergentes)");
  });
  es.addEventListener("inicio", (ev) => {
    vigiar();
    const d = dados(ev);
    if (d.reiniciar) {
      radio.textContent = "";
      log("rádio: Llama caiu no meio — texto parcial descartado, Central offline assume", "erro");
    }
    fonte.textContent = d.fonte === "llama" ? "· LLAMA" : `· OFFLINE (${d.motivo})`;
  });
  es.addEventListener("trecho", (ev) => {
    vigiar();
    radio.textContent += dados(ev).texto;
  });
  es.addEventListener("fim", () => {
    sessao.terminou = true;
    es.close();
    clearTimeout(sessao.relogio);
    radio.classList.remove("cursor-blink");
    if (estado.radio === sessao) estado.radio = null;
  });
  // EventSource reconecta sozinho ao fechar: fim sem "fim" é erro, nunca espera.
  es.onerror = () => falhar("transmissão encerrada sem o sinal de fim");
}

// ------------------------------------------------------------ despacho

async function despachar() {
  const execucao = ++estado.execucao;
  estado.pular = false;
  const params = {
    origem: estado.origem,
    destino: estado.destino,
    bloqueadas: [...estado.bloqueadas],
    algoritmo: $("#algoritmo").value,
  };
  pararRadio();
  limparReproducao();
  $("#log").replaceChildren();
  $("#radio").textContent = "Aguardando o fim da reprodução.";
  $("#radio-fonte").textContent = "";
  $("#btn-pular").disabled = false;
  hud();
  log(`despacho: ${params.origem} → ${params.destino} · bloqueadas ${listar(params.bloqueadas)} · ${params.algoritmo}`);

  try {
    const [plano, inferencia] = await Promise.all([
      api("/api/rota", params),
      api("/api/inferencia", { bloqueadas: params.bloqueadas }),
    ]);
    conferir(execucao);
    estado.plano = plano;
    mostrarInferencia(inferencia);
    rastroPuro(plano, inferencia);

    const buscas = Object.entries(plano.buscas);
    for (const [nome, trace] of buscas) {
      if (buscas.length > 1) limparReproducao();
      if (!trace.encontrado) log(`${nome}: ${trace.motivo}`, "erro");
      if (nome === "BFS") await reproduzirBFS(trace, execucao);
      else await reproduzirDFS(trace, execucao);
      await esperar(500);
    }
    const principal = buscas[0][1];
    await desenharRota(principal, execucao);
    conferir(execucao);
    hud({ visitados: principal.metricas.nos_visitados, passo: principal.metricas.passos,
      paradas: principal.metricas.paradas });
    carimbar(plano);
    mostrarCorrida(plano);
    narrar(params);
  } catch (erro) {
    if (erro instanceof Cancelado) return;
    log(String(erro.message || erro), "erro");
    $("#radio").textContent = "Despacho não concluído.";
  } finally {
    if (execucao === estado.execucao) $("#btn-pular").disabled = true;
  }
}

function limparTudo() {
  estado.execucao += 1;
  pararRadio();
  estado.origem = null;
  estado.destino = null;
  estado.bloqueadas = [];
  estado.plano = null;
  definirModo("origem");
  limparReproducao();
  atualizarSelecao();
  hud();
  $("#log").replaceChildren();
  $("#radio").textContent = "Aguardando despacho.";
  $("#radio-fonte").textContent = "";
  $("#btn-pular").disabled = true;
}

// ------------------------------------------------------------ início

async function iniciar() {
  hud();
  document.querySelectorAll(".modo").forEach((b) =>
    b.addEventListener("click", () => definirModo(b.dataset.modo)));
  $("#btn-despachar").addEventListener("click", despachar);
  $("#btn-pular").addEventListener("click", () => { estado.pular = true; });
  $("#btn-limpar").addEventListener("click", limparTudo);
  $("#btn-auditoria").addEventListener("click", (ev) => {
    const ligado = document.body.classList.toggle("modo-auditoria");
    ev.currentTarget.setAttribute("aria-pressed", String(ligado));
  });

  try {
    const [svg, rede, locais] = await Promise.all([
      carregarMapa(), api("/api/estacoes"), api("/api/locais"),
    ]);
    estado.rede = rede;
    estado.locais = locais.locais;
    if (locais.pendente) log(`locais: ${locais.aviso}`);
    conferirMapa();
    ligarMapa(svg);
    ligarBusca();
    ligarInterpretacao();
    atualizarSelecao();
    $("#status-api").textContent = "CENTRAL ONLINE";
    $("#status-api").classList.add("ok");
  } catch (erro) {
    $("#status-api").textContent = "CENTRAL FORA DO AR";
    $("#status-api").classList.add("falha");
    log(String(erro.message || erro), "erro");
  }
}

iniciar();
