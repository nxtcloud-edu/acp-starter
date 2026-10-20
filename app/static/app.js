// 내 에이전트 플랫폼의 화면 코드. dashboard.py의 JSON API를 부른다.
// 새 기능은 먼저 dashboard.py에 API를 더하고, 여기서 그 API를 부르게 만든다.

const $ = (id) => document.getElementById(id);
let last = 0;          // 마지막으로 받은 사건 번호
let answer = null;     // 지금 쓰는 중인 에이전트의 답 칸
const cards = {};      // 허락 요청 카드: 번호 → 칸
const loginCards = {}; // 로그인 카드: 에이전트 이름 → 칸

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

// ---- 이름과 색 (custom/brand.json) ----

async function loadBrand() {
  const brand = await api("GET", "/api/brand");
  document.title = brand.name;
  $("brand-name").textContent = brand.name;
  $("brand-tagline").textContent = brand.tagline || "";
  if (brand.accent) document.documentElement.style.setProperty("--accent", brand.accent);
}

// ---- 에이전트와 로그인 ----

const STATE = { idle: "연결하지 않음", starting: "연결하는 중…", ready: "준비됨", busy: "답을 쓰는 중…", error: "오류" };

function loginBadge(a) {
  if (!a.installed) return ["설치 안 됨", "need"];
  if (a.loggedIn === true) return ["로그인됨", "ok"];
  if (a.loggedIn === false) return ["로그인 필요", "need"];
  return ["알 수 없음", ""];
}

async function loadAgents() {
  const data = await api("GET", "/api/agents");
  $("agent").innerHTML = "";
  $("agents").innerHTML = "";
  for (const a of data.agents) {
    const option = el("option", "", a.name);
    option.value = a.name;
    $("agent").appendChild(option);

    const li = el("li", "agent");
    const [label, tone] = loginBadge(a);
    const info = el("div");
    info.append(el("span", "", a.name + " "), el("span", "badge " + tone, label));
    li.appendChild(info);
    if (a.installed && a.loginMode !== "terminal" && a.loggedIn !== true) {
      li.appendChild(button("로그인", () => api("POST", `/api/login/${a.name}`).catch(report)));
    } else if (a.installed && a.canLogout && a.loggedIn === true) {
      li.appendChild(button("로그아웃", () => api("POST", `/api/logout/${a.name}`).catch(report), "ghost"));
    } else if (a.installed && a.loginMode === "terminal" && a.loggedIn !== true) {
      li.appendChild(el("code", "", a.loginCommand));
    }
    $("agents").appendChild(li);
  }
  if (data.current) $("agent").value = data.current;
  showState(data.state, data.current);
}

function showState(state, agent) {
  $("state").textContent = agent ? `${agent} · ${STATE[state] || state}` : STATE[state] || state;
}

$("connect").onclick = async () => {
  try { await api("POST", "/api/session", { agent: $("agent").value }); }
  catch (e) { report(e); }
};
$("reload-agents").onclick = () => loadAgents().catch(report);

// 로그인 카드: 주소(와 기기 코드)를 보여 주고, Claude는 받은 코드를 붙여 넣는다.
function loginCard(event) {
  let card = loginCards[event.agent];
  if (!card) {
    card = el("div", "card");
    card.append(el("b", "", `${event.agent} 로그인`), el("div", "body"), el("div", "actions"));
    $("log").appendChild(card);
    loginCards[event.agent] = card;
  }
  const body = card.querySelector(".body");
  const actions = card.querySelector(".actions");
  body.innerHTML = "";
  actions.innerHTML = "";
  const cancel = button("취소", () => api("DELETE", `/api/login/${event.agent}`).catch(report), "ghost");

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
        row.append(input, button("보내기", () => api("POST", `/api/login/${event.agent}/code`, { code: input.value }).catch(report)));
        body.appendChild(row);
      }
      actions.appendChild(cancel);
      break;
    }
    case "checking":
      body.textContent = "코드를 확인하는 중…";
      break;
    case "done":
      body.textContent = "로그인했다. 이제 연결할 수 있다.";
      delete loginCards[event.agent];
      loadAgents().catch(report);
      break;
    case "logged_out":
      body.textContent = "로그아웃했다.";
      delete loginCards[event.agent];
      loadAgents().catch(report);
      break;
    case "cancelled":
      body.textContent = "로그인을 멈췄다.";
      delete loginCards[event.agent];
      loadAgents().catch(report);
      break;
    default:
      body.textContent = `로그인하지 못했다. ${event.message || ""}`;
      delete loginCards[event.agent];
      loadAgents().catch(report);
  }
  scrollDown();
}

// ---- 스킬 ----

async function loadSkills() {
  const data = await api("GET", "/api/skills");
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
  const title = (event.title || "").split("\n")[0].slice(0, 80);
  card.append(el("b", "", `허락 요청 · ${title}`), el("div", "detail", event.detail || ""), actions);
  $("log").appendChild(card);
  scrollDown();
  cards[event.id] = card;
}

function preambleNote(event) {
  const details = el("details", "msg note");
  details.append(el("summary", "", "플랫폼이 보낸 안내 (첫 질문 앞에 붙는다 · custom/업무.md와 스킬 목록)"),
                 el("pre", "", event.text));
  $("log").appendChild(details);
  scrollDown();
}

// 서버의 사건을 차례로 화면에 옮긴다.
function handle(event) {
  switch (event.type) {
    case "status":
      showState(event.state, event.agent);
      if (event.state === "ready") add("note", `${event.agent}에 연결됨`);
      if (event.state === "error") add("note error", event.message || "오류");
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
      add("note", `도구 · ${event.title}`);
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
      add("note", `규칙(custom/rules.py) · ${event.allow ? "허락" : "거절"} · ${event.title}`);
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
      if (event.state === "running") add("note", `일 '${event.name}' 실행 시작 (${event.agent})`);
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
      showState(data.state, data.agent);
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
    info.append(el("div", "", task.name),
                el("div", "meta", `${task.agent} · ${task.time ? "매일 " + task.time : "직접 실행"}${task.lastRun ? " · 마지막 " + task.lastRun : ""}`));
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

add("note", "왼쪽 위에서 로그인 상태를 보고, 에이전트를 골라 연결을 누르면 시작한다. 스킬의 '해 보기'를 누르면 예시 요청이 입력칸에 들어간다.");
loadBrand().catch(() => {});
loadAgents().catch(report);
loadSkills().catch(report);
loadTasks().catch(report);
loadOutbox().catch(report);
poll();
