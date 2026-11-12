/* 留学 Agent 控制台 —— 纯原生 JS，无构建步骤 */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const STAGE_LABEL = {
  clue: "新线索", consult: "咨询中", signed: "已签约", material: "材料收集",
  document: "文书制作", application: "网申递交", offer: "Offer/CAS",
  visa: "签证", finished: "已完结",
};

const DEMO = {
  chat: "学生李同学，南京理工大学计算机科学与技术专业大三，GPA 3.2/4.0，均分 82，雅思 6.5，有两段实习，一段科研，想申请英国和香港的计算机硕士，预算 35 万，2027 年 9 月入学。家长比较看重 QS 排名，问能不能保录前 50。",
  payload: {
    customer_questions: "你们能不能保录前 50？",
    experiences: [
      "1. 2026.07-2026.09 字节跳动 数据分析实习生：负责本地生活商户数据看板，用 SQL 清洗 50 万条订单数据，搭建 Python 自动化报表，日报产出从 3 小时压缩到 10 分钟。",
      "2. 2025.07-2025.09 江苏银行 金融科技部实习生：参与风控规则测试，编写 120 条测试用例，发现 8 个规则漏洞。",
      "3. 2025.03-2025.12 南京理工大学实验室科研：基于 XGBoost 的信用违约预测，处理 12 万条样本，AUC 从 0.76 提升到 0.84。",
      "4. 2025.11 全国大学生数学建模竞赛 省二等奖。",
    ].join("\n"),
    uploaded_files: [
      { name: "中英文成绩单", text: "南京理工大学 学生成绩单 TRANSCRIPT 教务处盖章 GPA 3.2 均分 82" },
      { name: "存款证明", text: "中国银行 存款证明 存款金额 300000 元 存入日期 2026-10-20 存期 30 天" },
      { name: "护照", text: "Passport 姓名 LI MING 护照号 E12345678 有效期至 2031-05-01" },
    ],
    application_form: {
      name_pinyin: "LI MING", passport_no: "E12345679", gpa: 3.3,
      program_code: "MSC-CS-2027", application_fee_paid: true, round: "第一轮",
    },
    emails: [
      { subject: "Missing documents for your application", text: "We require an additional document: your final transcript. Please upload before 2027-01-15." },
      { subject: "Interview invitation", text: "We would like to invite you for a Kira video assessment. Please complete it before 2027-01-10." },
    ],
    referees: [{ email: "prof.zhang@njust.edu.cn", send_link_date: "2026-10-20", submitted: false }],
    offer_file: {
      text: "University of Manchester\nProgramme: Advanced Computer Science\nSeptember 2027\n\nConditional Offer\nThis offer is subject to achieving an overall average of 85% and IELTS 7.0 with no band below 6.5.\nTuition deposit: GBP 1,000 payable by 2027-03-31.\nPlease respond to this offer by 2027-02-15.",
    },
    fund_data: { amount: 300000, deposit_days: 22, deposit_date: "2026-10-20",
                 large_inflows: [{ amount: 150000, days_ago: 5 }], statement_gaps: [75] },
    fund_from_parent: true,
    arrival_date: "2027-09-01",
    cas_date: "2027-06-01",
    chat_messages: [
      { role: "advisor", text: "放心，我们可以保录前 50，也能保过雅思。" },
      { role: "customer", text: "真的吗？那太好了。" },
    ],
  },
};

const app = {
  data: null,
  tab: "overview",
  route: "workbench",
  user: null,
};

const TOKEN_KEY = "sa_token";

function authHeader() {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: "Bearer " + token } : {};
}

/* ---------------- 工具 ---------------- */
function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function dash(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  return esc(value);
}

function badge(text, tone) {
  const map = { 高: "red", 中: "amber", 低: "green", 冲刺: "red", 匹配: "blue", 保底: "green",
                紧急: "red", 普通: "gray", 延期风险: "amber" };
  return `<span class="badge ${tone || map[text] || "gray"}">${esc(text)}</span>`;
}

function table(headers, rows) {
  if (!rows.length) return `<div class="empty">无数据</div>`;
  return `<table class="data"><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function toast(msg, isErr) {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.className = "toast"; }, 2800);
}

async function api(path, options = {}) {
  const resp = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(options.headers || {}) },
  });
  if (resp.status === 401) {
    logout(true);
    throw new Error("登录已过期，请重新登录");
  }
  if (!resp.ok) throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
  const body = await resp.json();
  if (body.code !== 0) throw new Error(body.message || "接口返回错误");
  return body.data;
}

/* ---------------- 极简 Markdown ---------------- */
function renderMarkdown(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  let inList = false;
  const inline = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (/^\s*[-*]\s+/.test(line)) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push(`<li>${inline(line.replace(/^\s*[-*]\s+/, ""))}</li>`);
      continue;
    }
    if (inList) { out.push("</ul>"); inList = false; }
    if (!line.trim()) continue;
    if (/^###\s+/.test(line)) out.push(`<h3>${inline(line.slice(4))}</h3>`);
    else if (/^##\s+/.test(line)) out.push(`<h2>${inline(line.slice(3))}</h2>`);
    else if (/^#\s+/.test(line)) out.push(`<h1>${inline(line.slice(2))}</h1>`);
    else if (/^>\s?/.test(line)) out.push(`<blockquote>${inline(line.replace(/^>\s?/, ""))}</blockquote>`);
    else if (/^---+$/.test(line)) out.push("<hr>");
    else out.push(`<p>${inline(line)}</p>`);
  }
  if (inList) out.push("</ul>");
  return `<div class="md">${out.join("")}</div>`;
}

/* ---------------- 路由 ---------------- */
function go(route) {
  app.route = route;
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.route === route));
  $$(".view").forEach((v) => v.classList.add("hidden"));
  $(`#view-${route}`).classList.remove("hidden");
  if (route === "customers") loadCustomers();
  if (route === "dashboard") loadDashboard();
  if (route === "system") loadSystem();
}

