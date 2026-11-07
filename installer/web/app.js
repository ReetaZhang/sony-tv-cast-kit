/* 索尼电视投屏助手 · 前端逻辑 */
(function () {
  "use strict";

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));

  const app = {
    state: null,
    logs: [],
    step: 1,
    selected: localStorage.getItem("sc.apk") || "lite",
    name: localStorage.getItem("sc.name") || "",
    pending: false,
    flags: { launched: false, installError: "" },
    checkResult: null,
    apkSignature: "",
  };

  /* ------------------------------------------------------------------ */
  /* 基础工具                                                            */
  /* ------------------------------------------------------------------ */
  function fmtSize(bytes) {
    if (!bytes) return "—";
    if (bytes > 1048576) return (bytes / 1048576).toFixed(1) + " MB";
    return Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  let toastTimer = null;
  function toast(message, kind) {
    const el = $("#toast");
    el.textContent = message;
    el.className = "toast show" + (kind ? " " + kind : "");
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.className = "toast";
      setTimeout(() => { el.hidden = true; }, 220);
    }, 2800);
  }

  async function api(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await res.json(); } catch (e) { data = { ok: false, error: "响应解析失败" }; }
    if (data.state) { app.state = data.state; }
    if (data.logs) { app.logs = data.logs; }
    render();
    if (!res.ok && !data.error) data.error = "请求失败（" + res.status + "）";
    return data;
  }

  function setBusy(btn, busy, label) {
    if (!btn) return;
    btn.disabled = busy;
    btn.classList.toggle("loading", busy);
    const span = btn.querySelector("span");
    if (span) {
      if (busy) { btn.dataset.label = span.textContent; span.textContent = label || "处理中…"; }
      else if (btn.dataset.label) { span.textContent = btn.dataset.label; }
    }
  }

  /* ------------------------------------------------------------------ */
  /* 渲染                                                                */
  /* ------------------------------------------------------------------ */
  function render() {
    const st = app.state;
    if (!st) return;

    $("#ipChip").innerHTML = '<svg class="chip-icon"><use href="#i-wifi"/></svg><i></i>' +
      esc(st.local_ip || "未联网");
    const adb = $("#adbChip");
    if (st.adb && st.adb.ready) {
      adb.className = "chip ok";
      adb.innerHTML = '<b class="dot"></b>adb ' + esc(st.adb.version || "就绪");
    } else {
      adb.className = "chip";
      adb.title = "首次连接电视时会自动下载 adb";
      adb.innerHTML = '<b class="dot"></b>adb 待准备';
    }

    const bar = $("#deviceBar");
    const dev = st.device;
    if (dev) {
      bar.classList.add("on");
      $("#deviceText").innerHTML = "已连接 <b>" + esc(dev.model || "电视") + "</b>" +
        (dev.android ? " · Android " + esc(dev.android) : "") +
        ' · <span style="opacity:.6">' + esc((dev.serial || "").replace(":5555", "")) + "</span>";
      $("#disconnectBtn").classList.remove("hidden");
      $("#refreshBtn").classList.add("hidden");
    } else {
      bar.classList.remove("on");
      $("#deviceText").textContent = "尚未连接电视 · 请先完成第 1 步";
      $("#disconnectBtn").classList.add("hidden");
      $("#refreshBtn").classList.remove("hidden");
    }

    renderSteps();
    renderApks();
    renderNameField();
    renderStats();
    renderCheck();
    renderLogs();
  }

  function renderCheck() {
    const apk = currentApk();
    const installed = !!(apk && apk.installed);
    const btn = $("#checkBtn");
    if (btn) btn.disabled = !installed || !(app.state && app.state.device);

    const box = $("#checkResult");
    if (!box) return;
    const r = app.checkResult;
    if (!r || !r.steps || !r.steps.length) { box.innerHTML = ""; return; }
    box.innerHTML = r.steps.map((st) =>
      '<div class="check-item ' + (st.ok ? "ok" : "bad") + '">' +
      '<svg><use href="#i-' + (st.ok ? "check" : "info") + '"/></svg>' +
      "<div><b>" + esc(st.label) + "</b>" + esc(st.detail) + "</div></div>").join("");
  }

  function renderStats() {
    const apk = currentApk();
    const installed = !!(apk && apk.installed);
    const nameEl = $("#statApk");
    if (!nameEl) return;
    nameEl.textContent = installed ? apk.title : "未安装";
    const shownName = !installed ? "—"
      : apk.rename ? (app.name || "未命名（点「保存」生效）") : "AirPlay-Receiver";
    $("#statName").textContent = shownName;
    const run = $("#statRun");
    run.textContent = app.flags.launched ? "运行中" : "未启动";
    run.className = "v" + (app.flags.launched ? " ok" : "");
  }

  function renderSteps() {
    const st = app.state || {};
    const connected = !!st.device;
    const installed = (st.apks || []).some((a) => a.installed);
    const done = { 1: connected, 2: installed, 3: installed, 4: false };
    $$(".stepper .step").forEach((el) => {
      const n = Number(el.dataset.step);
      el.classList.toggle("active", n === app.step);
      el.classList.toggle("done", !!done[n] && n !== app.step);
      el.querySelector(".num").textContent = done[n] && n !== app.step ? "✓" : String(n);
    });
    $$("main .panel").forEach((p) => p.classList.toggle("active", Number(p.dataset.step) === app.step));

    const ib = $("#installBtn");
    const cur = currentApk();
    const compatible = !cur || cur.compatible !== false;
    if (ib) {
      ib.disabled = !connected || !compatible;
      const status = $("#installStatus");
      if (connected && !compatible) {
        status.textContent = "此安装包与电视 CPU 架构不兼容，请改选「全功能版」";
        status.className = "status-text err";
      } else if (!connected) {
        status.textContent = "请先在第 1 步连接电视";
        status.className = "status-text";
      } else if (app.flags.installError) {
        status.textContent = "安装失败，请查看运行日志";
        status.className = "status-text err";
      } else if (installed) {
        status.textContent = "已安装，可进入第 3 步";
        status.className = "status-text ok";
      } else {
        status.textContent = "等待安装";
        status.className = "status-text";
      }
    }
    const lb = $("#launchBtn");
    if (lb) {
      lb.disabled = !installed;
      const st = $("#launchStatus");
      if (app.flags.launched) {
        st.textContent = "接收服务运行中，可以开始投屏了";
        st.className = "status-text ok";
      } else if (installed) {
        st.textContent = "接收端已安装，点击启动";
        st.className = "status-text";
      } else {
        st.textContent = "尚未安装接收端";
        st.className = "status-text";
      }
    }
  }

  function currentApk() {
    const list = (app.state && app.state.apks) || [];
    return list.find((a) => a.id === app.selected) || list[0] || null;
  }

  function renderApks() {
    const box = $("#apkList");
    const list = (app.state && app.state.apks) || [];
    if (!list.length) { box.innerHTML = '<p class="scan-empty">未找到安装包，请确认 apk 目录完整。</p>'; return; }

    // 数据没变化时不重建 DOM，避免悬停状态闪烁
    const signature = JSON.stringify(list.map((a) => [a.id, a.installed, a.installed_version, a.size])) + app.selected;
    if (signature === app.apkSignature) return;
    app.apkSignature = signature;

    box.innerHTML = list.map((a) => {
      const tags = (a.tags || []).map((t) =>
        '<span class="tag ' + (/验证/.test(t) ? "green" : "") + '">' + esc(t) + "</span>").join("");
      return (
        '<div class="apk ' + (a.id === app.selected ? "selected " : "") + (a.installed ? "installed " : "") +
        (a.compatible === false ? "incompatible" : "") +
        '" data-id="' + esc(a.id) + '">' +
          (a.installed ? '<span class="badge-installed">已安装</span>' : "") +
          '<div class="apk-top"><div><h3>' + esc(a.title) + "</h3>" +
            '<p class="sub">' + esc(a.subtitle || "") + "</p></div><span class=\"radio\"></span></div>" +
          '<p class="desc">' + esc(a.desc || "") + "</p>" +
          '<div class="meta">' + tags +
            '<span class="tag gray">' + fmtSize(a.size) + "</span>" +
            '<span class="tag gray">v' + esc(a.version) + "</span>" +
            (a.minSdkLabel ? '<span class="tag gray">' + esc(a.minSdkLabel) + "</span>" : "") +
            (a.compatible === false ? '<span class="tag red">不兼容此电视</span>' : "") +
          "</div>" +
        "</div>"
      );
    }).join("");

    $$("#apkList .apk").forEach((el) => {
      el.addEventListener("click", () => {
        app.selected = el.dataset.id;
        localStorage.setItem("sc.apk", app.selected);
        app.apkSignature = "";
        app.checkResult = null;
        render();
      });
    });
  }

  function renderNameField() {
    const apk = currentApk();
    const input = $("#nameInput");
    const btn = $("#saveNameBtn");
    const hint = $("#nameHint");
    if (!apk) return;
    if (apk.rename) {
      input.disabled = false;
      btn.disabled = false;
      if (document.activeElement !== input) input.value = app.name;
      hint.textContent = "保存后会在苹果设备的投屏列表里显示这个名字。建议用「客厅电视」这类好认的名字。";
      hint.className = "hint";
    } else {
      input.disabled = true;
      input.value = "";
      input.placeholder = "AirPlay-Receiver（精简版固定名称）";
      btn.disabled = true;
      hint.textContent = "精简版名称固定为 AirPlay-Receiver，不支持改名；需要自定义名称请选用全功能版。";
      hint.className = "hint";
    }
  }

  function renderLogs() {
    const box = $("#logList");
    if (!box) return;
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
    box.innerHTML = app.logs.map((l) =>
      '<div class="log-line ' + esc(l.level) + '"><span class="t">' + esc(l.ts) + "</span>" +
      "<span>" + esc(l.msg) + "</span></div>").join("");
    if (nearBottom) box.scrollTop = box.scrollHeight;
  }

  /* ------------------------------------------------------------------ */
  /* 交互                                                                */
  /* ------------------------------------------------------------------ */
  function gotoStep(n) {
    app.step = n;
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  $$(".stepper .step").forEach((el) => {
    el.addEventListener("click", () => {
      const n = Number(el.dataset.step);
      const st = app.state || {};
      if (n >= 2 && !st.device) { toast("请先在第 1 步连接电视", "err"); return; }
      gotoStep(n);
    });
  });

  $("#scanBtn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    setBusy(btn, true, "扫描中…");
    $("#scanHint").textContent = "正在扫描局域网，请稍候…";
    $("#scanResults").innerHTML = "";
    try {
      const data = await api("/api/scan");
      const hosts = data.hosts || [];
      if (hosts.length) {
        $("#scanHint").textContent = "找到 " + hosts.length + " 台设备，点击连接：";
        $("#scanResults").innerHTML = hosts.map((h) =>
          '<div class="scan-item"><svg><use href="#i-wifi"/></svg>' +
          '<span class="addr">' + esc(h) + ":5555</span>" +
          '<button class="btn" data-host="' + esc(h) + '">连接</button></div>').join("");
        $$("#scanResults .btn").forEach((b) => b.addEventListener("click", () => connect(b.dataset.host)));
      } else {
        $("#scanHint").innerHTML = '<span style="color:#f6c453">未发现电视。</span> 请确认电视「网络调试」已打开，或手动输入 IP。';
      }
    } catch (err) {
      toast("扫描失败：" + err.message, "err");
    } finally {
      setBusy(btn, false);
    }
  });

  async function connect(host) {
    const btn = $("#connectBtn");
    setBusy(btn, true, "连接中…");
    $("#connectHint").textContent = "正在连接 " + host + " … 首次连接时电视会弹出授权，请用遥控器选择「允许」。";
    try {
      const data = await api("/api/connect", { host });
      if (data.ok) {
        toast("已连接电视", "ok");
        $("#connectHint").textContent = "连接成功。";
        gotoStep(2);
      } else {
        $("#connectHint").innerHTML = '<span style="color:#ff8080">连接失败，请查看运行日志或下方排查提示。</span>';
      }
    } finally {
      setBusy(btn, false);
    }
  }

  $("#connectBtn").addEventListener("click", () => {
    const host = $("#hostInput").value.trim();
    if (!host) { $("#hostInput").focus(); toast("请输入电视 IP 地址", "err"); return; }
    connect(host);
  });
  $("#hostInput").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#connectBtn").click(); });

  $("#refreshBtn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    setBusy(btn, true, "刷新中…");
    try {
      const data = await api("/api/refresh");
      if (data.ok) { toast("已找到电视", "ok"); gotoStep(2); }
      else { toast("仍未找到电视，请确认已点「允许」并重试", "err"); }
    } finally {
      setBusy(btn, false);
    }
  });
  $("#nameInput").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#saveNameBtn").click(); });

  $("#installBtn").addEventListener("click", async (e) => {
    const apk = currentApk();
    if (!apk) return;
    const btn = e.currentTarget;
    app.pending = true;
    app.flags.installError = "";
    setBusy(btn, true, "安装中…");
    $("#installStatus").textContent = "正在推送安装包，请保持电视通电（约 10–60 秒）…";
    $("#installStatus").className = "status-text";
    try {
      const data = await api("/api/install", { id: apk.id });
      if (data.ok) {
        toast("安装成功", "ok");
        app.pending = false;
        app.flags.launched = false;
        gotoStep(3);
        return;
      }
      app.flags.installError = data.error || "install failed";
      toast("安装失败，请查看运行日志", "err");
    } catch (err) {
      app.flags.installError = err.message;
      toast("安装失败：" + err.message, "err");
    } finally {
      app.pending = false;
      setBusy(btn, false);
      render();
    }
  });

  $("#saveNameBtn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const apk = currentApk();
    const name = $("#nameInput").value.trim();
    if (!apk || !apk.rename) return;
    if (!name) { toast("请输入名称", "err"); return; }
    app.name = name;
    localStorage.setItem("sc.name", name);
    setBusy(btn, true, "保存中…");
    try {
      const data = await api("/api/rename", { id: apk.id, name: name });
      toast(data.ok ? "名称已保存" : "保存失败", data.ok ? "ok" : "err");
    } finally {
      setBusy(btn, false);
    }
  });

  $("#checkBtn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const apk = currentApk();
    if (!apk) return;
    app.pending = true;
    app.checkResult = null;
    renderCheck();
    setBusy(btn, true, "检测中…");
    try {
      const data = await api("/api/check", { id: apk.id });
      app.checkResult = data.check || null;
      renderCheck();
      toast(data.ok ? "自检通过，接收端已就绪" : "自检有项目未通过，请看结果",
            data.ok ? "ok" : "err");
    } catch (err) {
      toast("自检失败：" + err.message, "err");
    } finally {
      app.pending = false;
      setBusy(btn, false);
    }
  });

  $("#launchBtn").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const apk = currentApk();
    if (!apk) return;
    app.pending = true;
    setBusy(btn, true, "启动中…");
    $("#launchStatus").textContent = "正在启动接收服务…";
    $("#launchStatus").className = "status-text";
    try {
      const data = await api("/api/launch", { id: apk.id });
      if (data.ok) {
        app.flags.launched = true;
        toast("接收端已启动", "ok");
        app.pending = false;
        gotoStep(4);
        return;
      }
      $("#launchStatus").textContent = "启动失败，请查看日志";
      $("#launchStatus").className = "status-text err";
    } catch (err) {
      toast("启动失败：" + err.message, "err");
    } finally {
      app.pending = false;
      setBusy(btn, false);
      render();
    }
  });

  $("#disconnectBtn").addEventListener("click", async () => {
    await api("/api/disconnect");
    app.flags = { launched: false, installError: "" };
    toast("已断开连接");
    gotoStep(1);
  });

  /* Tabs ------------------------------------------------------------- */
  $$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      $$(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      $$(".tab-body").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab.dataset.tab));
    });
  });

  /* 日志抽屉 ---------------------------------------------------------- */
  const drawer = $("#logDrawer");
  $("#logToggle").addEventListener("click", () => drawer.classList.toggle("open"));
  $("#logClose").addEventListener("click", () => drawer.classList.remove("open"));
  $("#logToggle").classList.add("active");

  /* 帮助弹窗 ---------------------------------------------------------- */
  const modal = $("#helpModal");
  $("#helpBtn").addEventListener("click", () => { modal.hidden = false; });
  $("#helpClose").addEventListener("click", () => { modal.hidden = true; });
  modal.addEventListener("click", (e) => { if (e.target === modal) modal.hidden = true; });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { modal.hidden = true; drawer.classList.remove("open"); }
  });

  /* ------------------------------------------------------------------ */
  /* 启动                                                               */
  /* ------------------------------------------------------------------ */
  async function load() {
    try {
      const res = await fetch("/api/state");
      const data = await res.json();
      app.state = data.state;
      app.logs = data.logs || [];
      render();

      // 支持 ?step=2 直接打开某一步（方便演示 / 收藏）
      const params = new URLSearchParams(location.search);
      const step = Number(params.get("step"));
      if (step >= 1 && step <= 4) { app.step = step; render(); }
      if (params.get("logs") === "1") drawer.classList.add("open");
      if (params.get("check") === "1" && (app.state.apks || []).some((a) => a.installed)) {
        setTimeout(() => $("#checkBtn").click(), 300);
      }
    } catch (e) {
      setTimeout(load, 1500);
    }
  }

  load();
  setInterval(() => {
    if (document.hidden || app.pending) return;
    fetch("/api/state").then((r) => r.json()).then((data) => {
      app.state = data.state;
      app.logs = data.logs || [];
      render();
    }).catch(() => {});
  }, 1500);
})();
