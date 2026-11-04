// 내 에이전트 플랫폼의 화면 코드. dashboard.py의 JSON API를 부르는 클라이언트다.
// 새 기능은 먼저 dashboard.py에 API를 더하고, 여기서 그 API를 부른다.
// 화면은 엔진 이름을 따로 다루지 않는다. 엔진 목록은 /api/engines에서 받는다.
//
// 흐름: 처음에 /api/state로 지금 상태를 읽는다. 그 뒤로는 /api/events로 서버의 사건을 받아 화면에 옮긴다.

const $ = (id) => document.getElementById(id);

// 화면의 상태. 서버에서 받은 것을 한곳에 둔다.
const S = {
  engines: [],          // 엔진 목록(로그인 상태 포함)
  conversation: null,   // 지금 대화(메시지 포함)
  state: "idle",        // 서버가 열어 둔 엔진 세션의 상태
  engine: null,         // 그 세션의 엔진
  login: {},            // 엔진 이름 → 마지막 로그인 사건
};
let last = 0;           // 마지막으로 받은 사건 번호
let epoch = null;       // 서버를 켤 때마다 바뀌는 값. 바뀌면 처음부터 다시 읽는다
let answer = null;      // 지금 쓰는 중인 답 칸
const cards = {};       // 허락 카드: 번호 → 칸

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

const busy = () => S.state === "starting" || S.state === "busy";
const firstLine = (text) => (text || "").split("\n")[0].slice(0, 120);
const showError = (e) => add("note error", e.message);

// ---- 이름과 색 (custom/brand.json) ----

async function loadBrand() {
  const brand = await api("GET", "/api/brand");
  document.title = brand.name;
  $("brand-name").textContent = brand.name;
  $("brand-tagline").textContent = brand.tagline || "";
  if (brand.accent) document.documentElement.style.setProperty("--accent", brand.accent);
}

// ---- 엔진 세션의 상태 ----

const STATE = { idle: "대기 중", starting: "연결하는 중", ready: "준비됨", busy: "답을 쓰는 중", error: "오류" };

function setStatus(data) {
  const changed = data.state !== S.state || data.engine !== S.engine;
  S.state = data.state;
  S.engine = data.engine;
  const label = STATE[S.state] || S.state;
  $("status").textContent = S.engine ? `${S.engine} · ${label}` : label;
  $("status").dataset.state = S.state;
  $("send").disabled = busy();
  $("new-chat").disabled = busy();
  if (changed) renderEngines();
}

// ---- 엔진 카드: 로그인 상태, 로그인, 연결 ----

async function loadEngines() {
  S.engines = (await api("GET", "/api/engines")).engines;
  renderEngines();
}

function loginBadge(e) {
  if (!e.installed) return ["설치 안 됨", "need"];
  if (e.loggedIn === true) return ["로그인됨", "ok"];
  if (e.loggedIn === false) return ["로그인 필요", "need"];
  return ["알 수 없음", ""];
}

function renderEngines() {
  const list = $("engine-list");
  list.innerHTML = "";
  if (!S.engines.length) list.append(el("p", "muted small", "엔진 목록을 읽는 중…"));
  const current = S.conversation && S.conversation.engine;
  for (const e of S.engines) {
    const card = el("div", "engine" + (e.name === current ? " current" : ""));
    const head = el("div", "engine-head");
    const [text, tone] = loginBadge(e);
    head.append(el("b", "", e.name), el("span", "badge " + tone, text));
    card.append(head);
    if (e.name === current) card.append(el("p", "muted small", "이 대화의 엔진"));

    const actions = el("div", "actions");
    const connected = e.name === S.engine && (S.state === "ready" || S.state === "busy");
    const connect = button(connected ? "연결됨" : "연결",
                           () => api("POST", "/api/connect", { engine: e.name }).catch(showError));
    connect.disabled = connected || busy() || !e.installed || e.loggedIn === false;
    actions.append(connect);
    if (e.installed && e.loginMode !== "terminal" && e.loggedIn !== true) {
      actions.append(button("로그인", () => api("POST", `/api/login/${e.name}`).catch(showError), "ghost"));
    } else if (e.installed && e.loginMode === "terminal" && e.loggedIn !== true) {
      actions.append(el("code", "", e.loginCommand));
    } else if (e.installed && e.canLogout && e.loggedIn === true) {
      actions.append(button("로그아웃", () => api("POST", `/api/logout/${e.name}`).catch(showError), "link"));
    }
    card.append(actions);
    if (S.login[e.name]) card.append(loginBox(e.name, S.login[e.name]));
    list.append(card);
  }
}