/* ---------------- 顶部状态灯 ---------------- */
async function loadStatus() {
  try {
    const h = await api("/api/dashboard/health");
    $("#chipService").className = "chip ok";
    $("#chipService").querySelector("span").textContent = "服务正常";
    $("#chipKnowledge").className = "chip " + (h.knowledge > 0 ? "ok" : "warn");
    $("#chipKnowledge").querySelector("span").textContent = `知识 ${h.knowledge} 条`;
    $("#chipLlm").className = "chip " + (h.llm_live ? "ok" : "warn");
    $("#chipLlm").querySelector("span").textContent =
      h.llm_live ? `LLM ${h.llm}` : `LLM ${h.llm}（离线兜底）`;
  } catch (e) {
    $("#chipService").className = "chip err";
    $("#chipService").querySelector("span").textContent = "服务未连接";
  }
}

/* ---------------- 工作台：执行 ---------------- */
function readPayload() {
  const raw = $("#inpPayload").value.trim();
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error("高级业务数据不是合法 JSON：" + e.message);
  }
}

async function runFlow(mode) {
  const customerId = $("#inpCustomerId").value.trim() || "demo-001";
  const name = $("#inpName").value.trim();
  const chat = $("#inpChat").value.trim();
  let payload;
  try {
    payload = readPayload();
  } catch (e) {
    toast(e.message, true);
    return;
  }

  const btn = mode === "all" ? $("#btnRunAll") : $("#btnMatchOnly");
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = "执行中…";
  setStage("运行中", "run");
  $("#resultSub").textContent = "Agent 正在执行，请稍候（mock 模式通常 2-5 秒）";

  try {
    if (mode === "all") {
      await api("/api/graph/run-all", {
        method: "POST",
        body: JSON.stringify({ customer_id: customerId, chat_text: chat, payload }),
      });
    } else {
      await api("/api/school/match", {
        method: "POST",
        body: JSON.stringify({ customer_id: customerId, chat_text: chat, name }),
      });
    }
    await loadCustomer(customerId);
    toast("执行完成");
  } catch (e) {
    toast(e.message, true);
    $("#resultSub").textContent = "执行失败：" + e.message;
    setStage("失败", "");
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

function setStage(text, cls) {
  const el = $("#stagePill");
  el.textContent = text;
  el.className = "stage-pill " + (cls || "");
}

async function loadCustomer(customerId) {
  const data = await api(`/api/customer/${encodeURIComponent(customerId)}`);
  app.data = data;
  $("#inpCustomerId").value = data.customer_id;
  $("#inpName").value = data.customer_name || "";
  $("#resultTitle").textContent = data.customer_name || data.customer_id;
  $("#resultSub").textContent =
    `阶段 ${STAGE_LABEL[data.stage] || data.stage} · 执行链 ${(data.history || []).join(" → ") || "—"}`;
  setStage(STAGE_LABEL[data.stage] || data.stage, data.stage === "finished" ? "done" : "");
  renderTab();
}

/* ---------------- 工作台：渲染 ---------------- */
function renderTab() {
  const body = $("#tabBody");
  if (!app.data) {
    body.innerHTML = `<div class="empty">暂无数据，点左侧「一键跑全流程」</div>`;
    return;
  }
  const out = app.data.agent_outputs || {};
  const renderers = {
    overview: renderOverview,
    school: () => renderSchool(out.school),
    report: () => renderReport(out.school),
    document: () => renderDocument(out.document),
    material: () => renderMaterial(out.material),
    application: () => renderApplication(out.application),
    offer: () => renderOffer(out.offer),
    visa: () => renderVisa(out.visa),
    interview: () => renderInterview(out.interview),
    risk: () => renderRisk(out.risk),
  };
  body.innerHTML = (renderers[app.tab] || renderOverview)();
  $$(".school-item").forEach((el) => {
    el.addEventListener("click", () => el.classList.toggle("open"));
  });
  if (app.tab === "interview") wireInterview();
}

function renderOverview() {
  const d = app.data;
  const s = d.student_info || {};
  const out = d.agent_outputs || {};
  const school = (out.school || {}).result || {};
  const counts = {
    冲刺: (school.sprint_list || []).length,
    匹配: (school.match_list || []).length,
    保底: (school.safe_list || []).length,
  };
  const tasks = d.task_list || [];
  const urgent = tasks.filter((t) => t.level === "紧急");

  const infoRows = [
    ["院校", `${dash(s.school_name)}（${dash(s.school_level)}）`],
    ["专业", dash(s.major)],
    ["GPA", s.gpa != null ? `${s.gpa} / 4.0` : "—"],
    ["语言", s.ielts ? `雅思 ${s.ielts}` : (s.toefl ? `托福 ${s.toefl}` : "—")],
    ["意向", `${(s.target_country || []).join("、") || "—"} · ${dash(s.target_degree)} · ${dash(s.target_major)}`],
    ["预算 / 入学", `${dash(s.budget)} · ${s.intake_year || "—"} 年`],
  ];

  const chips = (d.risk_tags || []).map((t) => badge(t, "amber")).join(" ") || `<span class="badge green">无风险</span>`;

  const taskRows = tasks.slice(0, 12).map((t) => [
    esc(t.title), badge(t.level), esc(t.due_date || "—"), esc(t.source || ""),
  ]);

  return `
    <div class="section-title">学生档案</div>
    ${table(["项目", "内容"], infoRows)}

    <div class="section-title">选校结构 <span class="count">共 ${counts.冲刺 + counts.匹配 + counts.保底} 所</span></div>
    <div class="grid-4">
      <div class="kpi"><div class="label">冲刺</div><div class="value">${counts.冲刺}</div></div>
      <div class="kpi"><div class="label">匹配</div><div class="value">${counts.匹配}</div></div>
      <div class="kpi"><div class="label">保底</div><div class="value">${counts.保底}</div></div>
      <div class="kpi ${urgent.length ? "danger" : "ok"}"><div class="label">紧急待办</div>
        <div class="value">${urgent.length}</div></div>
    </div>

    <div class="section-title">风险标签</div>
    <div>${chips}</div>

    <div class="section-title">待办清单 <span class="count">共 ${tasks.length} 条</span></div>
    ${table(["待办", "等级", "截止", "来源"], taskRows)}

    ${(d.errors || []).length ? `<div class="section-title">异常</div>
      <div class="card" style="border-color:#fecaca;background:#fef2f2">
        ${d.errors.map((e) => `<div style="color:#b91c1c;font-size:12.5px">${esc(e)}</div>`).join("")}
      </div>` : ""}
  `;
}

function renderSchool(school) {
  if (!school || !school.result) return `<div class="empty">还没有选校结果</div>`;
  const res = school.result;
  const cols = [
    ["冲刺", "sprint_list", "red"],
    ["匹配", "match_list", "blue"],
    ["保底", "safe_list", "green"],
  ];

  const itemHtml = (item) => {
    const detail = Object.entries(item.score_detail || {})
      .map(([k, v]) => `<div class="detail-bar"><span style="width:66px">${esc(k)}</span>
        <span class="bar"><i style="width:${Math.min(100, (v / 60) * 100)}%"></i></span>
        <span>${v}</span></div>`).join("");
    return `<div class="school-item">
      <div class="top">
        <div><div class="name">${esc(item.school_name)}</div>
          <div class="major">${esc(item.major_name)} · ${esc(item.country)}</div></div>
        <div class="score">${item.match_score}</div>
      </div>
      <div class="meta">
        <span>${esc(item.gpa_require)}</span><span>${esc(item.lang_require)}</span>
        <span>截止 ${esc(item.deadline)}${item.days_left != null ? `（${item.days_left} 天）` : ""}</span>
      </div>
      ${item.risk_point ? `<div class="risk">风险：${esc(item.risk_point)}</div>` : ""}
      <div class="detail">${detail || "无打分明细"}
        <div style="margin-top:6px;color:#94a3b8">来源 ${esc(item.source_id)}</div></div>
    </div>`;
  };

  const cols3 = cols.map(([label, key, tone]) => `
    <div>
      <div class="section-title">${badge(label, tone)} <span class="count">${(res[key] || []).length} 所</span></div>
      <div class="school-col">${(res[key] || []).map(itemHtml).join("") || `<div class="empty">暂无</div>`}</div>
    </div>`).join("");

  const talk = school.talk ? `<div class="section-title">合规话术（客户问：${esc(school.talk.question)}）</div>
    ${badge(school.talk.intent, "blue")} ${badge("风险 " + school.talk.safety_level, school.talk.safety_level === "high" ? "red" : "green")}
    <div class="card" style="margin-top:8px">${esc(school.talk.text)}</div>` : "";

  const followup = school.followup ? `<div class="section-title">追问话术（信息缺失）</div>
    <div class="card">${esc(school.followup)}</div>` : "";

  const dropped = (res.filtered_out || []).length ? `<div class="section-title">被剔除 <span class="count">${res.filtered_out.length} 所</span></div>
    ${table(["学校", "专业", "原因"], res.filtered_out.slice(0, 8).map((d) => [esc(d.school_name), esc(d.major_name), esc(d.reason)]))}` : "";

  return `<div class="grid-3">${cols3}</div>${talk}${followup}${dropped}`;
}

function renderReport(school) {
  const report = school && school.report;
  if (!report) return `<div class="empty">还没有评估报告</div>`;
  const facts = report.facts || {};
  const difficulty = facts.difficulty || "—";
  return `
    <div class="grid-4" style="margin-bottom:14px">
      <div class="kpi"><div class="label">难度评级</div><div class="value">${esc(difficulty)}</div></div>
      <div class="kpi"><div class="label">时间窗口</div><div class="value" style="font-size:18px">${esc((facts.window || {}).window || "—")}</div></div>
      <div class="kpi"><div class="label">距入学</div><div class="value" style="font-size:18px">${esc((facts.window || {}).months_left ?? "—")}<small>月</small></div></div>
      <div class="kpi"><div class="label">生成方式</div><div class="value" style="font-size:18px">${esc(report.source)}</div></div>
    </div>
    ${renderMarkdown(report.markdown)}`;
}

function renderDocument(doc) {
  if (!doc) return `<div class="empty">还没有文书产出</div>`;
  const q = doc.quality || {};
  const total = Number(q.total || 0);
  const color = total >= 80 ? "#16a34a" : total >= 60 ? "#d97706" : "#dc2626";
  const dims = Object.entries(q.dimensions || {}).map(([k, v]) => `
    <div class="detail-bar"><span style="width:76px">${esc(k)}</span>
      <span class="bar"><i style="width:${Math.min(100, v)}%;background:${color}"></i></span>
      <span>${v}</span></div>`).join("");
  const res = doc.result || {};
  const block = (title, text) => text ? `
    <details style="margin-top:10px">
      <summary style="cursor:pointer;font-size:13px;font-weight:600">${esc(title)}</summary>
      <pre class="code" style="margin-top:8px;max-height:320px;white-space:pre-wrap">${esc(text)}</pre>
    </details>` : "";

  const versions = Object.entries(doc.versions || {}).map(([k, v]) => [esc(k), `<code>${esc(v)}</code>`]);

  return `
    <div class="grid-2" style="align-items:start">
      <div class="card" style="display:flex;gap:14px;align-items:center">
        <div class="ring" style="background:conic-gradient(${color} ${total * 3.6}deg, #eef2ff 0)">
          <span style="color:${color}">${total}</span></div>
        <div>
          <div style="font-weight:700">文书质检分（${esc(q.source || "rule")}）</div>
          <div style="font-size:12px;color:#64748b">低于 60 分会被打高危标签、禁止直接交付</div>
        </div>
      </div>
      <div class="card">
        <div style="font-size:12px;color:#64748b;margin-bottom:6px">六维得分（模板化/空话为反向项）</div>
        ${dims || "无"}
      </div>
    </div>

    <div class="section-title">质检意见</div>
    <ul>${(q.comments || []).map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
    <div class="section-title">优化建议</div>
    <ul>${(q.suggestions || []).map((c) => `<li>${esc(c)}</li>`).join("")}</ul>

    ${block("CV 简历", res.cv_content)}
    ${block("PS 个人陈述", res.ps_content)}
    ${block("推荐信 · 学术版", res.ref1_content)}
    ${block("推荐信 · 企业版", res.ref2_content)}

    <div class="section-title">版本存档 <span class="count">${versions.length} 个</span></div>
    ${table(["类型", "version_id"], versions)}`;
}

function renderMaterial(m) {
  if (!m) return `<div class="empty">还没有材料清单</div>`;
  const rows = (m.material_list || []).map((i) => [
    esc(i.material_name), esc(i.category), i.is_required ? badge("必交", "red") : badge("选交", "gray"),
    esc(i.submit_deadline || "—"), esc(i.check_standard || ""),
  ]);
  const missing = (m.missing_materials || []).map((x) => badge(x, "red")).join(" ");
  const risks = (m.all_risk || []).map((r) => [
    esc(r.material_name), badge(r.risk_level), esc(r.risk_desc), esc(r.fix_suggest || ""),
  ]);
  return `
    <div class="grid-3" style="margin-bottom:14px">
      <div class="kpi"><div class="label">清单项</div><div class="value">${(m.material_list || []).length}</div></div>
      <div class="kpi danger"><div class="label">缺失</div><div class="value">${(m.missing_materials || []).length}</div></div>
      <div class="kpi"><div class="label">校验风险</div><div class="value">${(m.all_risk || []).length}</div></div>
    </div>
    ${missing ? `<div class="section-title">缺失材料</div><div>${missing}</div>` : ""}
    ${m.notice_text ? `<div class="section-title">催收话术（学生端）</div>
      <blockquote class="md" style="margin:0;padding:10px 14px;background:#eff4ff;border-left:3px solid #2563eb;border-radius:0 8px 8px 0">
        ${esc(m.notice_text)}</blockquote>` : ""}
    <div class="section-title">材料清单</div>
    ${table(["材料", "分类", "必交", "建议截止", "校验标准"], rows)}
    <div class="section-title">校验风险</div>
    ${table(["材料", "等级", "问题", "整改建议"], risks)}`;
}

function renderApplication(a) {
  if (!a) return `<div class="empty">还没有网申数据</div>`;
  const errors = (a.form_error_list || []).map((e) => [
    esc(e.field_name), badge(e.level, e.level === "低级错误" ? "red" : "amber"),
    esc(e.error_msg), esc(e.suggest_value || "—"),
  ]);
  const mails = (a.mail_info_list || []).map((m) => `
    <div class="card">
      <div style="display:flex;justify-content:space-between;gap:8px">
        <strong>${esc(m.mail_intent)}</strong>${badge("置信 " + (m.confidence ?? "—"), "gray")}
      </div>
      <div style="font-size:12px;color:#64748b;margin-top:4px">${esc(m.source_subject || "")}</div>
      <div style="font-size:12.5px;margin-top:6px">
        截止：${esc(m.deadline || "—")}　需补：${(m.need_supplement || []).join("、") || "—"}
      </div>
      ${m.extra_notice ? `<div style="font-size:12px;color:#b45309;margin-top:4px">${esc(m.extra_notice)}</div>` : ""}
    </div>`).join("");
  const warns = (a.deadline_warn_list || []).map((w) => [
    esc(w.school), esc(w.major), badge(w.tier, w.rank >= 3 ? "red" : w.rank === 2 ? "amber" : "gray"),
    esc(w.deadline), `${w.days_left} 天`,
  ]);
  const refs = (a.referee_todo || []).map((r) => [
    esc(r.referee_email), esc(r.send_link_date), `${r.days_waiting} 天`,
    r.is_submitted ? badge("已提交", "green") : (r.remind_content ? badge("待催", "red") : badge("等待中", "gray")),
  ]);
  return `
    <div class="section-title">表单预校验 <span class="count">${errors.length} 处问题</span></div>
    ${table(["字段", "等级", "问题", "建议值"], errors)}
    <div class="section-title">院校邮件意图</div>
    <div class="grid-2">${mails || `<div class="empty">无邮件</div>`}</div>
    <div class="section-title">截止倒计时预警</div>
    ${table(["学校", "专业", "级别", "截止", "剩余"], warns)}
    <div class="section-title">推荐人跟进</div>
    ${table(["推荐人邮箱", "发链接日期", "已等待", "状态"], refs)}`;
}

function renderOffer(o) {
  if (!o) return `<div class="empty">还没有 Offer 数据</div>`;
  const conds = (o.cond_list || []).map((c) => [
    esc(c.cond_type), esc(c.require_value), esc(c.current_student_value || "—"),
    esc(c.gap || "—"), badge(c.reach_risk), esc(c.improve_suggest || ""),
  ]);
  const p = o.policy_info || {};
  const timeline = (o.cas_time_timeline || []).map((t) => `
    <div class="timeline-item"><div>${esc(t)}</div></div>`).join("");
  return `
    <div class="grid-2" style="margin-bottom:14px">
      <div class="card">
        <h4>${esc(o.school_name || "—")} · ${esc(o.major || "—")}</h4>
        <div class="row"><span class="k">入学</span><span class="v">${esc(o.intake || "—")}</span></div>
        <div class="row"><span class="k">类型</span><span class="v">${o.is_conditional ? "有条件 Offer" : "无条件 Offer"}</span></div>
        <div class="row"><span class="k">整体风险</span><span class="v">${badge(o.overall_risk)}</span></div>
      </div>
      <div class="card">
        <h4>押金与 CAS 政策</h4>
        <div class="row"><span class="k">押金</span><span class="v">${esc(p.deposit_amount || "—")}</span></div>
        <div class="row"><span class="k">退费规则</span><span class="v">${esc(p.deposit_refund_rule || "—")}</span></div>
        <div class="row"><span class="k">换无条件截止</span><span class="v">${esc(p.unconditional_deadline || "—")}</span></div>
        ${p.policy_conflict ? `<div class="row"><span class="k">政策冲突</span><span class="v" style="color:#dc2626">${esc(p.policy_conflict)}</span></div>` : ""}
      </div>
    </div>
    <div class="section-title">录取条件达标测算</div>
    ${table(["条件", "Offer 要求", "学生当前", "差距", "风险", "提升建议"], conds)}
    <div class="section-title">CAS 办理时间线</div>
    <div class="timeline">${timeline || `<div class="empty">无</div>`}</div>`;
}

function renderVisa(v) {
  if (!v) return `<div class="empty">还没有签证数据</div>`;
  const risks = (v.fund_risk_list || []).map((r) => [
    badge(r.risk_level), esc(r.risk_tag), esc(r.reason), esc(r.fix_plan || ""),
  ]);
  const mats = (v.visa_material_list || []).map((m) => [
    esc(m.material_name), m.need_notarize ? badge("需公证", "amber") : "—",
    `${m.valid_days} 天`, esc(m.remark || ""),
  ]);
  const tl = (v.time_timeline || []).map((n) => `
    <div class="timeline-item">
      <div><strong>${esc(n.node_name)}</strong>　<span class="when">${esc(n.suggest_finish_date || "")}（${n.cycle_days} 天）</span></div>
      <div style="color:#64748b;font-size:12px">${esc(n.risk_warn || "")}</div>
    </div>`).join("");
  return `
    <div class="grid-3" style="margin-bottom:14px">
      <div class="kpi"><div class="label">目标国家</div><div class="value" style="font-size:20px">${esc(v.target_country)}</div></div>
      <div class="kpi"><div class="label">资金总额</div><div class="value" style="font-size:20px">${(v.fund_total || 0).toLocaleString()}<small>元</small></div></div>
      <div class="kpi ${v.overall_risk === "高" ? "danger" : "ok"}"><div class="label">整体风险</div>
        <div class="value" style="font-size:20px">${esc(v.overall_risk)}</div></div>
    </div>
    <div class="section-title">资金风险</div>
    ${table(["等级", "风险", "原因", "整改方案"], risks)}
    <div class="section-title">签证材料包</div>
    ${table(["材料", "公证", "有效期", "备注"], mats)}
    <div class="section-title">递签时间线</div>
    <div class="timeline">${tl || `<div class="empty">无</div>`}</div>`;
}

function renderRisk(r) {
  if (!r) return `<div class="empty">还没有风控数据</div>`;
  const pred = r.prediction || {};
  const score = Number(pred.score || 0);
  const color = score >= 60 ? "#dc2626" : score >= 30 ? "#d97706" : "#16a34a";
  const orders = (r.workorders || []).map((o) => [
    badge(o.level), esc(o.role), esc(o.excerpt), esc(o.reason), esc(o.action),
  ]);
  const facts = Object.entries(pred.facts || {}).map(([k, v]) => [esc(k), String(v)]);
  return `
    <div class="grid-2" style="align-items:start;margin-bottom:14px">
      <div class="card" style="display:flex;gap:14px;align-items:center">
        <div class="ring" style="background:conic-gradient(${color} ${score * 3.6}deg, #eef2ff 0)">
          <span style="color:${color}">${score}</span></div>
        <div>
          <div style="font-weight:700">退费/客诉风险分（${esc(pred.level)}）</div>
          <div style="font-size:12px;color:#64748b">${(pred.reasons || []).map(esc).join("；")}</div>
        </div>
      </div>
      <div class="card">
        <h4>风险标签</h4>
        ${(pred.tags || []).map((t) => badge(t, "red")).join(" ") || badge("无", "green")}
      </div>
    </div>
    <div class="section-title">打分事实</div>
    ${table(["维度", "命中数"], facts)}
    <div class="section-title">合规工单 <span class="count">${orders.length} 条</span></div>
    ${table(["等级", "角色", "原话", "判定理由", "处理建议"], orders)}
    ${r.handover_preview ? `<div class="section-title">离职交接预览</div>
      <pre class="code" style="max-height:260px;white-space:pre-wrap">${esc(r.handover_preview)}</pre>` : ""}`;
}

/* ---------------- 模拟面试 ---------------- */
function renderIvScore(ans) {
  const dims = Object.entries(ans.dimensions || {}).map(([k, v]) => `
    <div class="iv-dim"><span style="width:64px">${esc(k)}</span>
      <span class="bar"><i style="width:${Math.min(100, v)}%"></i></span>
      <span>${v}</span></div>`).join("");
  return `
    <div class="grid-2" style="gap:10px;align-items:start">
      <div><div class="iv-score">${ans.total} 分</div>${dims}</div>
      <div>
        <div class="iv-feedback">${(ans.feedback || []).map(esc).join("；")}</div>
        ${ans.suggestion ? `<div class="iv-suggest">建议：${esc(ans.suggestion)}</div>` : ""}
      </div>
    </div>`;
}

function renderInterview(iv) {
  if (!iv || !iv.questions || !iv.questions.length) {
    return `<div class="empty">
      <p style="margin-bottom:12px">还没有模拟面试。会按目标专业自动抽 6 道题（动机/学术/行为/思辨/收尾）。</p>
      <button class="btn primary" id="btnInterviewStart">生成模拟面试</button>
      <p class="hint">生成后逐题作答，系统按「结构 / 具体性 / 量化 / 专业匹配 / 表达」五维打分。</p>
    </div>`;
  }

  const cards = iv.questions.map((q, idx) => {
    const ans = (iv.answers || []).find((a) => a.qid === q.qid);
    return `<div class="iv-item" data-qid="${esc(q.qid)}">
      <div class="iv-head">
        <span class="badge blue">${esc(q.category)}</span>
        <span class="badge gray">${esc(q.difficulty)}</span>
        <span class="iv-q">${idx + 1}. ${esc(q.question)}</span>
      </div>
      <div class="iv-focus">考察点：${esc(q.focus)}</div>
      <details class="iv-hint"><summary>参考要点（答题前别偷看）</summary><div>${esc(q.hints)}</div></details>
      <textarea class="iv-answer" rows="3" placeholder="按 STAR 写：背景 → 我的任务 → 我做了什么 → 结果（带数字）"></textarea>
      <div class="iv-actions">
        <button class="btn" data-iv-answer="${esc(q.qid)}">提交评分</button>
        ${ans ? `<span class="iv-score">${ans.total} 分</span>`
              : `<span class="hint" style="margin:0" data-iv-flag="${esc(q.qid)}">未作答</span>`}
      </div>
      <div class="iv-result" data-iv-result="${esc(q.qid)}">${ans ? renderIvScore(ans) : ""}</div>
    </div>`;
  }).join("");

  return `
    <div class="card" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div>
        <div style="font-weight:700">${esc(iv.target || "模拟面试")}</div>
        <div class="hint" style="margin-top:2px" id="ivStats">
          场次 ${esc(iv.session_id)} · 已答 ${(iv.answers || []).length}/${iv.questions.length} ·
          平均 ${iv.avg_score || 0} 分
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" id="btnIvReport">复盘报告</button>
        <button class="btn ghost" id="btnInterviewStart">重新出题</button>
      </div>
    </div>
    ${cards}
    <div id="ivReportBox"></div>`;
}

function wireInterview() {
  const startBtn = $("#btnInterviewStart");
  if (startBtn) {
    startBtn.addEventListener("click", async () => {
      const id = $("#inpCustomerId").value.trim();
      startBtn.disabled = true;
      startBtn.textContent = "出题中…";
      try {
        const data = await api("/api/interview/start", {
          method: "POST",
          body: JSON.stringify({ customer_id: id, count: 6 }),
        });
        app.data.agent_outputs = app.data.agent_outputs || {};
        app.data.agent_outputs.interview = data;
        renderTab();
        toast(`已生成 ${data.questions.length} 道题`);
      } catch (e) {
        toast("出题失败：" + e.message, true);
        startBtn.disabled = false;
        startBtn.textContent = "生成模拟面试";
      }
    });
  }

  $$("[data-iv-answer]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const qid = btn.dataset.ivAnswer;
      const item = btn.closest(".iv-item");
      const answer = item.querySelector(".iv-answer").value.trim();
      if (answer.length < 10) {
        toast("先写点内容再提交（至少 10 个字）", true);
        return;
      }
      btn.disabled = true;
      btn.textContent = "评分中…";
      try {
        const data = await api("/api/interview/answer", {
          method: "POST",
          body: JSON.stringify({
            session_id: app.data.agent_outputs.interview.session_id,
            qid,
            answer,
          }),
        });
        const iv = app.data.agent_outputs.interview;
        iv.answers = (iv.answers || []).filter((a) => a.qid !== qid).concat([data.score]);
        iv.avg_score = data.avg_score;
        item.querySelector(`[data-iv-result="${qid}"]`).innerHTML = renderIvScore(data.score);
        const stats = $("#ivStats");
        if (stats) {
          stats.textContent = `场次 ${iv.session_id} · 已答 ${iv.answers.length}/${iv.questions.length} · 平均 ${iv.avg_score} 分`;
        }
        const flag = item.querySelector(`[data-iv-flag="${qid}"]`);
        if (flag) {
          flag.textContent = `${data.score.total} 分`;
          flag.className = "iv-score";
        }
        toast(`得分 ${data.score.total}（平均 ${data.avg_score}）`);
      } catch (e) {
        toast("评分失败：" + e.message, true);
      } finally {
        btn.disabled = false;
        btn.textContent = "提交评分";
      }
    });
  });

  const reportBtn = $("#btnIvReport");
  if (reportBtn) {
    reportBtn.addEventListener("click", async () => {
      try {
        const data = await api(`/api/interview/report?session_id=${encodeURIComponent(
          app.data.agent_outputs.interview.session_id)}`);
        $("#ivReportBox").innerHTML = renderMarkdown(data.report);
        $("#ivReportBox").scrollIntoView({ behavior: "smooth" });
      } catch (e) {
        toast("生成报告失败：" + e.message, true);
      }
    });
  }
}

