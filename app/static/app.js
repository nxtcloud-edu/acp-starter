// 내 에이전트 플랫폼의 화면 코드. dashboard.py의 JSON API를 부른다.
// 새 기능은 먼저 dashboard.py에 API를 더하고, 여기서 그 API를 부르게 만든다.
// 화면은 엔진 이름을 따로 다루지 않는다. 엔진 목록은 /api/engines에서 받는다.

const $ = (id) => document.getElementById(id);
let last = 0;          // 마지막으로 받은 사건 번호
let answer = null;     // 지금 쓰는 중인 에이전트의 답 칸
const cards = {};      // 허락 요청 카드: 번호 → 칸
const loginCards = {}; // 로그인 카드: 엔진 이름 → 칸
let engineNames = [];  // /api/engines의 엔진 이름
let skillList = [];    // /api/skills의 스킬

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

function scrollDown() { $("log").scrollTop = $("log").scrollHeight; }

function add(className, text) {
  const div = el("div", "msg " + className, text);
  $("log").appendChild(div);
  scrollDown();
  return div;
}

function button(label, onclick, className) {
  const b = el("button", className || "", label);
  b.type = "button";
  b.onclick = onclick;
  return b;
}

const report = (e) => add("note error", e.message);
const firstLine = (text) => (text || "").split("\n")[0].slice(0, 120);

// ---- 이름과 색 (custom/brand.json) ----

async function loadBrand() {
  const brand = await api("GET", "/api/brand");
  document.title = brand.name;
  $("brand-name").textContent = brand.name;
  $("brand-tagline").textContent = brand.tagline || "";
  if (brand.accent) document.documentElement.style.setProperty("--accent", brand.accent);
}

// ---- 엔진과 로그인 ----

const STATE = { idle: "연결하지 않음", starting: "연결하는 중…", ready: "준비됨", busy: "답을 쓰는 중…", error: "오류" };

function loginBadge(e) {
  if (!e.installed) return ["설치 안 됨", "need"];
  if (e.loggedIn === true) return ["로그인됨", "ok"];
  if (e.loggedIn === false) return ["로그인 필요", "need"];
  return ["알 수 없음", ""];
}

async function loadEngines() {
  const data = await api("GET", "/api/engines");
  engineNames = data.engines.map((e) => e.name);
  $("engines").innerHTML = "";
  for (const e of data.engines) {
    const li = el("li", "agent");
    const [label, tone] = loginBadge(e);
    const info = el("div");
    info.append(el("span", "", e.name + " "), el("span", "badge " + tone, label));
    li.appendChild(info);
    if (e.installed && e.loginMode !== "terminal" && e.loggedIn !== true) {
      li.appendChild(button("로그인", () => api("POST", `/api/login/${e.name}`).catch(report)));
    } else if (e.installed && e.canLogout && e.loggedIn === true) {
      li.appendChild(button("로그아웃", () => api("POST", `/api/logout/${e.name}`).catch(report), "ghost"));
    } else if (e.installed && e.loginMode === "terminal" && e.loggedIn !== true) {
      li.appendChild(el("code", "", e.loginCommand));
    }
    $("engines").appendChild(li);
  }
}

$("reload-engines").onclick = () => loadEngines().catch(report);

// 로그인 카드: 주소(와 기기 코드)를 보여 주고, 코드 방식이면 받은 코드를 붙여 넣는다.
function loginCard(event) {
  let card = loginCards[event.engine];
  if (!card) {
    card = el("div", "card");
    card.append(el("b", "", `${event.engine} 로그인`), el("div", "body"), el("div", "actions"));
    $("log").appendChild(card);
    loginCards[event.engine] = card;
  }
  const body = card.querySelector(".body");
  const actions = card.querySelector(".actions");
  body.innerHTML = "";
  actions.innerHTML = "";
  const cancel = button("취소", () => api("DELETE", `/api/login/${event.engine}`).catch(report), "ghost");
  const finish = (text) => {
    body.textContent = text;
    delete loginCards[event.engine];
    loadEngines().catch(report);
  };

  switch (event.state) {
    case "started":
      body.textContent = "로그인 주소를 받는 중…";
      actions.appendChild(cancel);
      break;
    case "waiting": {
      if (event.url) {
        const link = el("a", "", event.url);
        link.href = event.url;
        link.target = "_blank";
        body.append(el("div", "", "1. 이 주소를 열고 구독한 계정으로 로그인한다."), link);
      }
      if (event.userCode) {
        body.append(el("div", "", "2. 주소의 화면에 이 코드를 넣는다."), el("div", "code", event.userCode));
        body.append(el("div", "muted small", "다 되면 이 카드가 저절로 바뀐다."));
      }
      if (event.mode === "code") {
        body.append(el("div", "", "2. 로그인한 뒤 화면에 나온 코드를 복사해 아래에 붙여 넣는다."));
        const input = el("input");
        input.placeholder = "코드 붙여 넣기";
        const row = el("div", "row");
        row.append(input, button("보내기", () => api("POST", `/api/login/${event.engine}/code`, { code: input.value }).catch(report)));
        body.appendChild(row);
      }
      actions.appendChild(cancel);
      break;
    }
    case "checking":
      body.textContent = "코드를 확인하는 중…";
      break;
    case "done":
      finish("로그인했다. 이제 이 엔진으로 에이전트를 연결할 수 있다.");
      break;
    case "logged_out":
      finish("로그아웃했다.");
      break;
    case "cancelled":
      finish("로그인을 멈췄다.");
      break;
    default:
      finish(`로그인하지 못했다. ${event.message || ""}`);
  }
  scrollDown();
}

