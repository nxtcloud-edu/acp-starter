// 내 에이전트 플랫폼의 화면 코드. dashboard.py의 JSON API를 부른다.
// 새 기능은 먼저 dashboard.py에 API를 더하고, 여기서 그 API를 부르게 만든다.
// 화면은 엔진 이름을 따로 다루지 않는다. 엔진 목록은 /api/engines에서 받는다.
//
// 왼쪽 메뉴(대화, 에이전트, 스킬, 일, 결과함)를 고르면 오른쪽에 그 화면이 나온다.
// 모든 화면이 "목록 + 상세" 꼴이다. 목록에서 고르면 상세가 바뀐다.
// 대화의 목록은 대화들이고, 상세는 고른 대화의 기록과 입력칸이다.

const $ = (id) => document.getElementById(id);

// 화면의 상태. 서버에서 받은 것과 화면에서 고른 것을 한곳에 둔다.
const S = {
  view: "chat",
  engines: [], agents: [], skills: [], tasks: [], files: [],
  conversations: [],     // 대화 목록(제목, 에이전트, 엔진, 바뀐 때)
  conv: null,            // 고른 대화의 번호. null이면 첫 질문을 아직 보내지 않은 새 대화
  convData: null,        // 고른 대화 전체(메시지 포함)
  draft: null,           // 새 대화의 {agent, engine}
  confirmDelete: false,  // 대화 지우기를 한 번 누른 상태
  attached: [],          // 올린 파일: {key, name, size, status(uploading, done, error), path, preview, note}
  run: { state: "idle", agent: null, engine: null, conversation: null },   // 서버가 열어 둔 엔진 세션
  live: { conversation: null, events: [] },   // 답을 쓰는 중인 차례의 사건(답 조각, 도구, 허락 카드)
  selected: { agents: null, skills: null, tasks: null, outbox: null },
  chosenEngine: {},      // 에이전트 이름 → 상세에서 고른 엔진
  login: {},             // 엔진 이름 → 마지막 로그인 사건
  editing: null,         // 에이전트 양식: null, {mode: "new"}, {mode: "edit", name}
  pending: new Set(),    // 답을 기다리는 허락 요청 번호
};
let last = 0;            // 마지막으로 받은 사건 번호
let epoch = null;        // 서버를 켤 때마다 바뀌는 값. 바뀌면 처음부터 다시 읽는다
let answer = null;       // 지금 쓰는 중인 에이전트의 답 칸
const cards = {};        // 허락 요청 카드: 번호 → 칸

// ---- 도구 ----

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label, onclick, className) {
  const b = el("button", className || "", label);
  b.type = "button";
  b.onclick = onclick;
  return b;
}

const firstLine = (text) => (text || "").split("\n")[0].slice(0, 120);
const busy = () => S.run.state === "starting" || S.run.state === "busy";
const report = (e) => { add("note error", e.message); if (S.view !== "chat") alertBar(e.message); };

// "2026-10-21 15:30:12" → 오늘이면 "15:30", 아니면 "10-21 15:30"
function shortTime(stamp) {
  if (!stamp) return "";
  const d = new Date();
  const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return stamp.slice(0, 10) === today ? stamp.slice(11, 16) : stamp.slice(5, 16);
}

function alertBar(text) {
  const bar = $("banner");
  bar.textContent = text;
  bar.dataset.kind = "alert";
  bar.hidden = false;
  bar.onclick = () => { bar.hidden = true; bar.dataset.kind = ""; updateBanner(); };
}

// ---- 메뉴와 화면 바꾸기 ----

const VIEWS = ["chat", "agents", "skills", "tasks", "outbox"];

function showView(name) {
  if (!VIEWS.includes(name)) name = "chat";
  S.view = name;
  for (const v of VIEWS) $("view-" + v).hidden = v !== name;
  for (const b of document.querySelectorAll("#nav button")) b.classList.toggle("active", b.dataset.view === name);
  try { history.replaceState(null, "", "#" + name); } catch (e) { /* 주소를 못 바꿔도 화면은 바뀐다 */ }
  updateBanner();
  render();
  if (name === "chat") $("text").focus();
}

for (const b of document.querySelectorAll("#nav button")) b.onclick = () => showView(b.dataset.view);
$("status-pill").onclick = () => goToRunning();

// 고른 메뉴의 화면을 다시 그린다. 대화의 기록 칸은 다시 그리지 않는다.
// 기록 칸은 사건이 올 때마다 이어 그리고, 대화를 바꿀 때만 renderChat()으로 처음부터 그린다.
function render() {
  if (S.view === "chat") { renderChatList(); renderChatHead(); renderComposer(); }
  if (S.view === "agents") { renderAgentList(); renderAgentDetail(); }
  if (S.view === "skills") { renderSkillList(); renderSkillDetail(); }
  if (S.view === "tasks") { renderTaskList(); renderTaskDetail(); }
  if (S.view === "outbox") { renderOutboxList(); renderOutboxDetail(); }
}

// 허락을 기다리는 요청이 있으면 대화 메뉴에 숫자를 붙인다.
// 그 요청의 대화를 보고 있지 않으면 위에 띠를 띄운다. 띠를 누르면 그 대화로 간다.
function updateBanner() {
  const n = S.pending.size;
  $("badge-chat").hidden = n === 0;
  $("badge-chat").textContent = n;
  const bar = $("banner");
  const elsewhere = S.view !== "chat" || (S.run.conversation && S.run.conversation !== S.conv);
  if (n > 0 && elsewhere) {
    bar.textContent = `허락을 기다리는 요청이 ${n}건 있다. 눌러서 그 대화로 간다.`;
    bar.dataset.kind = "permission";
    bar.hidden = false;
    bar.onclick = () => goToRunning();
  } else if (bar.dataset.kind === "permission") {
    bar.hidden = true;            // 그 대화를 보고 있으면 카드가 보이므로 띠를 거둔다
    bar.dataset.kind = "";
  }
}