/* ---------------- 客户台账 ---------------- */
async function loadCustomers() {
  const box = $("#customerTable");
  box.innerHTML = `<div class="empty">加载中…</div>`;
  try {
    const rows = await api("/api/customer/list?limit=100");
    if (!rows.length) {
      box.innerHTML = `<div class="empty">还没有客户，去工作台跑一个</div>`;
      return;
    }
    box.innerHTML = table(
      ["客户编号", "姓名", "阶段", "最近更新", ""],
      rows.map((c) => [
        `<code>${esc(c.customer_id)}</code>`, esc(c.name || "—"),
        badge(STAGE_LABEL[c.stage] || c.stage, c.stage === "finished" ? "green" : "blue"),
        esc((c.updated_at || "").replace("T", " ")),
        `<button class="link" data-open="${esc(c.customer_id)}">打开</button>`,
      ]),
    );
    $$("[data-open]").forEach((btn) => btn.addEventListener("click", async () => {
      go("workbench");
      await loadCustomer(btn.dataset.open);
      toast("已加载客户 " + btn.dataset.open);
    }));
  } catch (e) {
    box.innerHTML = `<div class="empty">加载失败：${esc(e.message)}</div>`;
  }
}

/* ---------------- 风控看板 ---------------- */
async function loadDashboard() {
  try {
    const d = await api("/api/dashboard/overview");
    const c = d.customers, t = d.tasks, r = d.risks;

    $("#kpiGrid").innerHTML = [
      ["客户总数", c.total, ""],
      ["已签约", c.signed, "ok"],
      ["转化率", c.conversion + "%", "ok"],
      ["待办", t.total, ""],
      ["紧急待办", (t.by_level || {})["紧急"] || 0, "danger"],
      ["风险条目", r.total, "danger"],
    ].map(([label, value, cls]) => `
      <div class="kpi ${cls}"><div class="label">${label}</div>
        <div class="value">${value}</div></div>`).join("");

    const pipe = d.pipeline || [];
    const maxStage = Math.max(1, ...pipe.map((s) => s.count), ...c.by_stage.map((s) => s.count));
    $("#funnel").innerHTML = pipe.map((s) => `
      <div class="funnel-row">
        <span class="label">${esc(s.label)}</span>
        <span class="track"><i style="width:${(s.count / maxStage) * 100}%"></i></span>
        <span class="num">${s.count}</span>
      </div>`).join("");

    const maxRisk = Math.max(1, ...(r.top || []).map((x) => x.count));
    $("#riskTop").innerHTML = (r.top || []).map((x) => `
      <div class="risk-row">
        <span class="tag">${esc(x.tag)}</span>
        <span class="bar"><i style="width:${(x.count / maxRisk) * 100}%"></i></span>
        <span class="n">${x.count}</span>
      </div>`).join("") || `<div class="empty">暂无风险</div>`;

    $("#recentCustomers").innerHTML = table(
      ["客户", "阶段", "更新时间"],
      (d.recent || []).map((x) => [
        `<code>${esc(x.customer_id)}</code> ${esc(x.name || "")}`,
        badge(STAGE_LABEL[x.stage] || x.stage, "blue"),
        esc((x.updated_at || "").replace("T", " ")),
      ]),
    );
  } catch (e) {
    toast("看板加载失败：" + e.message, true);
  }
}

