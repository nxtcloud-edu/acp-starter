// 내 에이전트 플랫폼의 화면 코드. dashboard.py의 JSON API를 부른다.
// 새 기능은 먼저 dashboard.py에 API를 더하고, 여기서 그 API를 부르게 만든다.
// 화면은 엔진 이름을 따로 다루지 않는다. 엔진 목록은 /api/engines에서 받는다.
//
// 왼쪽 메뉴(대화, 에이전트, 스킬, 일, 결과함)를 고르면 오른쪽에 그 화면이 나온다.
// 대화를 뺀 화면은 모두 "목록 + 상세" 꼴이다. 목록에서 고르면 상세가 바뀐다.

const $ = (id) => document.getElementById(id);

// 화면의 상태. 서버에서 받은 것과 화면에서 고른 것을 한곳에 둔다.
const S = {
  view: "chat",
  engines: [], agents: [], skills: [], tasks: [], files: [],
  current: null, engine: null, state: "idle",
  selected: { agents: null, skills: null, tasks: null, outbox: null },
  chosenEngine: {},      // 에이전트 이름 → 상세에서 고른 엔진
  login: {},             // 엔진 이름 → 마지막 로그인 사건
  editing: null,         // 에이전트 양식: null, {mode: "new"}, {mode: "edit", name}
  pending: new Set(),    // 답을 기다리는 허락 요청 번호
};
let last = 0;            // 마지막으로 받은 사건 번호
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
const report = (e) => { add("note error", e.message); if (S.view !== "chat") alertBar(e.message); };

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
$("status-pill").onclick = () => showView("chat");

function render() {
  if (S.view === "agents") { renderAgentList(); renderAgentDetail(); }
  if (S.view === "skills") { renderSkillList(); renderSkillDetail(); }
  if (S.view === "tasks") { renderTaskList(); renderTaskDetail(); }
  if (S.view === "outbox") { renderOutboxList(); renderOutboxDetail(); }
}