// ---- 이름과 색 (custom/brand.json) ----

async function loadBrand() {
  const brand = await api("GET", "/api/brand");
  document.title = brand.name;
  $("brand-name").textContent = brand.name;
  $("brand-tagline").textContent = brand.tagline || "";
  if (brand.accent) document.documentElement.style.setProperty("--accent", brand.accent);
}

// ---- 엔진 세션의 상태 ----

const STATE = { idle: "연결하지 않음", starting: "연결하는 중", ready: "준비됨", busy: "답을 쓰는 중", error: "오류" };

// 서버가 알려 준 엔진 세션(state, agent, engine, conversation)을 화면에 옮긴다.
function updateStatus(data) {
  const run = { state: data.state, agent: data.agent, engine: data.engine, conversation: data.conversation };
  const changed = JSON.stringify(run) !== JSON.stringify(S.run);
  S.run = run;
  const label = STATE[run.state] || run.state;
  $("status-pill").textContent = run.agent ? `${run.agent} · ${run.engine} · ${label}` : label;
  if (changed) { renderChatList(); renderChatHead(); renderComposer(); updateBanner(); }
}

// ---- 데이터 읽기 ----

async function loadEngines() { S.engines = (await api("GET", "/api/engines")).engines; }
async function loadSkills() { S.skills = (await api("GET", "/api/skills")).skills; }
async function loadTasks() { S.tasks = (await api("GET", "/api/tasks")).tasks; }
async function loadOutbox() { S.files = (await api("GET", "/api/outbox")).files; }
async function loadConversations() { S.conversations = (await api("GET", "/api/conversations")).conversations; }
async function loadAgents() {
  S.agents = (await api("GET", "/api/agents")).agents;
  if (!S.selected.agents && S.agents.length) S.selected.agents = S.agents[0].name;
}
const refresh = (...loaders) => Promise.all(loaders.map((f) => f())).then(render).catch(report);

// ---- 대화: 목록, 고르기, 새 대화, 지우기 ----

// 새 대화를 준비한다. 서버에는 첫 질문을 보낼 때 만든다.
function newDraft(agent, engine) {
  const a = S.agents.find((x) => x.name === agent) || S.agents[0];
  S.conv = null;
  S.convData = null;
  S.confirmDelete = false;
  S.draft = a ? { agent: a.name, engine: (a.name === agent && engine) || a.engine } : null;
}

async function selectConversation(id) {
  S.conv = id;
  S.convData = null;
  S.draft = null;
  S.confirmDelete = false;
  renderChat();
  let data;
  try { data = await api("GET", `/api/conversations/${id}`); }
  catch (e) { await loadConversations().catch(() => {}); newDraft(); renderChat(); return report(e); }
  if (S.conv !== id) return;      // 그사이 다른 대화를 골랐다
  S.convData = data;
  renderChat();
}

// 엔진 세션이 일하는 대화(허락 카드가 있는 대화)로 간다.
async function goToRunning() {
  if (S.run.conversation && S.run.conversation !== S.conv) await selectConversation(S.run.conversation);
  showView("chat");
}

function renderChat() { renderChatList(); renderChatHead(); renderLog(); renderComposer(); }

function renderChatList() {
  const list = $("chat-list");
  list.innerHTML = "";
  if (S.conv === null && S.draft) {
    const li = el("li", "selected");
    li.append(el("div", "name", "새 대화"), el("div", "meta", `${S.draft.agent} · ${S.draft.engine} · 첫 질문을 보내면 생긴다`));
    list.appendChild(li);
  }
  for (const c of S.conversations) {
    const li = el("li");
    li.classList.toggle("selected", c.id === S.conv);
    const name = el("div", "name");
    name.append(el("span", "", c.title || "제목 없음"));
    if (c.id === S.run.conversation && busy()) name.append(el("span", "badge on", "답을 쓰는 중"));
    li.append(name, el("div", "meta", `${c.agent} · ${c.engine} · ${shortTime(c.updated)}`));
    li.onclick = () => { if (c.id !== S.conv) selectConversation(c.id); };
    list.appendChild(li);
  }
  if (!list.children.length) list.appendChild(el("li", "empty", "대화가 없다. 에이전트 메뉴에서 에이전트를 만든다."));
}

function renderChatHead() {
  const head = $("chat-head");
  head.innerHTML = "";
  const c = S.convData;
  const who = c || S.draft;
  const left = el("div");
  if (!who) {
    left.append(el("h2", "", S.conv ? "불러오는 중…" : "대화"));
    head.append(left);
    return;
  }
  const running = c && S.run.conversation === c.id ? ` · ${STATE[S.run.state] || S.run.state}` : "";
  const listed = c && S.conversations.find((x) => x.id === c.id);   // 제목은 첫 질문을 보낸 뒤 목록에서 먼저 바뀐다
  left.append(el("h2", "", c ? (listed && listed.title) || c.title || "제목 없음" : "새 대화"),
              el("p", "muted", `에이전트 ${who.agent} · 엔진 ${who.engine}${running}`));
  const actions = el("div", "head-actions");
  actions.append(button("에이전트·엔진 바꾸기", () => {
    S.selected.agents = who.agent;
    S.chosenEngine[who.agent] = who.engine;
    S.editing = null;
    showView("agents");
  }, "ghost"));
  if (c && S.confirmDelete) {
    actions.append(el("span", "warn", "지우면 되돌릴 수 없다."),
                   button("지우기", deleteConversation, "danger"),
                   button("취소", () => { S.confirmDelete = false; renderChatHead(); }, "ghost"));
  } else if (c) {
    actions.append(button("지우기", () => { S.confirmDelete = true; renderChatHead(); }, "ghost"));
  }
  head.append(left, actions);
}

