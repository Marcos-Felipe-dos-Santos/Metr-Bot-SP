/* MetrôBot SP — front (tema claro, 4 passos)
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
  origem: null,        // nome escolhido: estação ou local conhecido
  destino: null,
  fechadas: [],        // cenário simulado (vira fatos lógicos no backend)
  manutencao: [],
  lotadas: [],
  rede: null,          // /api/estacoes
  locais: [],          // /api/locais
  estacaoDoLocal: new Map(),
  tabela: null,        // /api/tabela-verdade
  noSvg: new Map(),    // nome -> <g.estacao>
  execucao: 0,         // id da reprodução atual (cancela a anterior)
  pular: false,
  plano: null,
  radio: null,         // EventSource ativo
  params: null,        // último pedido (para repetir a narração)
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
    g.classList.remove("onda", "fronteira", "explorada", "recuada", "no-caminho", "paralisada");
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

const ALVO_DO_MODO = {
  origem: "a origem",
  destino: "o destino",
  fechar: "uma estação fechada",
  manutencao: "uma estação com elevador parado",
  lotada: "uma estação lotada",
};

function definirModo(modo) {
  estado.modo = modo;
  for (const b of document.querySelectorAll(".modo")) {
    b.setAttribute("aria-pressed", String(b.dataset.modo === modo));
  }
  $("#dica-alvo").textContent = ALVO_DO_MODO[modo];
}

const LISTA_DO_MODO = { fechar: "fechadas", manutencao: "manutencao", lotada: "lotadas" };

/** Estação de um nome escolhido (a própria estação ou a do local). */
function estacaoDe(nome) {
  if (!nome) return null;
  return estado.estacaoDoLocal.get(nome) ?? nome;
}

function conhecido(nome) {
  return estado.estacaoDoLocal.has(nome) || estado.rede.estacoes.some((e) => e.nome === nome);
}

function rotulo(nome) {
  const estacao = estacaoDe(nome);
  return estacao === nome ? nome : `${nome} (${estacao})`;
}

/** Único ponto de entrada: clique no mapa, busca e intérprete chamam esta função. */
function escolher(nome) {
  if (!conhecido(nome)) {
    log(`"${nome}" não existe no backend`, "erro");
    return;
  }
  const estacao = estacaoDe(nome);
  const lista = LISTA_DO_MODO[estado.modo];
  if (lista) {
    const itens = estado[lista];
    const i = itens.indexOf(estacao);
    if (i >= 0) itens.splice(i, 1);
    else itens.push(estacao);
    if (lista === "fechadas" && [estacaoDe(estado.origem), estacaoDe(estado.destino)].includes(estacao)) {
      log(`${estacao} é origem/destino: fechamento registrado mesmo assim (o core decide)`, "erro");
    }
  } else if (estado.fechadas.includes(estacao)) {
    log(`${estacao} está fechada — reabra antes (modo FECHAR)`, "erro");
    return;
  } else if (estado.modo === "origem") {
    estado.origem = nome;
    definirModo("destino");
  } else {
    estado.destino = nome;
  }
  atualizarSelecao();
}

function linhasParalisadas() {
  return [...document.querySelectorAll(".paralisar:checked")].map((c) => c.value);
}

