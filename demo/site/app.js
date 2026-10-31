"use strict";

const ROLE_TR = { employee: "Çalışan", it_specialist: "IT Uzmanı", manager: "Yönetici" };
const AGENT_TR = { triage: "Triage", solution: "Solution", ticket: "Ticket",
  analytics: "Analytics", supervisor: "Supervisor", guardrail: "Guardrail" };
const STEP_DELAY = 350;

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let data = null, current = null, turnIndex = 0, playing = false, token = 0;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Small markdown subset used by the agents: bold, italics, code, lists, tables, fences. */
function md(src) {
  const lines = String(src).split("\n");
  let html = "", i = 0;
  const inline = (t) => esc(t)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|\s)_([^_]+)_(?=\s|$|[.,])/g, "$1<em>$2</em>");
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const buf = []; i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      const lang = line.slice(3).trim();
      html += codeblock(buf.join("\n"), lang || "Raw code"); i++; continue;
    }
    if (line.trim().startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(lines[i++]);
      const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const body = rows.filter((r) => !/^\|?\s*-{3}/.test(r.trim().replace(/^\|/, "")));
      html += '<div class="table-wrap"><table>' + body.map((r, k) => "<tr>" + cells(r).map((c) =>
        k === 0 ? `<th>${inline(c)}</th>` : `<td>${inline(c)}</td>`).join("") + "</tr>").join("")
        + "</table></div>";
      continue;
    }
    if (/^\d+\.\s/.test(line)) {
      html += "<ol>";
      while (i < lines.length && /^\d+\.\s/.test(lines[i]))
        html += `<li>${inline(lines[i++].replace(/^\d+\.\s/, ""))}</li>`;
      html += "</ol>"; continue;
    }
    if (/^- /.test(line)) {
      html += "<ul>";
      while (i < lines.length && /^- /.test(lines[i])) html += `<li>${inline(lines[i++].slice(2))}</li>`;
      html += "</ul>"; continue;
    }
    const em = line.trim().match(/^_(.+)_$/);  // "_Kaynak: vpn_error_809_" (ids contain "_")
    if (em) html += `<p><em>${esc(em[1])}</em></p>`;
    else if (line.trim()) html += `<p>${inline(line)}</p>`;
    i++;
  }
  return html;
}

const MARK = '<svg class="mark" viewBox="0 0 24 24" aria-hidden="true"><g fill="#f80061">' +
  '<circle cx="12" cy="5" r="3.2"/><circle cx="12" cy="19" r="3.2"/><circle cx="5" cy="12" r="3.2"/>' +
  '<circle cx="19" cy="12" r="3.2"/></g></svg>';
const EXAMPLES = {
  employee: ["Outlook açılmıyor 0x800CCC0E hatası veriyor, ayrıca VPN de bağlanmıyor.",
    "Yazıcı kağıt sıkıştırıyor", "Talebimin durumu ne?"],
  it_specialist: ["Tüm ofiste internet yok, kimse çalışamıyor", "Hesabım kilitlendi"],
  manager: ["Bu hafta muhasebeden kaç VPN ticket'ı geldi?",
    "Departmanlara göre ticket dağılımını raporla", "Ortalama çözüm süresi kaç saat?"],
};
const DEPT = { calisan: "Muhasebe", uzman: "Operasyon", yonetici: "Muhasebe" };

function add(html, cls) {
  const el = document.createElement("div");
  if (cls) el.className = cls;
  el.innerHTML = html;
  $("log").appendChild(el);
  el.scrollIntoView({ block: "end", behavior: "smooth" });
  return el;
}

/* A Chainlit step: "Used <name> ˅", expanding to content with a pink left border. */
function step(name, detail, pinkMark = false) {
  return add(`${pinkMark ? MARK : '<span class="dot"></span>'}<details class="step">` +
    `<summary>Used ${name}</summary><div class="detail">${detail}</div></details>`, "row");
}

function message(markdown) {
  return add(`${MARK}<div class="msg">${md(markdown)}</div>`, "row msg-row");
}

function renderEvent(e) {
  switch (e.type) {
    case "nlu": {
      const intents = e.intents.map((i) =>
        `<code>${esc(i.label)}</code> (${Number(i.score).toFixed(2)})`).join(", ");
      const rows = e.entities.map((x) => `| ${x.label} | ${x.text} |`).join("\n") || "| - | - |";
      return step("NLU (intent + NER)", md(`**Backend:** ${e.backend || "?"}`) +
        `<p><strong>Niyet:</strong> ${intents}</p>` + md(`| Etiket | Değer |\n|---|---|\n${rows}`));
    }
    case "plan":
      return step("Supervisor planı", md(e.steps.map((s) =>
        `${s.id}. \`${s.intent}\` → ${s.agent}${s.note ? " — " + s.note : ""}`).join("\n")), true);
    case "plan_revision":
      return step("Plan revizyonu", md(`Adım ${e.step}: ${e.change}`), true);
    case "route":
      return step(`→ ${esc(AGENT_TR[e.agent] || e.agent)} Agent`,
        md(`Adım ${e.step} (\`${e.intent}\`) — plan: ${e.plan}`));
    case "triage":
      return step("Triage sonucu", md(`Öncelik: **${e.severity}** ${e.note || ""}`), true);
    case "tool_call":
      return step(`🔧 ${esc(e.tool)}`, codeblock(JSON.stringify(e.args, null, 1), "Input") +
        `<p>${e.ok ? "ok" : "hata: " + esc(e.error)}</p>`);
    case "sql":
      return step("SQL guard", codeblock(e.sql, "Input") +
        `<p>${e.ok ? "geçti" : "engellendi: " + esc(e.reason)}</p>`);
    case "guardrail": {
      const { type, ...rest } = e;
      return step(`🛡️ Guardrail: ${esc(e.kind)}`, codeblock(JSON.stringify(rest), "Output"), true);
    }
    case "message":
      return message(e.content);
    default:
      return null;
  }
}