/* ---------------- 系统状态 ---------------- */
async function loadSystem() {
  try {
    const s = await api("/api/system/stats");
    const rag = s.rag || {};
    const llm = s.llm || {};
    const st = s.storage || {};
    $("#sysKpi").innerHTML = [
      ["院校库", rag.school || 0], ["签证库", rag.visa || 0],
      ["文书库", rag.writing || 0], ["合规库", rag.compliance || 0],
      ["客户", st.customers || 0], ["文书版本", st.doc_versions || 0],
    ].map(([label, value]) => `
      <div class="kpi"><div class="label">${label}</div><div class="value">${value}</div></div>`).join("");

    $("#sysConfig").innerHTML = table(["配置", "值"], [
      ["LLM Provider", esc(llm.provider) + (llm.enabled ? "（已连接真实模型）" : "（离线规则兜底）")],
      ["LLM 调用次数", String(llm.calls ?? 0)],
      ["LLM 缓存命中", String((llm.cache || {}).hits ?? 0)],
      ["RAG 后端", esc((s.config || {}).rag_backend)],
      ["Embedding", esc((s.config || {}).embed_backend)],
      ["OCR 后端", esc((s.config || {}).ocr_backend)],
      ["LangGraph", (s.config || {}).use_langgraph ? "启用" : "已关闭"],
    ]);
    $("#sysRaw").textContent = JSON.stringify(s, null, 2);
  } catch (e) {
    $("#sysRaw").textContent = "加载失败：" + e.message;
  }
}