async function deleteConversation() {
  const { id, agent, engine } = S.convData;
  try { await api("DELETE", `/api/conversations/${id}`); }
  catch (e) { S.confirmDelete = false; renderChatHead(); return report(e); }
  await loadConversations().catch(report);
  const next = S.conversations[0];
  if (next) return selectConversation(next.id);
  newDraft(agent, engine);
  renderChat();
}

// 고른 대화의 기록을 처음부터 그린다. 답을 쓰는 중이면 그 차례의 사건을 이어 그린다.
function renderLog() {
  const log = $("log");
  log.innerHTML = "";
  answer = null;
  for (const id of Object.keys(cards)) delete cards[id];
  const c = S.convData;
  if (!c) {
    if (S.conv) log.appendChild(el("p", "placeholder", "불러오는 중…"));
    else if (S.draft) log.appendChild(el("p", "placeholder", `${S.draft.agent}에게 맡길 일을 아래에 적는다. 첫 질문을 보내면 대화가 생기고 왼쪽 목록에 남는다.`));
    return;
  }
  for (const m of c.messages) renderMessage(m);
  if (S.live.conversation === c.id) for (const event of S.live.events) renderLive(event);
  if (!log.children.length) log.appendChild(el("p", "placeholder", "아직 질문이 없다."));
  scrollDown();
}

// 대화 기록의 메시지 하나(conversations.py의 꼴)를 그린다.
function renderMessage(m) {
  if (m.role === "user") return userMessage(m.text, m.files);
  if (m.role === "preamble") return preambleNote(m);
  if (m.role === "note") return add(m.error ? "note error" : "note", m.text);
  if (m.role !== "agent") return;
  add("agent", m.text || "(답이 비어 있다)");
  const summary = [m.stopLabel, `엔진 ${m.engine}`, m.usage].filter(Boolean).join(" · ");
  const lines = [...(m.tools || []).map((t) => "도구 · " + t), ...(m.refused || []).map((t) => "거절 · " + t),
                 ...(m.notices || []).map((t) => "플랫폼 · " + t)];
  if (!lines.length) return add("note", summary);
  const details = el("details", "msg note");
  const counts = `쓴 도구 ${(m.tools || []).length}개` + ((m.refused || []).length ? ` · 거절 ${m.refused.length}개` : "");
  details.append(el("summary", "", `${summary} · ${counts}`), el("pre", "", lines.join("\n")));
  $("log").appendChild(details);
}

function renderComposer() {
  const who = S.convData || S.draft;
  const other = busy() && S.run.conversation !== S.conv;
  $("send").disabled = !who || busy() || S.attached.some((f) => f.status === "uploading");
  const note = !who ? (S.conv ? "" : "에이전트가 없다. 에이전트 메뉴에서 만든다.")
    : other ? "다른 대화에서 답을 쓰는 중이다. 그 답이 끝나면 보낼 수 있다." : "";
  $("composer-note").textContent = note;
  $("composer-note").hidden = !note;
}

$("new-chat").onclick = () => {
  const from = S.convData || S.draft;
  newDraft(from && from.agent, from && from.engine);
  renderChat();
  $("text").focus();
};

// ---- 에이전트: 고르기, 엔진 고르기, 엔진 로그인, 새 대화, 만들기, 고치기 ----

function skillsText(skills) {
  if (skills === null) return "모든 스킬";
  return skills.length ? skills.join(", ") : "스킬 없음";
}

function loginBadge(e) {
  if (!e.installed) return ["설치 안 됨", "need"];
  if (e.loggedIn === true) return ["로그인됨", "ok"];
  if (e.loggedIn === false) return ["로그인 필요", "need"];
  return ["알 수 없음", ""];
}

function renderAgentList() {
  const list = $("agent-list");
  list.innerHTML = "";
  for (const a of S.agents) {
    const li = el("li");
    li.classList.toggle("selected", a.name === S.selected.agents && !S.editing);
    const name = el("div", "name");
    name.append(el("span", "", a.name));
    if (a.name === S.run.agent) name.append(el("span", "badge on", "연결됨"));
    li.append(name, el("div", "meta", a.description || "설명 없음"),
              el("div", "meta", `기본 엔진 ${a.engine} · ${skillsText(a.skills)}`));
    li.onclick = () => { S.selected.agents = a.name; S.editing = null; render(); };
    list.appendChild(li);
  }
  if (!S.agents.length) list.appendChild(el("li", "empty", "에이전트가 없다. \"+ 새 에이전트\"로 만든다."));
}