// 로그인 상자: 주소(와 기기 코드)를 보여 주고, 코드 방식이면 받은 코드를 붙여 넣는다.
function loginBox(engine, event) {
  const box = el("div", "login-box");
  const cancel = () => button("취소", () => api("DELETE", `/api/login/${engine}`).catch(showError), "ghost");
  box.append(el("b", "", `${engine} 로그인`));
  switch (event.state) {
    case "started":
      box.append(el("div", "", "로그인 주소를 받는 중…"), cancel());
      break;
    case "waiting": {
      if (event.url) {
        const link = el("a", "", event.url);
        link.href = event.url;
        link.target = "_blank";
        box.append(el("div", "", "1. 이 주소를 열고 구독한 계정으로 로그인합니다."), link);
      }
      if (event.userCode) {
        box.append(el("div", "", "2. 주소의 화면에 이 코드를 넣습니다."), el("div", "code", event.userCode),
                   el("div", "muted small", "다 되면 이 상자가 저절로 바뀝니다."));
      }
      if (event.mode === "code") {
        box.append(el("div", "", "2. 로그인한 뒤 화면에 나온 코드를 복사해 붙여 넣습니다."));
        const input = el("input");
        input.placeholder = "코드 붙여 넣기";
        const row = el("div", "row");
        row.append(input, button("보내기", () => api("POST", `/api/login/${engine}/code`, { code: input.value }).catch(showError)));
        box.append(row);
      }
      box.append(cancel());
      break;
    }
    case "checking": box.append(el("div", "", "코드를 확인하는 중…")); break;
    case "done": box.append(el("div", "", "로그인했습니다. 이제 연결할 수 있습니다.")); break;
    case "logged_out": box.append(el("div", "", "로그아웃했습니다.")); break;
    case "cancelled": box.append(el("div", "", "로그인을 멈췄습니다.")); break;
    default: box.append(el("div", "", `로그인하지 못했습니다. ${event.message || ""}`));
  }
  return box;
}

// ---- 대화 기록 ----

function scrollDown() { $("log").scrollTop = $("log").scrollHeight; }

function add(className, text) {
  for (const p of $("log").querySelectorAll(".placeholder")) p.remove();
  const div = el("div", "msg " + className, text);
  $("log").append(div);
  scrollDown();
  return div;
}

// 대화를 처음부터 그린다.
function renderLog() {
  $("log").innerHTML = "";
  answer = null;
  for (const id of Object.keys(cards)) delete cards[id];
  for (const m of S.conversation.messages) renderMessage(m);
  if (!$("log").children.length) {
    $("log").append(el("p", "placeholder", "왼쪽에서 엔진을 연결하고 맡길 일을 아래에 적어 보세요."));
  }
}

// 대화 기록의 메시지 하나(conversations.py의 꼴)를 그린다.
function renderMessage(m) {
  if (m.role === "user") return add("user", m.text);
  if (m.role === "preamble") return preambleNote(m);
  if (m.role === "note") return add(m.error ? "note error" : "note", m.text);
  if (m.role !== "agent") return;
  add("agent", m.text || "(답이 비어 있습니다)");
  const summary = [m.stopLabel, `엔진 ${m.engine}`, m.usage].filter(Boolean).join(" · ");
  const lines = [...(m.tools || []).map((t) => "도구 · " + t), ...(m.refused || []).map((t) => "거절 · " + t),
                 ...(m.notices || []).map((t) => "플랫폼 · " + t)];
  if (!lines.length) return add("note", summary);
  const details = el("details", "msg note");
  details.append(el("summary", "", `${summary} · 쓴 도구 ${(m.tools || []).length}개`), el("pre", "", lines.join("\n")));
  $("log").append(details);
}