/* ---------------- 初始化 ---------------- */
function initDemo() {
  $("#inpChat").value = DEMO.chat;
  $("#inpPayload").value = JSON.stringify(DEMO.payload, null, 2);
}

function initApp() {
  if (app.inited) {
    loadStatus();
    return;
  }
  app.inited = true;
  $("#nav").addEventListener("click", (e) => {
    const btn = e.target.closest(".nav-item");
    if (btn) go(btn.dataset.route);
  });

  $("#tabs").addEventListener("click", (e) => {
    const tab = e.target.closest(".tab");
    if (!tab) return;
    app.tab = tab.dataset.tab;
    $$(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    renderTab();
  });

  $("#btnRunAll").addEventListener("click", () => runFlow("all"));
  $("#btnMatchOnly").addEventListener("click", () => runFlow("match"));
  $("#btnFillDemo").addEventListener("click", () => { initDemo(); toast("已填充示例数据"); });
  $("#btnClear").addEventListener("click", () => {
    app.data = null;
    $("#tabBody").innerHTML = `<div class="empty">暂无数据</div>`;
    $("#resultTitle").textContent = "执行结果";
    $("#resultSub").textContent = "还没有数据，点左边「一键跑全流程」";
    setStage("—", "");
  });
  $("#btnReloadCustomers").addEventListener("click", loadCustomers);

  $("#btnStudentLink").addEventListener("click", async () => {
    const id = $("#inpCustomerId").value.trim() || (app.data && app.data.customer_id);
    if (!id) {
      toast("先填客户编号或跑一次流程", true);
      return;
    }
    try {
      const data = await api(`/api/customer/${encodeURIComponent(id)}/student-link`);
      const url = location.origin + data.url;
      try { await navigator.clipboard.writeText(url); } catch (e) { /* 剪贴板不可用时忽略 */ }
      toast("学生端链接已复制，正在打开…");
      window.open(url, "_blank");
    } catch (e) {
      toast("生成链接失败：" + e.message, true);
    }
  });

  loadStatus();
  setInterval(loadStatus, 30000);
  go((location.hash || "#workbench").slice(1) || "workbench");
}

/* ---------------- 登录 / 登出 ---------------- */
function showLogin() {
  $("#loginLayer").hidden = false;
  $("#chipUser").hidden = true;
  const box = $("#loginErr");
  if (box) box.textContent = "";
}

function hideLogin() {
  $("#loginLayer").hidden = true;
}

function renderUser() {
  if (!app.user) return;
  $("#chipUser").hidden = false;
  const role = app.user.role === "admin" ? "负责人" : "顾问";
  $("#chipUserName").textContent = `${app.user.name || app.user.username}（${role}）`;
}

function logout(silent) {
  localStorage.removeItem(TOKEN_KEY);
  app.user = null;
  $("#chipUser").hidden = true;
  showLogin();
  if (!silent) toast("已退出登录");
}

async function doLogin(event) {
  event.preventDefault();
  const btn = $("#btnLogin");
  const err = $("#loginErr");
  err.textContent = "";
  btn.disabled = true;
  btn.textContent = "登录中…";
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("#loginUser").value.trim(),
        password: $("#loginPass").value,
      }),
    });
    localStorage.setItem(TOKEN_KEY, data.token);
    app.user = data.user;
    renderUser();
    hideLogin();
    initDemo();
    initApp();
    toast(`欢迎，${data.user.name || data.user.username}`);
  } catch (e) {
    err.textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "登录";
  }
}

async function boot() {
  initDemo();
  $("#loginForm").addEventListener("submit", doLogin);
  $("#btnLogout").addEventListener("click", () => logout(false));

  if (!localStorage.getItem(TOKEN_KEY)) {
    showLogin();
    return;
  }
  try {
    app.user = await api("/api/auth/me");
    renderUser();
    hideLogin();
    initApp();
  } catch (e) {
    showLogin();
  }
}

document.addEventListener("DOMContentLoaded", boot);