function atualizarSelecao() {
  const org = estacaoDe(estado.origem);
  const dst = estacaoDe(estado.destino);
  for (const [nome, g] of estado.noSvg) {
    g.classList.toggle("origem", nome === org);
    g.classList.toggle("destino", nome === dst);
    g.classList.toggle("bloqueada", estado.fechadas.includes(nome));
    g.classList.toggle("manutencao", estado.manutencao.includes(nome));
    g.classList.toggle("lotada", estado.lotadas.includes(nome));
  }
  $("#sel-origem").textContent = estado.origem ? rotulo(estado.origem) : "—";
  $("#sel-destino").textContent = estado.destino ? rotulo(estado.destino) : "—";
  // O campo mostra a escolha atual (sem atrapalhar quem está digitando nele).
  for (const [seletor, nome] of [["#busca", estado.origem], ["#busca-destino", estado.destino]]) {
    const campo = $(seletor);
    if (campo && campo !== document.activeElement) campo.value = nome ?? "";
  }
  $("#sel-fechadas").textContent = estado.fechadas.join(", ") || "nenhuma";
  $("#sel-manutencao").textContent = estado.manutencao.join(", ") || "nenhuma";
  $("#sel-lotadas").textContent = estado.lotadas.join(", ") || "nenhuma";
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
  const perto = estado.locais.filter((l) => l.estacao === g.dataset.nome).map((l) => l.nome);
  if (perto.length) {
    box.appendChild(el("br"));
    box.appendChild(el("span", "", `perto: ${perto.join(", ")}`));
  }
  const avisos = [
    [estado.fechadas, "FECHADA"],
    [estado.manutencao, "ELEVADOR EM MANUTENÇÃO"],
    [estado.lotadas, "LOTADA"],
  ].filter(([lista]) => lista.includes(g.dataset.nome));
  for (const [, texto] of avisos) {
    box.appendChild(el("br"));
    box.appendChild(el("span", "dossie-alerta", texto));
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
    rotulo: e.nome, detalhe: e.linhas.map((l) => l.nome).join(" + "),
  }));
  const locais = estado.locais.map((l) => ({
    rotulo: l.nome, detalhe: `local → ${l.estacao}`,
  }));
  return [...locais, ...estacoes];
}

/** Um campo de busca por passo; o campo só diz PARA ONDE vai o nome escolhido. */
function ligarBusca(seletorInput, seletorDrop, modoDoCampo) {
  const input = $(seletorInput);
  const drop = $(seletorDrop);
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
    definirModo(modoDoCampo);
    escolher(item.rotulo);
    input.value = "";
    fechar();
  };

  input.addEventListener("focus", () => definirModo(modoDoCampo));
  input.addEventListener("input", () => {
    const termo = normalizar(input.value);
    drop.replaceChildren();
    if (!termo) return fechar();
    // Só ordena texto para o dropdown: exato primeiro, depois "começa com".
    const peso = (o) => {
      const n = normalizar(o.rotulo);
      return n === termo ? 0 : n.startsWith(termo) ? 1 : 2;
    };
    itens = opcoesBusca()
      .filter((o) => normalizar(o.rotulo).includes(termo))
      .sort((a, b) => peso(a) - peso(b))
      .slice(0, 12);
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
    avisar("Lendo a frase…", "");
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
        avisar(`O servidor não entendeu: ${detalhe}`, "erro");
        log(`interpretar: ${detalhe}`, "erro");
        return;
      }
      const fonte = dados.fonte === "llm" ? dados.modelo : `offline — ${dados.motivo}`;
      if (!dados.origem || !dados.destino) {
        // Como no PDF: sem origem E destino válidos, o pedido é rejeitado inteiro.
        avisar(`Não entendi origem/destino (${fonte}). Escolha pelo mapa ou pela busca.`, "erro");
        log(`interpretar (${fonte}): ${JSON.stringify(dados.extraido)} → rejeitado`, "erro");
        $("#busca").focus();
        return;
      }
      estado.origem = dados.origem;
      estado.destino = dados.destino;
      estado.fechadas = [...dados.fechadas];
      $("#acessibilidade").checked = dados.acessibilidade;
      definirModo("fechar");
      atualizarSelecao();
      const partes = [
        `origem ${rotulo(dados.origem)}`,
        `destino ${rotulo(dados.destino)}`,
        `fechadas ${listar(dados.fechadas)}`,
        `acessibilidade ${dados.acessibilidade ? "sim" : "não"}`,
      ];
      avisar(`Entendido via ${fonte}: ${partes.join(" · ")}. Confira e clique em "Traçar rota".`, "trace");
      log(`interpretar (${fonte}): ${JSON.stringify(dados.extraido)} → ${partes.join(" · ")}`, "trace");
    } catch (erro) {
      avisar(`Sem contato com o servidor: ${erro.message}`, "erro");
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
    selo.textContent = "Rota traçada";
    selo.classList.remove("negado");
  } else {
    selo.textContent = principal.motivo.startsWith("sem caminho")
      ? "Destino inalcançável" : "Não foi possível traçar";
    selo.classList.add("negado");
  }
  selo.hidden = false;
  $("#resultado").hidden = false;
}