function codeblock(text, label = "Raw code") {
  return `<div class="codeblock"><div class="cb-head">${esc(label)}</div><pre>${esc(text)}</pre></div>`;
}

function welcome(sc) {
  const examples = EXAMPLES[sc.role].map((x) => `- ${x}`).join("\n");
  message(`Merhaba! **${ROLE_TR[sc.role]}** rolüyle giriş yaptınız (${DEPT[sc.user] || "-"}).` +
    `\n\nÖrnek talepler:\n${examples}`);
}

async function play(events, my) {
  for (const e of events) {
    if (my !== token) return null;
    if (e.type === "done") continue;
    if (e.type === "interrupt") return e;
    renderEvent(e);
    await sleep(e.type === "message" ? STEP_DELAY * 2 : STEP_DELAY);
  }
  return null;
}

function approvalCard(e) {
  const d = e.draft;
  const el = add(`${MARK}<div class="msg"><p><strong>${esc(e.question)}</strong></p>` +
    md(`| Alan | Değer |\n|---|---|\n| Başlık | ${d.title} |\n| Öncelik | ${d.severity}` +
      `${e.escalate ? " (L2 eskalasyon)" : ""} |\n| Kategori | ${d.category} |`) +
    codeblock(d.description) +
    `<div class="actions"><button data-a="approve">✅ Onayla</button>` +
    `<button data-a="reject">❌ Reddet</button></div></div>`, "row msg-row");
  return new Promise((resolve) => {
    el.querySelectorAll(".actions button").forEach((btn) => btn.addEventListener("click", () => {
      el.querySelector(".actions").outerHTML =
        `<p class="chosen"><strong>Selected:</strong> ${btn.dataset.a === "approve" ? "✅ Onayla" : "❌ Reddet"}</p>`;
      resolve(btn.dataset.a);
    }));
  });
}

function prepareNext() {
  const turn = current.turns[turnIndex];
  const input = $("next-text"), send = $("send");
  if (!turn) {
    input.value = "";
    input.placeholder = "Senaryo bitti — üstten başka senaryo seçin";
    send.disabled = true;
    return;
  }
  input.value = turn.text;
  send.disabled = false;
}

async function sendTurn() {
  if (playing) return;
  const turn = current.turns[turnIndex];
  if (!turn || turn.kind !== "message") return;
  playing = true;
  const my = token;
  $("send").disabled = true;
  add(`<div class="user-bubble">${esc(turn.text)}</div>`, "user-row");
  turnIndex++;
  let pending = await play(turn.events, my);
  while (pending && my === token) {
    const approval = current.turns[turnIndex];
    const choice = await approvalCard(pending);
    if (my !== token) break;
    turnIndex++;
    pending = await play(approval[choice], my);
    if (choice === "reject") {
      add("Bu dalda konuşma burada bitiyor. Onay dalını görmek için sol üstteki kalem simgesiyle baştan başlayın.", "end");
      turnIndex = current.turns.length;
    }
  }
  playing = false;
  if (my === token) prepareNext();
}

function select(sc) {
  token++;
  playing = false;
  current = sc;
  turnIndex = 0;
  $("log").innerHTML = "";
  $("scenario").value = sc.id;
  $("avatar").textContent = sc.user[0];
  $("avatar").title = `${sc.user} · ${ROLE_TR[sc.role]}`;
  welcome(sc);
  prepareNext();
  try { history.replaceState(null, "", `#${sc.id}`); } catch (_) { /* file:// preview */ }
}

async function init() {
  try {
    data = await (await fetch(`recordings.json?v=${Date.now()}`, { cache: "no-store" })).json();
  } catch (err) {
    message(`Kayıtlar yüklenemedi: ${err}`);
    return;
  }
  $("meta-commit").textContent = data.commit;
  $("meta-nlu").textContent = data.nlu_backend === "rules" ? "kural tabanlı" : data.nlu_backend;
  $("meta-llm").textContent = data.llm.startsWith("kapalı") ? "kapalı" : data.llm;
  const select_ = $("scenario");
  for (const sc of data.scenarios) {
    const opt = document.createElement("option");
    opt.value = sc.id;
    opt.textContent = `${sc.title} (${ROLE_TR[sc.role]})`;
    select_.appendChild(opt);
  }
  select_.addEventListener("change", () =>
    select(data.scenarios.find((s) => s.id === select_.value)));
  select(data.scenarios.find((s) => `#${s.id}` === location.hash) || data.scenarios[0]);
}

function toggleTheme() {
  const root = document.documentElement;
  const dark = (root.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches
    ? "light" : "dark")) === "dark";
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("theme", root.dataset.theme); } catch (_) { /* private mode */ }
}
try {
  const saved = localStorage.getItem("theme");
  if (saved) document.documentElement.dataset.theme = saved;
} catch (_) { /* private mode */ }

$("composer").addEventListener("submit", (ev) => { ev.preventDefault(); sendTurn(); });
$("restart").addEventListener("click", () => current && select(current));
$("theme").addEventListener("click", toggleTheme);
init();