function renderAgentDetail() {
  const box = $("agent-detail");
  box.innerHTML = "";
  if (S.editing) return agentForm(box);
  const a = S.agents.find((x) => x.name === S.selected.agents);
  if (!a) { box.appendChild(el("p", "placeholder", "왼쪽에서 에이전트를 고른다.")); return; }

  // 지금 고른 대화가 이 에이전트의 대화이면, 그 대화의 엔진을 바꿔 이어 갈 수 있다.
  const conv = S.convData && S.convData.agent === a.name && S.convData.messages.length ? S.convData : null;
  const head = el("div", "name");
  head.append(el("h2", "", a.name));
  box.append(head, el("p", "lead", a.description || "설명 없음"));
  if (conv) box.append(el("p", "muted", `지금 대화 "${conv.title || "제목 없음"}"는 엔진 ${conv.engine}로 돈다.`));

  // 엔진 고르기: 엔진을 바꿔도 역할, 스킬, 허락 규칙, 대화 기록은 플랫폼이 그대로 보낸다.
  const chosen = S.chosenEngine[a.name] || (conv && conv.engine) || a.engine;
  box.append(el("h3", "", "돌릴 엔진"));
  box.append(el("p", "muted small", "엔진을 바꿔도 역할, 스킬, 허락 규칙, 대화 기록은 플랫폼이 그대로 보낸다."));
  const engines = el("div", "engines");
  for (const e of S.engines) {
    const row = el("div", "engine" + (e.name === chosen ? " chosen" : ""));
    const label = el("label");
    const radio = el("input");
    radio.type = "radio"; radio.name = "engine"; radio.checked = e.name === chosen;
    radio.onchange = () => { S.chosenEngine[a.name] = e.name; renderAgentDetail(); };
    label.append(radio, el("span", "", e.name + (e.name === a.engine ? " (기본)" : "")));
    const side = el("div", "side");
    const [text, tone] = loginBadge(e);
    side.append(el("span", "badge " + tone, text));
    if (e.installed && e.loginMode !== "terminal" && e.loggedIn !== true) {
      side.append(button("로그인", () => api("POST", `/api/login/${e.name}`).catch(report)));
    } else if (e.installed && e.canLogout && e.loggedIn === true) {
      side.append(button("로그아웃", () => api("POST", `/api/logout/${e.name}`).catch(report), "link"));
    } else if (e.installed && e.loginMode === "terminal" && e.loggedIn !== true) {
      side.append(el("code", "", e.loginCommand));
    }
    row.append(label, side);
    engines.append(row);
    const login = S.login[e.name];
    if (login) engines.append(loginBox(e.name, login));
  }
  box.append(engines);

  const engine = S.engines.find((x) => x.name === chosen);
  const ready = engine && engine.installed && engine.loggedIn !== false;
  const actions = el("div", "actions");
  const start = button(`${chosen}로 새 대화`, () => { newDraft(a.name, chosen); renderChat(); showView("chat"); });
  start.disabled = !ready;
  actions.append(start);
  if (conv && chosen !== conv.engine) {
    const move = button(`지금 대화를 ${chosen}로 이어 가기`, async () => {
      try {
        S.convData = await api("PATCH", `/api/conversations/${conv.id}`, { engine: chosen });
        await loadConversations();
        renderChat();
        showView("chat");
      } catch (e) { report(e); }
    }, "ghost");
    move.disabled = !ready;
    actions.append(move);
  } else if (conv) {
    actions.append(button("지금 대화로 돌아가기", () => showView("chat"), "ghost"));
  }
  actions.append(button("고치기", () => { S.editing = { mode: "edit", name: a.name }; render(); }, "ghost"));
  box.append(actions);
  if (!ready) box.append(el("p", "muted small", "고른 엔진에 먼저 로그인한다."));
  if (conv && chosen !== conv.engine) {
    box.append(el("p", "muted small", "이어 가면 다음 질문을 보낼 때 플랫폼이 지금까지의 대화를 새 엔진에 넘긴다."));
  }

  box.append(el("h3", "", "역할"), el("pre", "prose", a.role || "(비어 있다. 설명이 대신 간다)"));
  box.append(el("h3", "", "쓸 스킬"));
  const chips = el("div", "chips");
  const names = a.skills === null ? S.skills.map((s) => s.name) : a.skills;
  for (const n of names) chips.append(el("span", "badge ok", n));
  if (!names.length) chips.append(el("span", "badge", "없음"));
  box.append(chips);
}

// 로그인 상자: 주소(와 기기 코드)를 보여 주고, 코드 방식이면 받은 코드를 붙여 넣는다.
function loginBox(engine, event) {
  const box = el("div", "login-box");
  const cancel = () => button("취소", () => api("DELETE", `/api/login/${engine}`).catch(report), "ghost");
  box.append(el("b", "", `${engine} 로그인`));
  switch (event.state) {
    case "started":
      box.append(el("div", "", "로그인 주소를 받는 중…"), cancel());
      break;
    case "waiting": {
      if (event.url) {
        const link = el("a", "", event.url);
        link.href = event.url; link.target = "_blank";
        box.append(el("div", "", "1. 이 주소를 열고 구독한 계정으로 로그인한다."), link);
      }
      if (event.userCode) {
        box.append(el("div", "", "2. 주소의 화면에 이 코드를 넣는다."), el("div", "code", event.userCode),
                   el("div", "muted small", "다 되면 이 상자가 저절로 바뀐다."));
      }
      if (event.mode === "code") {
        box.append(el("div", "", "2. 로그인한 뒤 화면에 나온 코드를 복사해 붙여 넣는다."));
        const input = el("input");
        input.placeholder = "코드 붙여 넣기";
        const row = el("div", "row");
        row.append(input, button("보내기", () => api("POST", `/api/login/${engine}/code`, { code: input.value }).catch(report)));
        box.append(row);
      }
      box.append(cancel());
      break;
    }
    case "checking": box.append(el("div", "", "코드를 확인하는 중…")); break;
    case "done": box.append(el("div", "", "로그인했다. 이제 이 엔진으로 대화할 수 있다.")); break;
    case "logged_out": box.append(el("div", "", "로그아웃했다.")); break;
    case "cancelled": box.append(el("div", "", "로그인을 멈췄다.")); break;
    default: box.append(el("div", "", `로그인하지 못했다. ${event.message || ""}`));
  }
  return box;
}

