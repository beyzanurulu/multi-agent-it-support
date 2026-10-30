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
      html += `<pre>${esc(buf.join("\n"))}</pre>`; i++; continue;
    }
    if (line.trim().startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(lines[i++]);
      const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const body = rows.filter((r) => !/^\|?\s*-{3}/.test(r.trim().replace(/^\|/, "")));
      html += "<table>" + body.map((r, k) => "<tr>" + cells(r).map((c) =>
        k === 0 ? `<th>${inline(c)}</th>` : `<td>${inline(c)}</td>`).join("") + "</tr>").join("")
        + "</table>";
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

function add(html, cls) {
  const el = document.createElement("div");
  if (cls) el.className = cls;
  el.innerHTML = html;
  $("log").appendChild(el);
  el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  return el;
}

function step(summary, detail, kind = "") {
  return add(`<details class="step ${kind}"><summary>${summary}</summary>` +
    `<div class="detail">${detail}</div></details>`);
}

function renderEvent(e) {
  switch (e.type) {
    case "nlu": {
      const intents = e.intents.map((i) =>
        `<span class="chip">${esc(i.label)} ${Number(i.score).toFixed(2)}</span>`).join("");
      const ents = e.entities.length
        ? "<table><tr><th>Etiket</th><th>Değer</th></tr>" + e.entities.map((x) =>
          `<tr><td>${esc(x.label)}</td><td>${esc(x.text)}</td></tr>`).join("") + "</table>"
        : "<p>Entity yok</p>";
      return step(`NLU — ${e.intents.map((i) => esc(i.label)).join(", ")}`,
        `<div class="chips">${intents}</div>${ents}<p>Backend: ${esc(e.backend)}</p>`);
    }
    case "plan":
      return step("Supervisor planı", "<ol>" + e.steps.map((s) =>
        `<li><code>${esc(s.intent)}</code> → ${esc(s.agent)}${s.note ? " — " + esc(s.note) : ""}</li>`)
        .join("") + "</ol>");
    case "plan_revision":
      return step("Plan revizyonu", `Adım ${esc(e.step)}: ${esc(e.change)}`);
    case "route":
      return step(`→ ${esc(AGENT_TR[e.agent] || e.agent)} Agent`,
        `Adım ${esc(e.step)} (<code>${esc(e.intent)}</code>) — plan: ${esc(e.plan)}`);
    case "triage":
      return step(`Triage — öncelik: ${esc(e.severity)}`, esc(e.note || "Ek not yok"));
    case "tool_call":
      return step(esc(e.tool), `<pre>${esc(JSON.stringify(e.args, null, 1))}</pre>` +
        (e.ok ? `<p>ok${e.ms ? ` · ${e.ms} ms` : ""}</p>` : `<p>hata: ${esc(e.error)}</p>`), "tool");
    case "sql":
      return step(`SQL guard — ${e.ok ? "geçti" : "engellendi"}`,
        `<pre>${esc(e.sql)}</pre>${e.ok ? "" : `<p>${esc(e.reason)}</p>`}`, "tool");
    case "guardrail": {
      const { type, ...rest } = e;
      return step(`Guardrail: ${esc(e.kind)}`, `<pre>${esc(JSON.stringify(rest, null, 1))}</pre>`,
        "guard");
    }
    case "message":
      return add(`<div class="author">${esc(AGENT_TR[e.agent] || e.agent || "Asistan")}</div>` +
        `<div class="body">${md(e.content)}</div>`, `msg ${e.agent === "guardrail" ? "guardrail" : ""}`);
    default:
      return null;
  }
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
  const el = add(`<h3>${esc(e.question)}</h3>
    <table><tr><th>Başlık</th><td>${esc(d.title)}</td></tr>
    <tr><th>Öncelik</th><td>${esc(d.severity)}${e.escalate ? " (L2 eskalasyon)" : ""}</td></tr>
    <tr><th>Kategori</th><td>${esc(d.category)}</td></tr></table>
    <pre>${esc(d.description)}</pre>
    <div class="actions"><button class="primary" data-a="approve">✅ Onayla</button>
    <button class="ghost" data-a="reject">❌ Reddet</button></div>`, "approval");
  return new Promise((resolve) => {
    el.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      el.querySelector(".actions").outerHTML =
        `<p class="chosen">Seçim: ${b.dataset.a === "approve" ? "Onaylandı" : "Reddedildi"}</p>`;
      resolve(b.dataset.a);
    }));
  });
}

function prepareNext() {
  const turn = current.turns[turnIndex];
  const input = $("next-text"), send = $("send");
  if (!turn) {
    input.value = "Senaryo bitti";
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
  add(esc(turn.text), "bubble-user");
  turnIndex++;
  let pending = await play(turn.events, my);
  while (pending && my === token) {
    const approval = current.turns[turnIndex];
    const choice = await approvalCard(pending);
    if (my !== token) break;
    turnIndex++;
    pending = await play(approval[choice], my);
    if (choice === "reject") {
      add("Bu dalda konuşma burada bitiyor. Onay dalını görmek için “Baştan”a basın.", "end");
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
  $("sc-title").textContent = sc.title;
  $("sc-desc").textContent = sc.description;
  $("sc-role").textContent = `${ROLE_TR[sc.role]} · ${sc.user}`;
  document.querySelectorAll("#scenario-list button").forEach((b) =>
    b.setAttribute("aria-current", b.dataset.id === sc.id ? "true" : "false"));
  prepareNext();
  try { history.replaceState(null, "", `#${sc.id}`); } catch (_) { /* file:// preview */ }
}

async function init() {
  try {
    data = await (await fetch("recordings.json", { cache: "no-store" })).json();
  } catch (err) {
    $("sc-title").textContent = "Kayıtlar yüklenemedi";
    $("sc-desc").textContent = String(err);
    return;
  }
  $("meta-commit").textContent = data.commit;
  $("meta-nlu").textContent = data.nlu_backend === "rules" ? "kural tabanlı" : data.nlu_backend;
  $("meta-llm").textContent = data.llm;
  $("meta-date").textContent = new Date(data.recorded_at).toLocaleString("tr-TR");
  const list = $("scenario-list");
  for (const sc of data.scenarios) {
    const li = document.createElement("li");
    li.innerHTML = `<button type="button" data-id="${esc(sc.id)}">${esc(sc.title)}` +
      `<small>${esc(ROLE_TR[sc.role])}</small></button>`;
    li.querySelector("button").addEventListener("click", () => select(sc));
    list.appendChild(li);
  }
  const start = data.scenarios.find((s) => `#${s.id}` === location.hash) || data.scenarios[0];
  select(start);
}

$("composer").addEventListener("submit", (ev) => { ev.preventDefault(); sendTurn(); });
$("restart").addEventListener("click", () => current && select(current));
init();