/** Itinerário legível: vem pronto do diagnóstico do backend, nada é recalculado. */
function mostrarPassos(plano) {
  const lista = $("#passos");
  lista.replaceChildren();
  const principal = Object.values(plano.comparacao)[0];
  if (!principal.encontrado) {
    const li = el("li", "vazio", plano.diagnostico.obstrucoes.length
      ? `Sem caminho: ${plano.diagnostico.obstrucoes.join(", ")} bloqueia(m) a passagem.`
      : "Sem caminho entre as duas estações.");
    lista.appendChild(li);
    return;
  }
  const baldeacaoEm = new Map(plano.diagnostico.baldeacoes.map((b) => [b.estacao, b]));
  for (const t of plano.diagnostico.trechos) {
    const li = el("li");
    li.appendChild(el("span", "", `${t.de} → ${t.ate} · ${t.paradas} parada(s)`));
    const tag = el("span", `linha-tag l${t.linha}`, `Linha ${nomeDaLinha(t.linha)}`);
    li.appendChild(tag);
    lista.appendChild(li);
    const b = baldeacaoEm.get(t.ate);
    if (b) {
      lista.appendChild(el("li", "baldeacao",
        `Baldeação na ${b.estacao}: Linha ${nomeDaLinha(b.de_linha)} → Linha ${nomeDaLinha(b.para_linha)}`));
    }
  }
  lista.appendChild(el("li", "vazio",
    `Chegada: ${plano.destino} · ${principal.paradas} parada(s) no total.`));
}

function nomeDaLinha(id) {
  return estado.rede.linhas.find((l) => l.id === id).nome;
}