// 에이전트 만들기와 고치기. 저장하면 custom/agents/<이름>.md가 생기거나 바뀐다.
function agentForm(box) {
  const existing = S.editing.mode === "edit" ? S.agents.find((x) => x.name === S.editing.name) : null;
  box.append(el("h2", "", existing ? `에이전트 고치기 · ${existing.name}` : "새 에이전트"));
  box.append(el("p", "muted", existing ? `custom/agents/${existing.name}.md를 고친다.` : "custom/agents/<이름>.md가 생긴다."));
  const grid = el("div", "form-grid");
  const field = (label, input) => { grid.append(el("label", "", label), input); return input; };

  const name = field("이름", el("input"));
  name.placeholder = "예: 마감_정리 (공백 대신 밑줄)";
  const engine = field("기본 엔진", el("select"));
  for (const e of S.engines) { const o = el("option", "", e.name); o.value = e.name; engine.appendChild(o); }
  const description = field("설명", el("input"));
  description.placeholder = "목록에 보일 한 줄";
  const checks = field("스킬", el("div", "checks"));
  const all = el("input"); all.type = "checkbox";
  const allLabel = el("label"); allLabel.append(all, " 모두");
  checks.appendChild(allLabel);
  const boxes = S.skills.map((s) => {
    const b = el("input"); b.type = "checkbox"; b.value = s.name;
    const l = el("label"); l.append(b, " " + s.name);
    checks.appendChild(l);
    return b;
  });
  all.onchange = () => boxes.forEach((b) => { b.disabled = all.checked; });
  const role = field("역할", el("textarea"));
  role.rows = 8;
  role.placeholder = "이 에이전트가 맡는 일과 지킬 규칙. 플랫폼 안내의 \"너의 역할\"에 들어간다.";

  if (existing) {
    name.value = existing.name; name.disabled = true;
    engine.value = existing.engine; description.value = existing.description; role.value = existing.role;
    all.checked = existing.skills === null;
    boxes.forEach((b) => { b.checked = (existing.skills || []).includes(b.value); });
  } else {
    all.checked = true;
    engine.value = (S.engines[0] || {}).name || "";
  }
  all.onchange();
  box.append(grid);

  const actions = el("div", "actions");
  actions.append(button(existing ? "저장" : "만들기", async () => {
    const body = {
      name: name.value.trim(), engine: engine.value, description: description.value, role: role.value,
      skills: all.checked ? null : boxes.filter((b) => b.checked).map((b) => b.value),
    };
    try {
      if (existing) await api("PUT", `/api/agents/${encodeURIComponent(existing.name)}`, body);
      else await api("POST", "/api/agents", body);
      S.editing = null;
      S.selected.agents = body.name;
      await refresh(loadAgents);
    } catch (e) { alertBar(e.message); }
  }), button("취소", () => { S.editing = null; render(); }, "ghost"));
  box.append(actions);
  (existing ? description : name).focus();
}

$("new-agent").onclick = () => { S.editing = { mode: "new" }; showView("agents"); };

// ---- 스킬 ----

function renderSkillList() {
  const list = $("skill-list");
  list.innerHTML = "";
  for (const s of S.skills) {
    const li = el("li");
    li.classList.toggle("selected", s.name === S.selected.skills);
    li.append(el("div", "name", s.name), el("div", "meta", s.description));
    li.onclick = () => { S.selected.skills = s.name; render(); };
    list.appendChild(li);
  }
  if (!S.skills.length) list.appendChild(el("li", "empty", "스킬이 없다."));
}

async function renderSkillDetail() {
  const box = $("skill-detail");
  const name = S.selected.skills || (S.skills[0] && S.skills[0].name);
  if (!name) { box.innerHTML = ""; box.appendChild(el("p", "placeholder", "왼쪽에서 스킬을 고른다.")); return; }
  S.selected.skills = name;
  let skill;
  try { skill = await api("GET", `/api/skills/${encodeURIComponent(name)}`); } catch (e) { return report(e); }
  if (S.view !== "skills" || S.selected.skills !== name) return;
  box.innerHTML = "";
  box.append(el("h2", "", skill.name), el("p", "lead", skill.description));
  box.append(el("h3", "", "이 스킬을 쓰는 에이전트"));
  const chips = el("div", "chips");
  for (const a of skill.agents) chips.append(el("span", "badge ok", a));
  if (!skill.agents.length) chips.append(el("span", "badge", "없음"));
  box.append(chips);
  if (skill.example) {
    box.append(el("h3", "", "해 볼 요청"), el("pre", "prose", skill.example));
    const actions = el("div", "actions");
    actions.append(button("대화 입력칸에 넣기", () => { $("text").value = skill.example; showView("chat"); }));
    box.append(actions);
  }
  box.append(el("h3", "", skill.path), el("pre", "", skill.text));
}

// ---- 일 ----

