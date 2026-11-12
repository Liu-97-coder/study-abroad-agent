/* 学生端：材料上传 + 进度查看（凭 access_key 免登录） */

const $ = (sel) => document.querySelector(sel);
const key = new URLSearchParams(location.search).get("k") || "";
let view = null;

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function toast(msg, isErr) {
  const el = $("#sToast");
  el.textContent = msg;
  el.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.className = "toast"; }, 3200);
}

async function getJSON(url) {
  const resp = await fetch(url);
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail || body.message || `HTTP ${resp.status}`);
  return body.data;
}

function renderProgress(progress) {
  $("#sProgress").innerHTML = (progress || []).map((s) => `
    <div class="s-step ${s.done ? "done" : ""}">
      <div class="bar"></div>${esc(s.label)}
    </div>`).join("");
}

function uploadedMap() {
  const map = {};
  (view.uploaded || []).forEach((u) => { map[u.name] = u; });
  return map;
}

function renderMaterials() {
  const uploaded = view.uploaded || [];
  const findDone = (name) => uploaded.find((u) => u.name === name
    || u.name.includes(name) || name.includes(u.name));
  const rows = (view.materials || []).map((m) => {
    const done = findDone(m.name);
    const cls = done ? (done.pass_flag ? "uploaded" : "rejected") : "";
    const status = done
      ? (done.pass_flag ? "已通过校验" : "已收到，待修正")
      : "待上传";
    return `
      <div class="s-item ${cls}" data-material="${esc(m.name)}">
        <div class="row1">
          <div>
            <div class="name">${esc(m.name)} ${m.required ? "" : '<span class="badge gray">选交</span>'}</div>
            <div class="std">${esc(m.standard || "")}</div>
            ${m.deadline ? `<div class="due">建议 ${esc(m.deadline)} 前提交</div>` : ""}
          </div>
          <label class="s-upload">
            ${done ? "重新上传" : "上传"}
            <input type="file" accept="image/*,.pdf,.txt,.md" data-upload="${esc(m.name)}" />
          </label>
        </div>
        <div class="s-result" data-result="${esc(m.name)}">${status}</div>
      </div>`;
  });
  $("#sMaterials").innerHTML = rows.join("") || `<div class="s-empty">暂无材料要求</div>`;

  document.querySelectorAll("input[data-upload]").forEach((input) => {
    input.addEventListener("change", () => uploadFile(input));
  });
}

function renderUploaded() {
  const list = view.uploaded || [];
  $("#sUploadedCount").textContent = list.length ? `共 ${list.length} 份` : "";
  $("#sUploaded").innerHTML = list.length
    ? list.map((u) => `
        <div class="s-item ${u.pass_flag ? "uploaded" : "rejected"}">
          <div class="row1">
            <div class="name">${esc(u.name)}</div>
            <span class="badge ${u.pass_flag ? "green" : "red"}">
              ${u.pass_flag ? "已通过" : "待修正"}</span>
          </div>
          <div class="std">${esc(u.uploaded_at || "")}</div>
        </div>`).join("")
    : `<div class="s-empty">还没有上传记录</div>`;
}

async function uploadFile(input) {
  const material = input.dataset.upload;
  const file = input.files && input.files[0];
  if (!file) return;

  const row = input.closest(".s-item");
  const label = row.querySelector(".s-upload");
  const resultBox = row.querySelector(`[data-result]`);
  label.classList.add("busy");
  resultBox.textContent = "上传并校验中…";

  const form = new FormData();
  form.append("key", key);
  form.append("material_name", material);
  form.append("file", file);

  try {
    const resp = await fetch("/api/student/upload", { method: "POST", body: form });
    const body = await resp.json();
    if (!resp.ok || body.code !== 0) throw new Error(body.message || body.detail || "上传失败");
    const data = body.data;
    const risks = (data.risks || []).map((r) =>
      `<div class="risk">· [${esc(r.level)}] ${esc(r.desc)}<div class="fix">整改：${esc(r.fix)}</div></div>`).join("");
    resultBox.innerHTML = `<b>${esc(data.message)}</b>${risks}`;
    toast(data.pass ? "校验通过" : "已收到，请按提示修正");
    await load();
  } catch (e) {
    resultBox.textContent = "上传失败：" + e.message;
    toast(e.message, true);
  } finally {
    label.classList.remove("busy");
    input.value = "";
  }
}

async function load() {
  if (!key) {
    $("#sNotice").innerHTML = "链接缺少访问参数，请向顾问重新索取。";
    $("#sMaterials").innerHTML = "";
    return;
  }
  view = await getJSON(`/api/student/view?key=${encodeURIComponent(key)}`);
  $("#sName").textContent = view.customer_name || "同学";
  $("#sStage").textContent = "当前阶段：" + (view.stage_label || "—");
  $("#sTarget").textContent = [view.target.country, view.target.degree, view.target.major]
    .filter(Boolean).join(" · ") || "申请意向待确认";
  renderProgress(view.progress);
  $("#sMissing").textContent = view.missing.length ? `还差 ${view.missing.length} 项` : "已齐全";
  $("#sNotice").textContent = view.notice;
  renderMaterials();
  renderUploaded();
}

load().catch((e) => {
  $("#sNotice").textContent = "加载失败：" + e.message;
  $("#sMaterials").innerHTML = "";
});