// 플랫폼이 엔진에 보낸 안내. 눌러서 펼치면 실제로 간 글이 보인다.
function preambleNote(item) {
  const details = el("details", "msg note");
  const carried = item.history ? ` · 앞의 대화 ${item.history}개를 넣음` : "";
  details.append(el("summary", "", `플랫폼이 보낸 안내 · 엔진 ${item.engine}${carried}`), el("pre", "", item.text));
  $("log").append(details);
  scrollDown();
}

function permissionCard(event) {
  const card = el("div", "card");
  const actions = el("div", "actions");
  actions.append(button("허락", () => api("POST", `/api/permissions/${event.id}`, { allow: true }).catch(showError)),
                 button("거절", () => api("POST", `/api/permissions/${event.id}`, { allow: false }).catch(showError), "ghost"));
  card.append(el("b", "", `허락 요청 · ${event.label}`), el("div", "detail", event.detail || ""), actions);
  $("log").append(card);
  scrollDown();
  cards[event.id] = card;
}

// ---- 서버의 사건을 화면에 옮긴다 ----

// 답을 쓰는 중인 차례의 사건. 대화 기록에는 차례가 끝나야 남으므로 그동안은 사건으로 그린다.
const LIVE = ["text", "tool", "permission", "permission_result", "rule", "rule_error", "notice"];

function renderLive(event) {
  switch (event.type) {
    case "text":
      if (!answer) answer = add("agent", "");
      answer.textContent += event.text;
      scrollDown();
      return;
    case "tool": add("note", `도구 · ${event.label} · ${firstLine(event.detail)}`); break;
    case "permission": permissionCard(event); break;
    case "permission_result": {
      const card = cards[event.id];
      if (card) card.querySelector(".actions").textContent = event.timeout ? "답이 없어 거절함" : event.allow ? "허락함" : "거절함";
      return;
    }
    case "rule": add("note", `규칙(custom/rules.py) · ${event.allow ? "허락" : "거절"} · ${event.label} · ${firstLine(event.detail)}`); break;
    case "rule_error": add("note error", event.message); break;
    case "notice": add("note", `플랫폼 · ${event.text}`); break;
  }
  answer = null;   // 도구나 알림 뒤에 오는 글은 새 칸에 쓴다
}

async function loadConversation(redraw) {
  S.conversation = await api("GET", "/api/conversation");
  if (redraw) renderLog();
  renderEngines();
}

function handle(event) {
  if (LIVE.includes(event.type)) return renderLive(event);
  switch (event.type) {
    case "user": add("user", event.text); answer = null; break;
    case "preamble": preambleNote(event); break;
    case "note": add("note", event.text); loadConversation(false).catch(showError); break;
    case "record_error": add("note error", event.message); break;
    case "done": add("note", `${event.stopLabel} · ${event.usage}`); answer = null; break;
    case "status":
      if (event.state === "error" && event.message) add("note error", `오류: ${event.message}`);
      setStatus(event);
      break;
    case "conversation": loadConversation(true).catch(showError); break;
    case "login":
      S.login[event.engine] = event;
      if (["done", "logged_out", "failed", "cancelled"].includes(event.state)) loadEngines().catch(showError);
      else renderEngines();
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
      setStatus(data);
    } catch (e) {
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
}

// ---- 보내기, 새 대화 ----

$("composer").onsubmit = async (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (!text || busy()) return;
  try {
    await api("POST", "/api/prompt", { text });
    $("text").value = "";
  } catch (e) { showError(e); }
};

$("text").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {   // 한글을 조합하는 중에는 보내지 않는다
    event.preventDefault();
    $("composer").requestSubmit();
  }
});

$("new-chat").onclick = () => api("POST", "/api/conversation/new").catch(showError);   // 화면은 사건을 받아 다시 그린다

// ---- 시작 ----

// 서버의 지금 상태를 읽는다. 답을 쓰는 중인 차례가 있으면 그 사건부터 이어 그린다.
async function start() {
  const state = await api("GET", "/api/state");
  last = state.last;
  epoch = state.epoch;
  S.conversation = state.conversation;
  renderLog();
  for (const event of state.live) if (LIVE.includes(event.type)) renderLive(event);
  setStatus(state);
  renderEngines();
  loadEngines().catch(showError);   // 로그인 상태를 보는 데 시간이 걸려서 기다리지 않는다
}

loadBrand().catch(() => {});
start().catch(showError).finally(poll);