function renderTaskList() {
  const list = $("task-list");
  list.innerHTML = "";
  for (const t of S.tasks) {
    const li = el("li");
    li.classList.toggle("selected", t.name === S.selected.tasks);
    li.append(el("div", "name", t.name),
              el("div", "meta", `${t.agent}${t.engine ? " · " + t.engine : ""} · ${t.time ? "매일 " + t.time : "직접 실행"}`));
    li.onclick = () => { S.selected.tasks = t.name; render(); };
    list.appendChild(li);
  }
  if (!S.tasks.length) list.appendChild(el("li", "empty", "일이 없다. tasks/에 파일을 더한다."));
}

function renderTaskDetail() {
  const box = $("task-detail");
  box.innerHTML = "";
  const t = S.tasks.find((x) => x.name === S.selected.tasks) || S.tasks[0];
  if (!t) { box.appendChild(el("p", "placeholder", "왼쪽에서 일을 고른다.")); return; }
  S.selected.tasks = t.name;
  const agent = S.agents.find((a) => a.name === t.agent);
  box.append(el("h2", "", t.name));
  box.append(el("p", "lead", `에이전트 ${t.agent} · 엔진 ${t.engine || (agent ? agent.engine + " (에이전트의 기본)" : "?")} · ${t.time ? "매일 " + t.time : "직접 실행할 때만"}`));
  box.append(el("p", "muted", t.lastRun ? `마지막 실행 ${t.lastRun}` : "이번에 켠 뒤로 아직 돌리지 않았다."));
  const actions = el("div", "actions");
  actions.append(button("지금 실행", () => api("POST", `/api/tasks/${encodeURIComponent(t.name)}/run`)
    .then(() => alertBar(`일 '${t.name}'을 시작했다. 끝나면 결과함에 파일이 생긴다.`)).catch(report)));
  box.append(actions);
  box.append(el("h3", "", "맡길 내용"), el("pre", "prose", t.prompt));
  box.append(el("h3", "", "이 일의 결과"));
  const results = S.files.filter((f) => f.name.endsWith(`_${t.name}.md`)).slice(0, 10);
  const ul = el("ul", "pick-list plain");
  for (const f of results) {
    const li = el("li", "", f.name);
    li.onclick = () => { S.selected.outbox = f.name; showView("outbox"); };
    ul.appendChild(li);
  }
  if (!results.length) ul.appendChild(el("li", "empty", "아직 없다."));
  box.append(ul);
}

$("reload-tasks").onclick = () => refresh(loadTasks, loadOutbox);

// ---- 결과함 ----

function renderOutboxList() {
  const list = $("outbox-list");
  list.innerHTML = "";
  for (const f of S.files.slice(0, 100)) {
    const li = el("li");
    li.classList.toggle("selected", f.name === S.selected.outbox);
    li.append(el("div", "name", f.name), el("div", "meta", f.type));
    li.onclick = () => { S.selected.outbox = f.name; render(); };
    list.appendChild(li);
  }
  if (!S.files.length) list.appendChild(el("li", "empty", "아직 없다."));
}

async function renderOutboxDetail() {
  const box = $("outbox-detail");
  const f = S.files.find((x) => x.name === S.selected.outbox) || S.files[0];
  if (!f) { box.innerHTML = ""; box.appendChild(el("p", "placeholder", "결과 파일이 아직 없다.")); return; }
  S.selected.outbox = f.name;
  const head = () => {
    box.innerHTML = "";
    const link = el("a", "", "새 탭에서 열기 ↗");
    link.href = f.url; link.target = "_blank";
    const row = el("div", "detail-head");
    row.append(el("h2", "", f.name), link);
    box.append(row);
  };
  if (f.type === "html") {
    head();
    const frame = el("iframe", "viewer");
    frame.src = f.url;
    frame.setAttribute("sandbox", "");
    box.append(frame);
    return;
  }
  let file;
  try { file = await api("GET", `/api/outbox/${encodeURIComponent(f.name)}`); } catch (e) { return report(e); }
  if (S.view !== "outbox" || S.selected.outbox !== f.name) return;
  head();
  box.append(el("pre", "", file.text));
}

$("reload-outbox").onclick = () => refresh(loadOutbox);

// ---- 대화 기록 칸 ----

function scrollDown() { $("log").scrollTop = $("log").scrollHeight; }

function add(className, text) {
  for (const p of $("log").querySelectorAll(".placeholder")) p.remove();
  const div = el("div", "msg " + className, text);
  $("log").appendChild(div);
  scrollDown();
  return div;
}

function permissionCard(event) {
  const card = el("div", "card");
  const actions = el("div", "actions");
  for (const [label, allow] of [["허락", true], ["거절", false]]) {
    actions.appendChild(button(label, () => api("POST", `/api/permissions/${event.id}`, { allow }).catch(report),
                               allow ? "" : "ghost"));
  }
  card.append(el("b", "", `허락 요청 · ${event.label}`), el("div", "detail-text", event.detail || ""), actions);
  $("log").appendChild(card);
  scrollDown();
  cards[event.id] = card;
}

function preambleNote(item) {
  const details = el("details", "msg note");
  const carried = item.history ? ` · 앞의 대화 ${item.history}개를 넣어 보냄` : "";
  details.append(el("summary", "", `플랫폼이 보낸 안내 · 엔진 ${item.engine}${carried} (질문 앞에 붙였다 · 업무, 역할, 스킬)`),
                 el("pre", "", item.text));
  $("log").appendChild(details);
  scrollDown();
}