// ---- 에이전트 (custom/agents/) ----

function skillsText(skills) {
  if (skills === null) return "스킬: 모두";
  return skills.length ? `스킬: ${skills.join(", ")}` : "스킬: 없음";
}

async function loadAgents() {
  const data = await api("GET", "/api/agents");
  $("agents").innerHTML = "";
  for (const a of data.agents) {
    const li = el("li", "agent-item" + (a.name === data.current ? " current" : ""));
    const head = el("div", "head");
    head.append(el("b", "", a.name), button("고치기", () => agentForm(a), "link"));
    const select = el("select");
    for (const name of engineNames) {
      const option = el("option", "", name === a.engine ? `${name} (기본)` : name);
      option.value = name;
      select.appendChild(option);
    }
    select.value = a.name === data.current && data.engine ? data.engine : a.engine;
    const row = el("div", "row");
    row.append(select, button("연결", () => connect(a.name, select.value)));
    const memory = a.history ? ` · 플랫폼이 가진 대화 ${a.history}개` : "";
    li.append(head, el("div", "desc", a.description || ""), el("div", "desc", skillsText(a.skills) + memory), row);
    $("agents").appendChild(li);
  }
  if (!data.agents.length) $("agents").innerHTML = '<li class="meta">에이전트가 없다. "+ 새 에이전트"로 만든다</li>';
  showState(data.state, data.current, data.engine);
}

async function connect(agent, engine) {
  try { await api("POST", "/api/session", { agent, engine }); }
  catch (e) { report(e); }
}

function showState(state, agent, engine) {
  const who = agent ? `${agent} · ${engine} · ` : "";
  $("state").textContent = who + (STATE[state] || state);
}

// 에이전트 만들기와 고치기. 저장하면 custom/agents/<이름>.md가 생기거나 바뀐다.
function agentForm(existing) {
  const card = el("div", "card");
  const grid = el("div", "form-grid");
  const field = (label, input) => { grid.append(el("label", "", label), input); return input; };

  const name = field("이름", el("input"));
  name.placeholder = "예: 마감_정리 (공백 대신 밑줄)";
  const engine = field("엔진", el("select"));
  for (const n of engineNames) { const o = el("option", "", n); o.value = n; engine.appendChild(o); }
  const description = field("설명", el("input"));
  description.placeholder = "화면에 보일 한 줄";
  const checks = field("스킬", el("div", "checks"));
  const all = el("input"); all.type = "checkbox";
  const allLabel = el("label"); allLabel.append(all, " 모두");
  checks.appendChild(allLabel);
  const boxes = skillList.map((s) => {
    const box = el("input"); box.type = "checkbox"; box.value = s.name;
    const label = el("label"); label.append(box, " " + s.name);
    checks.appendChild(label);
    return box;
  });
  all.onchange = () => boxes.forEach((b) => { b.disabled = all.checked; });
  const role = field("역할", el("textarea"));
  role.rows = 6;
  role.placeholder = "이 에이전트가 맡는 일과 지킬 규칙. 플랫폼 안내의 \"너의 역할\"에 들어간다.";

  if (existing) {
    name.value = existing.name;
    name.disabled = true;
    engine.value = existing.engine;
    description.value = existing.description;
    role.value = existing.role;
    all.checked = existing.skills === null;
    boxes.forEach((b) => { b.checked = (existing.skills || []).includes(b.value); });
  } else {
    all.checked = true;
    engine.value = engineNames[0] || "";
  }
  all.onchange();

  const actions = el("div", "actions");
  const save = button(existing ? "저장" : "만들기", async () => {
    const body = {
      name: name.value.trim(), engine: engine.value, description: description.value, role: role.value,
      skills: all.checked ? null : boxes.filter((b) => b.checked).map((b) => b.value),
    };
    try {
      if (existing) await api("PUT", `/api/agents/${encodeURIComponent(existing.name)}`, body);
      else await api("POST", "/api/agents", body);
      card.innerHTML = "";
      card.append(el("b", "", `${body.name} ${existing ? "저장함" : "만듦"}`),
                  el("div", "muted small", `custom/agents/${body.name}.md`));
      loadAgents().catch(report);
    } catch (e) { report(e); }
  });
  actions.append(save, button("취소", () => card.remove(), "ghost"));
  card.append(el("b", "", existing ? `에이전트 고치기 · ${existing.name}` : "새 에이전트"), grid, actions);
  $("log").appendChild(card);
  scrollDown();
  (existing ? description : name).focus();
}