function mostrarCorrida(plano) {
  const box = $("#corrida");
  box.replaceChildren();
  const tabela = el("table", "tabela-corrida");
  const cab = el("tr");
  ["", "visitados", "passos", "backtracks", "máx. fronteira", "paradas", "tempo"].forEach((t) => cab.appendChild(el("th", "", t)));
  tabela.appendChild(cab);
  for (const [nome, c] of Object.entries(plano.comparacao)) {
    const tr = el("tr", `alg-${nome.toLowerCase()}`);
    [nome, c.nos_visitados, c.passos, c.backtracks ?? "—", c.max_fronteira, c.paradas ?? "—",
      c.tempo_min === null ? "—" : `~${c.tempo_min} min`]
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
  const nomeLinha = (id) => estado.rede.linhas.find((l) => l.id === id).nome;
  const resumo = el("dl", "resumo");
  const item = (rotuloItem, valor, tipo = "") => {
    resumo.appendChild(el("dt", "", rotuloItem));
    resumo.appendChild(el("dd", tipo, String(valor)));
  };
  const principal = Object.values(plano.comparacao)[0];
  item("paradas", principal.paradas ?? "sem rota");
  item("baldeações", d.baldeacoes.length
    ? `${d.baldeacoes.length}: ${d.baldeacoes.map((b) => `na ${b.estacao}, ${nomeLinha(b.de_linha)} → ${nomeLinha(b.para_linha)}`).join("; ")}`
    : "0");
  item("tempo estimado", d.tempo_min === null ? "—" : `~${d.tempo_min} min (2 min por trecho)`);
  item("alertas", plano.alertas.length
    ? plano.alertas.map((a) => `${a.papel}: ${a.estacao} (elevador)`).join("; ") : "nenhum",
  plano.alertas.length ? "erro" : "");
  item("lotação", plano.alertas_lotacao.join(", ") || "nenhuma", plano.alertas_lotacao.length ? "radio" : "");
  item("bloqueadas (lógica)", plano.bloqueadas.join(", ") || "nenhuma");
  item("regras disparadas", plano.regras_disparadas.join(", "));
  if (d.obstrucoes.length) item("obstruções", d.obstrucoes.join(", "), "erro");
  box.appendChild(resumo);
}

function rastroPuro(plano, inferencia) {
  const L = [];
  L.push(`DESPACHO ${plano.origem} -> ${plano.destino}`);
  L.push(`cenário: ${JSON.stringify(plano.cenario)}`);
  L.push(`bloqueadas (base lógica): ${listar(plano.bloqueadas)}`);
  L.push(`alertas: ${JSON.stringify(plano.alertas)}  lotação: ${listar(plano.alertas_lotacao)}`);
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
  L.push(`regras disparadas: ${listar(inferencia.regras_disparadas)}`);
  L.push(`integrações deduzidas (R6): ${listar(inferencia.integracoes)}`);
  L.push(`total de fatos: ${inferencia.total_fatos}  derivados: ${inferencia.fatos_derivados.length}`);
  if (!inferencia.inferencias.length) L.push("nenhuma regra disparou");
  for (const i of inferencia.inferencias) {
    L.push(`#${i.n} rodada=${i.iteracao} ${i.regra}: ${i.fato.texto}  <=  ${i.justificativa.map((j) => j.texto).join(" ∧ ")}`);
  }
  $("#rastro-puro").textContent = L.join("\n");
}

// ------------------------------------------------------------ teatro de inferência

function mostrarInferencia(inf) {
  const box = $("#regras");
  box.replaceChildren();
  $("#inferencia-resumo").textContent =
    `Base: ${inf.total_fatos} fatos · ${inf.fatos_derivados.length} derivados · ` +
    `integrações (R6): ${inf.integracoes.join(", ")} · disparadas: ${inf.regras_disparadas.join(", ")}`;
  const disparos = new Map();
  for (const i of inf.inferencias) {
    if (!disparos.has(i.regra)) disparos.set(i.regra, []);
    disparos.get(i.regra).push(i);
  }
  for (const r of inf.regras) {
    const d = disparos.get(r.id) || [];
    const div = el("div", `regra${d.length ? " disparada" : ""}`);
    const titulo = el("span", "", `${r.id} · ${r.nome}`);
    if (r.do_grupo) titulo.appendChild(el("span", "tag-grupo", " do grupo"));
    div.appendChild(titulo);
    div.appendChild(el("span", "formula", r.formula));
    // R6 dispara para as 3 integrações em todo despacho: resume para não poluir.
    const mostrar = r.id === "R6" ? d.slice(0, 1) : d.slice(0, 6);
    for (const i of mostrar) {
      div.appendChild(el("span", "justificativa",
        `${i.fato.texto} ⇐ ${i.justificativa.map((j) => j.texto).join(" ∧ ")}`));
    }
    if (d.length > mostrar.length) {
      div.appendChild(el("span", "justificativa", `… +${d.length - mostrar.length} (ver o trace completo abaixo)`));
    }
    if (!d.length) div.appendChild(el("span", "justificativa", "não disparou"));
    box.appendChild(div);
  }
}

function mostrarTabelaVerdade() {
  const t = estado.tabela;
  const v = (b) => (b ? "V" : "F");
  const linhas = [
    `TABELA-VERDADE (gerada pelo backend) — ${t.formula}`,
    ...Object.entries(t.legenda).map(([k, d]) => `  ${k} = ${d}`),
    "",
    "  P | Q | R | P ∧ (¬Q ∨ R)",
    "  --+---+---+-------------",
    ...t.linhas.map((l) => `  ${v(l.P)} | ${v(l.Q)} | ${v(l.R)} | ${v(l.resultado)}`),
  ];
  $("#tabela-verdade").textContent = linhas.join("\n");
}

// ------------------------------------------------------------ rádio (SSE)

function pararRadio() {
  if (estado.radio) {
    estado.radio.fonte.close();
    clearTimeout(estado.radio.relogio);
    estado.radio = null;
  }
  const parar = $("#btn-parar");
  if (parar) parar.disabled = true;
}

function narrar(params) {
  pararRadio();
  const radio = $("#radio");
  const fonte = $("#radio-fonte");
  radio.textContent = "";
  radio.classList.add("cursor-blink");
  radio.classList.remove("erro");
  fonte.textContent = "· preparando";
  $("#btn-parar").disabled = false;
  $("#btn-narrar").disabled = false;

  const qs = new URLSearchParams();
  for (const [chave, valor] of Object.entries(params)) {
    if (Array.isArray(valor)) valor.forEach((v) => qs.append(chave, v));
    else qs.append(chave, String(valor));
  }
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
    $("#btn-parar").disabled = true;
    log(`narração: ${msg}`, "erro");
  };
  const vigiar = () => {
    clearTimeout(sessao.relogio);
    sessao.relogio = setTimeout(() => falhar("sem resposta do servidor (tempo esgotado)"), NARRACAO_TIMEOUT_MS);
  };
  const dados = (ev) => JSON.parse(ev.data);
  vigiar();

  es.addEventListener("fatos", (ev) => {
    vigiar();
    const f = dados(ev);
    const confere = JSON.stringify(f.cenario) === JSON.stringify(estado.plano.cenario) &&
      Object.keys(f.esforco).join("|") === Object.keys(estado.plano.comparacao).join("|");
    if (!confere) falhar("narração não corresponde ao despacho exibido (parâmetros divergentes)");
  });
  es.addEventListener("inicio", (ev) => {
    vigiar();
    const d = dados(ev);
    if (d.reiniciar) {
      radio.textContent = "";
      log("narração: a IA caiu no meio — texto parcial descartado, o servidor assume", "erro");
    }
    fonte.textContent = d.fonte === "llama"
      ? `· IA na nuvem · LLM ${d.modelo}`
      : `· gerada no servidor · OFFLINE (${d.motivo})`;
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
    $("#btn-parar").disabled = true;
    if (estado.radio === sessao) estado.radio = null;
  });
  // EventSource reconecta sozinho ao fechar: fim sem "fim" é erro, nunca espera.
  es.onerror = () => falhar("transmissão encerrada sem o sinal de fim");
}