// 허락을 기다리는 요청이 있으면 대화 메뉴에 숫자를, 다른 화면에서는 띠를 보인다.
function updateBanner() {
  const n = S.pending.size;
  $("badge-chat").hidden = n === 0;
  $("badge-chat").textContent = n;
  const bar = $("banner");
  if (n > 0 && S.view !== "chat") {
    bar.textContent = `허락을 기다리는 요청이 ${n}건 있다. 눌러서 대화로 간다.`;
    bar.dataset.kind = "permission";
    bar.hidden = false;
    bar.onclick = () => showView("chat");
  } else if (bar.dataset.kind === "permission") {
    bar.hidden = true;            // 대화 화면에서는 카드가 보이므로 띠를 거둔다
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

// ---- 연결 상태 ----

const STATE = { idle: "연결하지 않음", starting: "연결하는 중", ready: "준비됨", busy: "답을 쓰는 중", error: "오류" };

function updateStatus(state, agent, engine) {
  S.state = state || S.state;
  if (agent !== undefined) { S.current = agent; S.engine = engine; }
  const label = STATE[S.state] || S.state;
  $("status-pill").textContent = S.current ? `${S.current} · ${S.engine} · ${label}` : label;
  $("chat-who").textContent = S.current
    ? `${S.current} 에이전트 · 엔진 ${S.engine} · ${label}`
    : "연결한 에이전트가 없다. 에이전트 메뉴에서 에이전트와 엔진을 골라 연결한다.";
}

// ---- 데이터 읽기 ----

async function loadEngines() { S.engines = (await api("GET", "/api/engines")).engines; }
async function loadSkills() { S.skills = (await api("GET", "/api/skills")).skills; }
async function loadTasks() { S.tasks = (await api("GET", "/api/tasks")).tasks; }
async function loadOutbox() { S.files = (await api("GET", "/api/outbox")).files; }
async function loadAgents() {
  const data = await api("GET", "/api/agents");
  S.agents = data.agents;
  updateStatus(data.state, data.current, data.engine);
  if (!S.selected.agents && S.agents.length) S.selected.agents = data.current || S.agents[0].name;
}
const refresh = (...loaders) => Promise.all(loaders.map((f) => f())).then(render).catch(report);

// ---- 에이전트: 고르기, 엔진 고르기, 엔진 로그인, 연결, 만들기, 고치기 ----

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
    if (a.name === S.current) name.append(el("span", "badge on", "연결됨"));
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

  const head = el("div", "name");
  const title = el("h2", "", a.name);
  head.append(title);
  box.append(head, el("p", "lead", a.description || "설명 없음"));
  if (a.name === S.current) box.append(el("p", "muted", `지금 엔진 ${S.engine}로 연결되어 있다 · ${STATE[S.state] || S.state}`));

  // 엔진 고르기: 엔진을 바꿔도 역할, 스킬, 허락 규칙, 앞의 대화는 그대로 간다.
  const chosen = S.chosenEngine[a.name] || (a.name === S.current && S.engine) || a.engine;
  box.append(el("h3", "", "돌릴 엔진"));
  box.append(el("p", "muted small", "엔진을 바꿔도 역할, 스킬, 허락 규칙, 앞의 대화는 플랫폼이 그대로 보낸다."));
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
  const go = button(a.name === S.current && chosen === S.engine ? "대화로 가기" : `${chosen}로 연결하고 대화하기`, async () => {
    if (a.name === S.current && chosen === S.engine && S.state !== "error") return showView("chat");
    try { await api("POST", "/api/session", { agent: a.name, engine: chosen }); showView("chat"); }
    catch (e) { report(e); }
  });
  go.disabled = !ready;
  actions.append(go, button("고치기", () => { S.editing = { mode: "edit", name: a.name }; render(); }, "ghost"));
  box.append(actions);
  if (!ready) box.append(el("p", "muted small", "고른 엔진에 먼저 로그인한다."));

  if (a.history) {
    box.append(el("h3", "", "앞의 대화"));
    box.append(el("p", "muted", `플랫폼이 이 에이전트와의 대화 ${a.history}개를 가지고 있다. 연결하면 엔진이 달라도 이어서 보낸다.`));
    box.append(button("앞의 대화를 지우고 새로 연결", async () => {
      try { await api("POST", "/api/session", { agent: a.name, engine: chosen, fresh: true }); showView("chat"); }
      catch (e) { report(e); }
    }, "ghost"));
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
    case "done": box.append(el("div", "", "로그인했다. 이제 이 엔진으로 연결할 수 있다.")); break;
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
$("change-agent").onclick = () => showView("agents");

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

// ---- 대화 ----

function scrollDown() { $("log").scrollTop = $("log").scrollHeight; }

function add(className, text) {
  const div = el("div", "msg " + className, text);
  $("log").appendChild(div);
  scrollDown();
  return div;
}

$("composer").onsubmit = async (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (!text) return;
  try { await api("POST", "/api/prompt", { text }); $("text").value = ""; }
  catch (e) { report(e); }
};

$("text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
});

// 새 대화: 지금 에이전트의 앞의 대화를 지우고 같은 엔진으로 다시 연결한다.
$("fresh").onclick = async () => {
  if (!S.current) { showView("agents"); return; }
  try { await api("POST", "/api/session", { agent: S.current, engine: S.engine, fresh: true }); }
  catch (e) { report(e); }
};

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

function preambleNote(event) {
  const details = el("details", "msg note");
  const carried = event.history ? ` · 앞의 대화 ${event.history}개를 이어 보냄` : "";
  details.append(el("summary", "", `플랫폼이 보낸 안내 · ${event.agent}${carried} (첫 질문 앞에 붙는다 · 업무, 역할, 스킬)`),
                 el("pre", "", event.text));
  $("log").appendChild(details);
  scrollDown();
}

// ---- 서버의 사건을 화면에 옮긴다 ----

function handle(event) {
  switch (event.type) {
    case "status":
      updateStatus(event.state, event.agent, event.engine);
      if (event.state === "ready") add("note", `${event.agent}에 연결됨 · 엔진 ${event.engine}`);
      if (event.state === "error") report(new Error(event.message || "오류"));
      if (event.state === "starting" || event.state === "ready") refresh(loadAgents);
      break;
    case "preamble":
      preambleNote(event);
      break;
    case "user":
      add("user", event.text);
      answer = null;
      break;
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
      S.pending.add(event.id);
      updateBanner();
      answer = null;
      break;
    case "permission_result": {
      const card = cards[event.id];
      if (card) card.querySelector(".actions").textContent = event.timeout ? "답이 없어 거절함" : event.allow ? "허락함" : "거절함";
      S.pending.delete(event.id);
      updateBanner();
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
    case "done":
      add("note", `${event.stopLabel} · ${event.usage}`);
      answer = null;
      refresh(loadOutbox, loadAgents);
      break;
    case "task":
      if (event.state === "running") add("note", `일 '${event.name}' 실행 시작 (${event.agent}${event.engine ? " · " + event.engine : ""})`);
      else {
        add("note", `일 '${event.name}' 끝 → 결과함 ${event.file}`);
        if (event.deliveryError) add("note error", event.deliveryError);
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
      for (const event of data.events) handle(event);
      last = data.last;
      updateStatus(data.state, data.agent, data.engine);
    } catch (e) {
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

// ---- 시작 ----

loadBrand().catch(() => {});
Promise.all([loadEngines(), loadSkills(), loadTasks(), loadOutbox()])
  .then(loadAgents)
  .then(() => showView(location.hash.slice(1) || (S.current ? "chat" : "agents")))
  .catch(report);
add("note", "에이전트 메뉴에서 에이전트와 엔진을 골라 연결하면 여기서 대화한다.");
poll();