$("new-agent").onclick = () => agentForm(null);

// ---- 스킬 ----

async function loadSkills() {
  const data = await api("GET", "/api/skills");
  skillList = data.skills;
  $("skills").innerHTML = "";
  for (const skill of data.skills) {
    const li = el("li", "skill");
    li.append(el("div", "", skill.name), el("div", "desc", skill.description));
    if (skill.example) {
      li.appendChild(button("해 보기", () => { $("text").value = skill.example; $("text").focus(); }, "ghost"));
    }
    $("skills").appendChild(li);
  }
  if (!data.skills.length) $("skills").innerHTML = '<li class="meta">스킬이 없다</li>';
}

// ---- 대화 ----

$("composer").onsubmit = async (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (!text) return;
  try { await api("POST", "/api/prompt", { text }); $("text").value = ""; }
  catch (e) { report(e); }
};

// 새 대화: 지금 에이전트의 앞의 대화를 지우고 같은 엔진으로 다시 연결한다.
$("fresh").onclick = async () => {
  try {
    const data = await api("GET", "/api/agents");
    if (!data.current) { add("note", "먼저 에이전트에 연결한다."); return; }
    await api("POST", "/api/session", { agent: data.current, engine: data.engine, fresh: true });
  } catch (e) { report(e); }
};

$("text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("composer").requestSubmit();
  }
});

function permissionCard(event) {
  const card = el("div", "card");
  const actions = el("div", "actions");
  for (const [label, allow] of [["허락", true], ["거절", false]]) {
    actions.appendChild(button(label, () => api("POST", `/api/permissions/${event.id}`, { allow }).catch(report),
                               allow ? "" : "ghost"));
  }
  card.append(el("b", "", `허락 요청 · ${event.label}`), el("div", "detail", event.detail || ""), actions);
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

// 서버의 사건을 차례로 화면에 옮긴다.
function handle(event) {
  switch (event.type) {
    case "status":
      if (event.state === "ready") add("note", `${event.agent}에 연결됨 · 엔진 ${event.engine}`);
      if (event.state === "error") add("note error", event.message || "오류");
      if (event.state === "starting" || event.state === "ready") loadAgents().catch(() => {});
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
    case "done":
      add("note", `끝 · ${event.usage}`);
      answer = null;
      loadOutbox().catch(() => {});
      break;
    case "task":
      if (event.state === "running") add("note", `일 '${event.name}' 실행 시작 (${event.agent}${event.engine ? " · " + event.engine : ""})`);
      else {
        add("note", `일 '${event.name}' 끝 → 결과함 ${event.file}`);
        if (event.deliveryError) add("note error", event.deliveryError);
        loadOutbox().catch(() => {});
      }
      break;
    case "login":
      loginCard(event);
      break;
  }
}

async function poll() {
  while (true) {
    try {
      const data = await api("GET", `/api/events?after=${last}`);
      for (const event of data.events) handle(event);
      last = data.last;
      showState(data.state, data.agent, data.engine);
    } catch (e) {
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

// ---- 일과 결과함 ----

async function loadTasks() {
  const data = await api("GET", "/api/tasks");
  $("tasks").innerHTML = "";
  for (const task of data.tasks) {
    const li = el("li", "task");
    const info = el("div");
    const who = task.agent + (task.engine ? ` · ${task.engine}` : "");
    info.append(el("div", "", task.name),
                el("div", "meta", `${who} · ${task.time ? "매일 " + task.time : "직접 실행"}${task.lastRun ? " · 마지막 " + task.lastRun : ""}`));
    li.append(info, button("실행", () => api("POST", `/api/tasks/${encodeURIComponent(task.name)}/run`).catch(report)));
    $("tasks").appendChild(li);
  }
  if (!data.tasks.length) $("tasks").innerHTML = '<li class="meta">일이 없다</li>';
}

async function loadOutbox() {
  const data = await api("GET", "/api/outbox");
  $("outbox").innerHTML = "";
  for (const file of data.files.slice(0, 20)) {
    const li = el("li", "clickable", file.name);
    li.onclick = async () => {
      if (file.type === "html") { window.open(file.url, "_blank"); return; }
      const f = await api("GET", `/api/outbox/${encodeURIComponent(file.name)}`);
      add("file", f.text);
    };
    $("outbox").appendChild(li);
  }
  if (!data.files.length) $("outbox").innerHTML = '<li class="meta">아직 없다</li>';
}

$("reload-tasks").onclick = () => loadTasks().catch(report);
$("reload-outbox").onclick = () => loadOutbox().catch(report);

add("note", "에이전트를 고르고 엔진을 골라 연결하면 시작한다. 엔진의 로그인 상태는 왼쪽 '엔진' 칸에 있다. 스킬의 '해 보기'를 누르면 예시 요청이 입력칸에 들어간다.");
loadBrand().catch(() => {});
Promise.all([loadEngines(), loadSkills()]).then(loadAgents).catch(report);
loadTasks().catch(report);
loadOutbox().catch(report);
poll();