// ------------------------------------------------------------ despacho

async function despachar() {
  const execucao = ++estado.execucao;
  estado.pular = false;
  // Os MESMOS parâmetros vão para /api/rota, /api/inferencia e /api/narrar.
  const params = {
    origem: estado.origem,
    destino: estado.destino,
    fechadas: [...estado.fechadas],
    manutencao: [...estado.manutencao],
    acessibilidade: $("#acessibilidade").checked,
    paralisadas: linhasParalisadas(),
    horario_pico: $("#horario-pico").checked,
    lotadas: [...estado.lotadas],
    algoritmo: $("#algoritmo").value,
  };
  estado.params = params;
  pararRadio();
  limparReproducao();
  $("#log").replaceChildren();
  $("#radio").textContent = "A narração começa quando a animação terminar.";
  $("#radio-fonte").textContent = "";
  $("#btn-narrar").disabled = true;
  $("#btn-pular").disabled = false;
  hud();
  log(`despacho: ${params.origem} → ${params.destino} · fechadas ${listar(params.fechadas)} · ${params.algoritmo}`);

  try {
    const [plano, inferencia] = await Promise.all([
      api("/api/rota", params),
      api("/api/inferencia", { ...params, algoritmo: undefined }),
    ]);
    conferir(execucao);
    estado.plano = plano;
    mostrarInferencia(inferencia);
    rastroPuro(plano, inferencia);
    // Bloqueios deduzidos só pela lógica (R7: linha paralisada).
    const marcarParalisadas = () => {
      for (const e of plano.bloqueadas) {
        if (!plano.cenario.fechadas.includes(e)) estado.noSvg.get(e)?.classList.add("paralisada");
      }
    };
    marcarParalisadas();

    const buscas = Object.entries(plano.buscas);
    for (const [nome, trace] of buscas) {
      if (buscas.length > 1) {
        limparReproducao();
        marcarParalisadas();
      }
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
    mostrarPassos(plano);
    narrar(params);
  } catch (erro) {
    if (erro instanceof Cancelado) return;
    log(String(erro.message || erro), "erro");
    $("#radio").textContent = "Não foi possível traçar a rota.";
  } finally {
    if (execucao === estado.execucao) $("#btn-pular").disabled = true;
  }
}

function limparTudo() {
  estado.execucao += 1;
  pararRadio();
  estado.origem = null;
  estado.destino = null;
  estado.fechadas = [];
  estado.manutencao = [];
  estado.lotadas = [];
  estado.plano = null;
  estado.params = null;
  $("#acessibilidade").checked = false;
  $("#horario-pico").checked = false;
  document.querySelectorAll(".paralisar").forEach((c) => { c.checked = false; });
  $("#busca").value = "";
  $("#busca-destino").value = "";
  $("#interpretar-status").textContent = "";
  definirModo("origem");
  limparReproducao();
  atualizarSelecao();
  hud();
  $("#log").replaceChildren();
  $("#resultado").hidden = true;
  $("#corrida").replaceChildren();
  $("#passos").replaceChildren(el("li", "vazio", "Nenhuma rota traçada ainda."));
  $("#radio").textContent = "A narração aparece aqui depois de traçar a rota.";
  $("#radio-fonte").textContent = "";
  $("#btn-pular").disabled = true;
  $("#btn-narrar").disabled = true;
}

// ------------------------------------------------------------ início

async function iniciar() {
  hud();
  document.querySelectorAll(".modo").forEach((b) =>
    b.addEventListener("click", () => definirModo(b.dataset.modo)));
  $("#btn-despachar").addEventListener("click", despachar);
  $("#btn-pular").addEventListener("click", () => { estado.pular = true; });
  $("#btn-limpar").addEventListener("click", limparTudo);
  $("#btn-narrar").addEventListener("click", () => {
    if (estado.params && estado.plano) narrar(estado.params);
  });
  $("#btn-parar").addEventListener("click", () => {
    pararRadio();
    $("#radio").classList.remove("cursor-blink");
    $("#radio-fonte").textContent = "· narração interrompida";
  });
  $("#btn-auditoria").addEventListener("click", (ev) => {
    const ligado = document.body.classList.toggle("modo-auditoria");
    ev.currentTarget.setAttribute("aria-pressed", String(ligado));
    ev.currentTarget.textContent = ligado ? "Esconder detalhes da busca" : "Mostrar detalhes da busca";
  });

  try {
    const [svg, rede, locais, tabela] = await Promise.all([
      carregarMapa(), api("/api/estacoes"), api("/api/locais"), api("/api/tabela-verdade"),
    ]);
    estado.rede = rede;
    estado.locais = locais.locais;
    estado.estacaoDoLocal = new Map(locais.locais.map((l) => [l.nome, l.estacao]));
    estado.tabela = tabela;
    mostrarTabelaVerdade();
    conferirMapa();
    ligarMapa(svg);
    ligarBusca("#busca", "#dropdown", "origem");
    ligarBusca("#busca-destino", "#dropdown-destino", "destino");
    ligarInterpretacao();
    atualizarSelecao();
    $("#status-api").textContent = "conectado";
    $("#status-api").classList.add("ok");
  } catch (erro) {
    $("#status-api").textContent = "servidor fora do ar";
    $("#status-api").classList.add("falha");
    log(String(erro.message || erro), "erro");
  }
}

iniciar();
