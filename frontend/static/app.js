(function () {
  "use strict";

  var screens = {
    start: document.getElementById("screen-start"),
    manual: document.getElementById("screen-manual"),
    progress: document.getElementById("screen-progress"),
    done: document.getElementById("screen-done"),
    error: document.getElementById("screen-error"),
  };

  var btnStart = document.getElementById("btn-start");
  var btnRestart = document.getElementById("btn-restart");
  var btnRetry = document.getElementById("btn-retry");
  var inputBooks = document.getElementById("max-books");

  // Manual-entry screen elements
  var btnGoManual = document.getElementById("btn-go-manual");
  var manualTitle = document.getElementById("manual-title");
  var manualHighlights = document.getElementById("manual-highlights");
  var manualPhysical = document.getElementById("manual-physical");
  var manualMatches = document.getElementById("manual-matches");
  var manualResult = document.getElementById("manual-result");
  var btnManualSearch = document.getElementById("btn-manual-search");
  var btnManualPreview = document.getElementById("btn-manual-preview");
  var btnManualApply = document.getElementById("btn-manual-apply");
  var btnManualBack = document.getElementById("btn-manual-back");

  var manualPreviewedPayload = null;

  var modal2fa = document.getElementById("modal-2fa");
  var input2fa = document.getElementById("input-2fa");
  var btn2fa = document.getElementById("btn-2fa");

  var globalStatus = document.getElementById("global-status");
  var doneMessage = document.getElementById("done-message");
  var errorMessage = document.getElementById("error-message");

  var fullResync = document.getElementById("full-resync");
  var backendBanner = document.getElementById("backend-banner");
  var apiBaseInput = document.getElementById("api-base");
  var apiUserInput = document.getElementById("api-user");
  var apiPassInput = document.getElementById("api-pass");
  var btnSaveSettings = document.getElementById("btn-save-settings");
  var settingsStatus = document.getElementById("settings-status");

  // ----------------------------------------------------------------
  // Backend connection
  //
  // Same-origin by default (API_BASE = ""): served from Flask, the browser
  // handles Basic auth natively and no extra header is sent. When this page
  // is hosted statically (Vercel), the user saves the Render URL + Basic
  // credentials once; they persist in localStorage and every request goes
  // out with an explicit Authorization header.
  // ----------------------------------------------------------------

  var settings = {
    apiBase: (localStorage.getItem("k2n_api_base") || "").replace(/\/+$/, ""),
    user: localStorage.getItem("k2n_api_user") || "",
    pass: localStorage.getItem("k2n_api_pass") || "",
  };

  function apiFetch(path, options) {
    options = options || {};
    var headers = {};
    Object.keys(options.headers || {}).forEach(function (key) {
      headers[key] = options.headers[key];
    });
    if (settings.apiBase && settings.user) {
      headers["Authorization"] = "Basic " + btoa(settings.user + ":" + settings.pass);
    }
    options.headers = headers;
    return fetch(settings.apiBase + path, options);
  }

  function loadSettingsForm() {
    apiBaseInput.value = settings.apiBase;
    apiUserInput.value = settings.user;
    apiPassInput.value = settings.pass;
  }

  function saveSettings() {
    settings.apiBase = apiBaseInput.value.trim().replace(/\/+$/, "");
    settings.user = apiUserInput.value.trim();
    settings.pass = apiPassInput.value;
    localStorage.setItem("k2n_api_base", settings.apiBase);
    localStorage.setItem("k2n_api_user", settings.user);
    localStorage.setItem("k2n_api_pass", settings.pass);
    settingsStatus.textContent = settings.apiBase
      ? "保存しました。バックエンド: " + settings.apiBase
      : "保存しました。このページと同じサーバーを使います。";
    checkBackendHealth();
  }

  // Render's free plan sleeps after idle; /healthz both probes and wakes it.
  var healthCheckTimer = null;

  function checkBackendHealth() {
    if (healthCheckTimer) {
      clearTimeout(healthCheckTimer);
      healthCheckTimer = null;
    }
    if (!settings.apiBase) {
      backendBanner.classList.add("hidden");
      btnStart.disabled = false;
      return;
    }
    backendBanner.classList.remove("hidden");
    backendBanner.textContent = "バックエンドの状態を確認しています...";
    btnStart.disabled = true;
    apiFetch("/healthz")
      .then(function (response) {
        if (!response.ok) {
          throw new Error("unhealthy");
        }
        backendBanner.textContent = "バックエンドに接続できました。";
        btnStart.disabled = false;
        healthCheckTimer = setTimeout(function () {
          backendBanner.classList.add("hidden");
        }, 2000);
      })
      .catch(function () {
        backendBanner.textContent =
          "バックエンドを起動中です（無料プランのためスリープ解除に最大1分ほどかかります）...";
        healthCheckTimer = setTimeout(checkBackendHealth, 5000);
      });
  }

  function showScreen(name) {
    Object.keys(screens).forEach(function (key) {
      screens[key].classList.toggle("active", key === name);
    });
  }

  function setStatus(message, stateClass) {
    globalStatus.textContent = message;
    globalStatus.className = "status-bar" + (stateClass ? " " + stateClass : "");
  }

  function updatePhase(phase, current, total, message) {
    var bar = document.getElementById("bar-" + phase);
    var count = document.getElementById("count-" + phase);
    var status = document.getElementById("status-" + phase);
    if (!bar || !count || !status) {
      return;
    }

    if (total > 0) {
      bar.style.width = ((current / total) * 100).toFixed(1) + "%";
      count.textContent = current + " / " + total;
    }

    status.textContent = message;
    setStatus(message);
  }

  function resetProgress() {
    ["scrape", "notion", "sheets"].forEach(function (phase) {
      var bar = document.getElementById("bar-" + phase);
      var count = document.getElementById("count-" + phase);
      var status = document.getElementById("status-" + phase);
      if (bar) {
        bar.style.width = "0%";
      }
      if (count) {
        count.textContent = "";
      }
      if (status) {
        status.textContent = "";
      }
    });

    setStatus("ログインを待っています...");
  }

  // ----------------------------------------------------------------
  // SSE over fetch
  //
  // EventSource cannot send an Authorization header, so the stream is read
  // through fetch + ReadableStream instead — identical frames, works both
  // same-origin and cross-origin. The server replays all events from index
  // 0 on every connection, so a 2s reconnect after an abnormal close is
  // lossless (the idempotent handlers simply re-render).
  // ----------------------------------------------------------------

  var sse = { active: false, controller: null };

  function closeSSE() {
    sse.active = false;
    if (sse.controller) {
      sse.controller.abort();
      sse.controller = null;
    }
  }

  function connectSSE() {
    closeSSE();
    sse.active = true;
    openEventStream();
  }

  function openEventStream() {
    if (!sse.active) {
      return;
    }
    var controller = new AbortController();
    sse.controller = controller;

    apiFetch("/api/events", { signal: controller.signal })
      .then(function (response) {
        if (!response.ok || !response.body) {
          throw new Error("stream unavailable");
        }
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";

        function pump() {
          return reader.read().then(function (chunk) {
            if (chunk.done) {
              scheduleReconnect();
              return;
            }
            buffer += decoder.decode(chunk.value, { stream: true });
            var frames = buffer.split("\n\n");
            buffer = frames.pop();
            frames.forEach(handleSSEFrame);
            return pump();
          });
        }

        return pump();
      })
      .catch(function () {
        scheduleReconnect();
      });
  }

  function scheduleReconnect() {
    if (!sse.active) {
      return; // closed deliberately after done / pipeline_error
    }
    setTimeout(openEventStream, 2000);
  }

  function handleSSEFrame(frame) {
    var eventType = "message";
    var dataLines = [];
    frame.split("\n").forEach(function (line) {
      if (line.indexOf("event:") === 0) {
        eventType = line.slice(6).trim();
      } else if (line.indexOf("data:") === 0) {
        dataLines.push(line.slice(5).trim());
      }
      // lines starting with ":" are keep-alive comments — ignored
    });
    if (dataLines.length === 0 && eventType === "message") {
      return;
    }
    var data = {};
    try {
      data = JSON.parse(dataLines.join("\n") || "{}");
    } catch (error) {
      data = {};
    }
    dispatchSSEEvent(eventType, data);
  }

  function dispatchSSEEvent(eventType, data) {
    if (eventType === "progress") {
      updatePhase(data.phase, data.current, data.total, data.message);
    } else if (eventType === "2fa_required") {
      modal2fa.classList.add("active");
      input2fa.value = "";
      input2fa.focus();
      setStatus("2段階認証コードの入力を待っています...");
    } else if (eventType === "done") {
      ["scrape", "notion", "sheets"].forEach(function (phase) {
        var bar = document.getElementById("bar-" + phase);
        if (bar) {
          bar.style.width = "100%";
        }
      });
      setStatus("同期が完了しました", "done");
      doneMessage.textContent = data.notes_count + " 件のハイライトを処理しました。";
      modal2fa.classList.remove("active");
      showScreen("done");
      closeSSE();
    } else if (eventType === "pipeline_error") {
      modal2fa.classList.remove("active");
      errorMessage.textContent = data.message;
      setStatus("エラーが発生しました", "error");
      showScreen("error");
      closeSSE();
    }
  }

  function startPipeline() {
    var value = inputBooks.value.trim();
    var body = {};

    if (value) {
      body.max_books = value;
    }
    if (fullResync.checked) {
      body.full_resync = true;
    }

    btnStart.disabled = true;
    btnStart.textContent = "開始中...";

    apiFetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (data) {
            throw new Error(data.error || "同期を開始できませんでした。");
          });
        }

        fullResync.checked = false; // one-shot option
        resetProgress();
        showScreen("progress");
        connectSSE();
      })
      .catch(function (error) {
        alert(error.message);
      })
      .finally(function () {
        btnStart.disabled = false;
        btnStart.textContent = "同期を開始";
      });
  }

  function submit2FA() {
    var code = input2fa.value.trim().replace(/\s/g, "");
    if (!code) {
      return;
    }

    btn2fa.disabled = true;
    btn2fa.textContent = "送信中...";

    apiFetch("/api/2fa", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: code }),
    })
      .then(function (response) {
        if (!response.ok) {
          return response.json().then(function (data) {
            throw new Error(data.error || "コードを送信できませんでした。");
          });
        }

        modal2fa.classList.remove("active");
        setStatus("認証コードを送信しました。続行を待っています...");
      })
      .catch(function (error) {
        alert(error.message);
      })
      .finally(function () {
        btn2fa.disabled = false;
        btn2fa.textContent = "コードを送信";
      });
  }

  function goToStart() {
    closeSSE();
    modal2fa.classList.remove("active");
    inputBooks.value = "";
    input2fa.value = "";
    showScreen("start");
  }

  // ----------------------------------------------------------------
  // Manual (non-Kindle) highlight entry
  // ----------------------------------------------------------------

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  function setManualResult(text, stateClass) {
    manualResult.textContent = text || "";
    manualResult.className = "result-box" + (stateClass ? " " + stateClass : "");
  }

  function invalidatePreview() {
    // Any edit means the previewed payload no longer matches the form.
    manualPreviewedPayload = null;
    btnManualApply.classList.add("hidden");
  }

  function resetManual() {
    manualTitle.value = "";
    manualHighlights.value = "";
    manualPhysical.checked = false;
    manualMatches.innerHTML = "";
    setManualResult("");
    invalidatePreview();
  }

  function readHighlightLines() {
    return manualHighlights.value
      .split("\n")
      .map(function (line) { return line.trim(); })
      .filter(function (line) { return line.length > 0; });
  }

  function buildManualPayload(apply) {
    var payload = {
      title: manualTitle.value.trim(),
      highlights: readHighlightLines(),
      apply: apply,
    };
    if (manualPhysical.checked) {
      payload.source = "physical";
    }
    return payload;
  }

  function renderMatches(data) {
    manualMatches.innerHTML = "";
    if (data.sheets_configured === false) {
      manualMatches.innerHTML =
        '<p class="match-note">Google Sheets が未設定のため候補検索は使えません。' +
        'タイトルの表記を正確に入力してください。</p>';
      return;
    }
    var matches = data.matches_for_title || [];
    if (matches.length === 0) {
      manualMatches.innerHTML =
        '<p class="match-note">一致する既存の本は見つかりませんでした。新しい本として登録されます。</p>';
      return;
    }
    var note = document.createElement("p");
    note.className = "match-note";
    note.textContent = "この本ですか？ タップすると正式タイトルを採用します。";
    manualMatches.appendChild(note);

    matches.forEach(function (match) {
      var item = document.createElement("div");
      item.className = "match-item";
      item.innerHTML =
        "<span>" + escapeHtml(match.title) + "</span>" +
        '<span class="match-score">' +
        (match.is_exact_normalized ? "完全一致" : "類似 " + Math.round(match.score * 100) + "%") +
        "</span>";
      item.addEventListener("click", function () {
        manualTitle.value = match.title;
        invalidatePreview();
        var nodes = manualMatches.querySelectorAll(".match-item");
        for (var i = 0; i < nodes.length; i++) {
          nodes[i].classList.remove("selected");
        }
        item.classList.add("selected");
      });
      manualMatches.appendChild(item);
    });
  }

  function manualSearch() {
    var title = manualTitle.value.trim();
    if (!title) {
      manualMatches.innerHTML =
        '<p class="match-note">先に本のタイトルを入力してください。</p>';
      return;
    }
    btnManualSearch.disabled = true;
    btnManualSearch.textContent = "検索中...";
    apiFetch("/api/manual/books?title=" + encodeURIComponent(title))
      .then(function (response) {
        if (!response.ok) {
          throw new Error("候補の検索に失敗しました。");
        }
        return response.json();
      })
      .then(renderMatches)
      .catch(function (error) {
        manualMatches.innerHTML =
          '<p class="match-note">' + escapeHtml(error.message) + "</p>";
      })
      .finally(function () {
        btnManualSearch.disabled = false;
        btnManualSearch.textContent = "既存の本を検索（この本ですか？）";
      });
  }

  function describePlan(data) {
    var lines = ["追加予定: " + data.books + " 冊 / " + data.highlights + " ハイライト",
      "保存先: " + (data.targets || []).join(" + ")];
    (data.plan || []).forEach(function (book) {
      lines.push("・" + book.title + "（" + book.highlights + " 件, source=" + book.source + "）");
    });
    return lines.join("\n");
  }

  function describeResult(data) {
    var lines = [];
    if (data.notion) {
      lines.push("[Notion] 追加 " + data.notion.added +
        " / 重複スキップ " + data.notion.skipped +
        " / 失敗 " + data.notion.failed);
    }
    if (data.sheets) {
      if (data.sheets.not_configured) {
        lines.push("[Google Sheets] 未設定のためスキップ");
      } else {
        lines.push("[Google Sheets] 新規本 " + data.sheets.new_books +
          " / 新規ハイライト " + data.sheets.new_highlights +
          " / 重複スキップ " + data.sheets.skipped_duplicates);
      }
    }
    if (data.problems && data.problems.length) {
      lines.push("⚠ " + data.problems.join("; "));
    }
    return lines.join("\n");
  }

  function manualPreview() {
    var payload = buildManualPayload(false);
    if (!payload.title) {
      setManualResult("本のタイトルを入力してください。", "error");
      return;
    }
    if (payload.highlights.length === 0) {
      setManualResult("ハイライトを1件以上入力してください。", "error");
      return;
    }
    btnManualPreview.disabled = true;
    btnManualPreview.textContent = "確認中...";
    apiFetch("/api/manual/highlights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            throw new Error(data.error || "確認に失敗しました。");
          }
          return data;
        });
      })
      .then(function (data) {
        setManualResult("以下の内容を追加します。よろしければ「追加する」を押してください。\n\n" +
          describePlan(data));
        manualPreviewedPayload = buildManualPayload(true);
        btnManualApply.classList.remove("hidden");
      })
      .catch(function (error) {
        setManualResult(error.message, "error");
        invalidatePreview();
      })
      .finally(function () {
        btnManualPreview.disabled = false;
        btnManualPreview.textContent = "内容を確認";
      });
  }

  function manualApply() {
    if (!manualPreviewedPayload) {
      setManualResult("先に「内容を確認」を押してください。", "error");
      return;
    }
    btnManualApply.disabled = true;
    btnManualApply.textContent = "追加中...";
    apiFetch("/api/manual/highlights", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(manualPreviewedPayload),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            throw new Error(data.error || "追加に失敗しました。");
          }
          return data;
        });
      })
      .then(function (data) {
        if (data.ok) {
          setManualResult("追加が完了しました。\n\n" + describeResult(data), "ok");
          manualHighlights.value = "";
          invalidatePreview();
        } else {
          setManualResult("一部が追加できませんでした。\n\n" + describeResult(data), "error");
        }
      })
      .catch(function (error) {
        setManualResult(error.message, "error");
      })
      .finally(function () {
        btnManualApply.disabled = false;
        btnManualApply.textContent = "この内容で追加する";
      });
  }

  function goToManual() {
    resetManual();
    showScreen("manual");
    manualTitle.focus();
  }

  btnGoManual.addEventListener("click", goToManual);
  btnManualBack.addEventListener("click", goToStart);
  btnManualSearch.addEventListener("click", manualSearch);
  btnManualPreview.addEventListener("click", manualPreview);
  btnManualApply.addEventListener("click", manualApply);
  manualTitle.addEventListener("input", invalidatePreview);
  manualHighlights.addEventListener("input", invalidatePreview);
  manualPhysical.addEventListener("change", invalidatePreview);

  btnStart.addEventListener("click", startPipeline);
  btnRestart.addEventListener("click", goToStart);
  btnRetry.addEventListener("click", goToStart);
  btn2fa.addEventListener("click", submit2FA);

  input2fa.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      submit2FA();
    }
  });

  inputBooks.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      startPipeline();
    }
  });

  btnSaveSettings.addEventListener("click", saveSettings);

  loadSettingsForm();
  checkBackendHealth();
})();