// 답을 쓰는 중인 차례의 사건. 대화 기록에는 차례가 끝나야 남으므로 그동안은 사건으로 그린다.
const LIVE = ["text", "tool", "permission", "permission_result", "rule", "rule_error", "notice"];

function renderLive(event) {
  switch (event.type) {
    case "text":
      if (!answer) answer = add("agent", "");
      answer.textContent += event.text;
      scrollDown();
      break;
    case "tool":
      add("note", `도구 · ${event.label} · ${firstLine(event.detail)}`);
      answer = null;
      break;
    case "permission":
      permissionCard(event);
      answer = null;
      break;
    case "permission_result": {
      const card = cards[event.id];
      if (card) card.querySelector(".actions").textContent = event.timeout ? "답이 없어 거절함" : event.allow ? "허락함" : "거절함";
      break;
    }
    case "rule":
      add("note", `규칙(custom/rules.py) · ${event.allow ? "허락" : "거절"} · ${event.label} · ${firstLine(event.detail)}`);
      answer = null;
      break;
    case "rule_error":
      add("note error", event.message);
      break;
    case "notice":
      add("note", `플랫폼 · ${event.text}`);
      break;
  }
}

// ---- 파일 올리기: + 단추, 끌어 놓기, 붙여 넣기 ----
// 고르면 바로 /api/uploads로 올린다(workspace/inbox/). 보낼 때 그 경로를 질문에 붙인다.
// 큰 사진은 올리기 전에 화면에서 줄인다(긴 변 2000px). 엔진은 큰 그림을 받지 않는다.

const IMAGE = /\.(png|jpe?g|gif|webp)$/i;          // 엔진에 그림으로 가는 사진
const SHOWABLE = /^image\/(png|jpeg|gif|webp)$/;    // 화면에서 미리 볼 수 있는 사진
const MAX_SIDE = 2000;
const SHRINK_BYTES = 1500 * 1000;
const size = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1e3))}KB`);

async function shrink(file) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return { file };
  let bitmap;
  try { bitmap = await createImageBitmap(file); } catch (e) { return { file }; }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  if (scale === 1 && file.size <= SHRINK_BYTES) return { file };
  const canvas = el("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";                            // 투명한 곳은 흰 바탕으로
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
  if (!blob || blob.size >= file.size) return { file };
  const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
  return { file: new File([blob], name, { type: "image/jpeg" }), note: `줄여서 올림 ${size(file.size)} → ${size(blob.size)}` };
}

async function addFiles(list) {
  for (const original of list) {
    const item = { key: Math.random().toString(36).slice(2), name: original.name, size: original.size, status: "uploading" };
    if (SHOWABLE.test(original.type)) item.preview = URL.createObjectURL(original);
    S.attached.push(item);
    renderTray(); renderComposer();
    try {
      const { file, note } = await shrink(original);
      const res = await fetch(`/api/uploads?name=${encodeURIComponent(file.name)}`,
                              { method: "POST", body: file, headers: { "Content-Type": "application/octet-stream" } });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.statusText);
      const warn = /^image\/(heic|heif)$/.test(original.type) ? "HEIC 사진은 엔진이 그림으로 받지 못한다. JPG로 바꿔 올린다" : "";
      Object.assign(item, { status: "done", path: data.path, name: data.name, size: data.size, note: warn || note });
    } catch (e) {
      Object.assign(item, { status: "error", note: e.message });
    }
    renderTray(); renderComposer();
  }
}

function renderTray() {
  const tray = $("tray");
  tray.innerHTML = "";
  tray.hidden = !S.attached.length;
  for (const item of S.attached) {
    const chip = el("div", "file-chip" + (item.status === "error" ? " error" : ""));
    if (item.preview) { const img = el("img"); img.src = item.preview; img.alt = ""; chip.append(img); }
    else chip.append(el("span", "ext", (item.name.includes(".") ? item.name.split(".").pop() : "파일").slice(0, 4).toUpperCase()));
    const state = item.status === "uploading" ? "올리는 중…" : item.status === "error" ? item.note
      : [size(item.size), item.note].filter(Boolean).join(" · ");
    const info = el("div", "info");
    info.append(el("b", "", item.name), el("span", "", state));
    const remove = button("×", () => removeAttached(item.key));
    remove.title = "빼기";
    chip.append(info, remove);
    tray.appendChild(chip);
  }
}

function removeAttached(key) {
  for (const item of S.attached) if (item.key === key && item.preview) URL.revokeObjectURL(item.preview);
  S.attached = S.attached.filter((item) => item.key !== key);
  renderTray(); renderComposer();
}

function clearAttached() {
  for (const item of S.attached) if (item.preview) URL.revokeObjectURL(item.preview);
  S.attached = [];
  renderTray(); renderComposer();
}

// 사람의 질문 칸. 올린 파일이 있으면 사진은 작게 보이고, 다른 파일은 이름이 보인다. 누르면 새 탭에서 열린다.
function userMessage(text, files) {
  const div = add("user", text || "");
  if (!files || !files.length) return div;
  const box = el("div", "files");
  for (const path of files) {
    const name = path.split("/").pop();
    const link = el("a", IMAGE.test(name) ? "" : "file", IMAGE.test(name) ? undefined : name);
    link.href = "/" + path.split("/").map(encodeURIComponent).join("/");
    link.target = "_blank";
    link.title = path;
    if (IMAGE.test(name)) {
      const img = el("img");
      img.src = link.href; img.alt = name;
      img.onload = scrollDown;
      link.append(img);
    }
    box.appendChild(link);
  }
  div.appendChild(box);
  return div;
}

$("attach").onclick = () => $("file-input").click();
$("file-input").onchange = () => { addFiles([...$("file-input").files]); $("file-input").value = ""; };
$("text").addEventListener("paste", (event) => {
  const files = [...((event.clipboardData && event.clipboardData.files) || [])];
  if (files.length) { event.preventDefault(); addFiles(files); }   // 글을 붙여 넣을 때는 그대로 둔다
});
const chatBox = document.querySelector(".chat");
chatBox.addEventListener("dragover", (event) => {
  if (![...event.dataTransfer.types].includes("Files")) return;
  event.preventDefault();
  chatBox.classList.add("dragging");
});
chatBox.addEventListener("dragleave", (event) => {
  if (!chatBox.contains(event.relatedTarget)) chatBox.classList.remove("dragging");
});
chatBox.addEventListener("drop", (event) => {
  event.preventDefault();
  chatBox.classList.remove("dragging");
  addFiles([...event.dataTransfer.files]);
});

// ---- 보내기 ----

$("composer").onsubmit = async (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  const files = S.attached.filter((f) => f.status === "done").map((f) => f.path);
  if ((!text && !files.length) || busy() || S.attached.some((f) => f.status === "uploading")) return;
  try {
    if (!S.conv) {
      if (!S.draft) return;
      const created = await api("POST", "/api/conversations", S.draft);   // 첫 질문을 보낼 때 대화를 만든다
      S.conv = created.id; S.convData = created; S.draft = null;
      renderChat();
    }
    await api("POST", `/api/conversations/${S.conv}/prompt`, { text, files });
    $("text").value = "";
    clearAttached();
  } catch (e) { report(e); }
};

$("text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
});

// 차례가 끝나면 서버의 대화 기록을 다시 읽는다. silent이면 지금 그린 화면은 그대로 둔다.
async function finishTurn(id, silent) {
  if (S.live.conversation === id) S.live = { conversation: null, events: [] };
  refresh(loadConversations);
  if (S.conv !== id) return;
  let data;
  try { data = await api("GET", `/api/conversations/${id}`); } catch (e) { return; }
  if (S.conv !== id) return;
  S.convData = data;
  if (!silent) renderLog();
  renderChatHead();
}

// ---- 서버의 사건을 화면에 옮긴다 ----

function handle(event) {
  const shown = S.convData && event.conversation === S.convData.id;   // 지금 보고 있는 대화의 사건인가
  if (LIVE.includes(event.type)) {
    if (S.live.conversation !== event.conversation) S.live = { conversation: event.conversation, events: [] };
    S.live.events.push(event);
    if (event.type === "permission") S.pending.add(event.id);
    if (event.type === "permission_result") S.pending.delete(event.id);
    updateBanner();
    if (shown) renderLive(event);
    return;
  }
  switch (event.type) {
    case "user":
      S.live = { conversation: event.conversation, events: [] };
      if (shown) { userMessage(event.text, event.files); answer = null; }
      refresh(loadConversations);
      break;
    case "preamble":
      if (shown) preambleNote(event);
      break;
    case "status":
      if (event.state === "error") finishTurn(event.conversation, false);
      break;
    case "done":
      if (shown) add("note", `${event.stopLabel} · ${event.usage}`);
      answer = null;
      finishTurn(event.conversation, true);
      refresh(loadOutbox);
      break;
    case "task":
      if (event.state === "done") {
        alertBar(`일 '${event.name}'이 끝났다. 결과함에 ${event.file}이 생겼다.`
                 + (event.deliveryError ? ` 보내기 오류: ${event.deliveryError}` : ""));
      }
      refresh(loadTasks, loadOutbox);
      break;
    case "login":
      S.login[event.engine] = event;
      if (["done", "logged_out", "failed", "cancelled"].includes(event.state)) refresh(loadEngines);
      else render();
      break;
  }
}

async function poll() {
  while (true) {
    try {
      const data = await api("GET", `/api/events?after=${last}`);
      if (data.epoch !== epoch) { await start(); continue; }   // 서버를 다시 켰다. 처음부터 다시 읽는다
      for (const event of data.events) handle(event);
      last = data.last;
      updateStatus(data);
    } catch (e) {
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

// ---- 시작 ----

// 서버의 지금 상태를 읽는다. 답을 쓰는 중인 차례가 있으면 그 사건부터 이어 그린다.
async function start() {
  const state = await api("GET", "/api/state");
  last = state.last;
  epoch = state.epoch;
  S.live = { conversation: state.conversation, events: state.live.filter((e) => LIVE.includes(e.type)) };
  S.pending = new Set();
  for (const e of S.live.events) {
    if (e.type === "permission") S.pending.add(e.id);
    if (e.type === "permission_result") S.pending.delete(e.id);
  }
  await Promise.all([loadEngines(), loadSkills(), loadTasks(), loadOutbox(), loadAgents(), loadConversations()]);
  updateStatus(state);
  const running = (state.state === "starting" || state.state === "busy") && state.conversation;
  const keep = S.conv && S.conversations.some((c) => c.id === S.conv) ? S.conv : null;
  const first = keep || running || (S.conversations[0] && S.conversations[0].id);
  if (first) await selectConversation(first);
  else { newDraft(); renderChat(); }
  showView(location.hash.slice(1) || "chat");
}

loadBrand().catch(() => {});
start().catch(report).finally(poll);
