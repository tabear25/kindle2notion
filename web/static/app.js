/* ============================================================
   kindle2notion web – frontend controller
   SSE client, 2FA modal, progress updates, screen transitions
   ============================================================ */

(function () {
  "use strict";

  // ---- DOM refs ----
  var screens = {
    start:    document.getElementById("screen-start"),
    progress: document.getElementById("screen-progress"),
    done:     document.getElementById("screen-done"),
    error:    document.getElementById("screen-error"),
  };

  var btnStart   = document.getElementById("btn-start");
  var btnRestart = document.getElementById("btn-restart");
  var btnRetry   = document.getElementById("btn-retry");
  var inputBooks = document.getElementById("max-books");

  var modal2fa   = document.getElementById("modal-2fa");
  var input2fa   = document.getElementById("input-2fa");
  var btn2fa     = document.getElementById("btn-2fa");

  var globalStatus = document.getElementById("global-status");
  var doneMessage  = document.getElementById("done-message");
  var errorMessage = document.getElementById("error-message");

  var eventSource = null;

  // ---- Screen management ----
  function showScreen(name) {
    Object.keys(screens).forEach(function (key) {
      screens[key].classList.toggle("active", key === name);
    });
  }

  // ---- Progress helpers ----
  function updatePhase(phase, current, total, message) {
    var bar    = document.getElementById("bar-" + phase);
    var count  = document.getElementById("count-" + phase);
    var status = document.getElementById("status-" + phase);
    if (!bar) return;

    if (total > 0) {
      bar.style.width = ((current / total) * 100).toFixed(1) + "%";
      count.textContent = current + " / " + total;
    }
    status.textContent = message;
    globalStatus.textContent = message;
  }

  function resetProgress() {
    ["scrape", "notion", "sheets"].forEach(function (phase) {
      var bar    = document.getElementById("bar-" + phase);
      var count  = document.getElementById("count-" + phase);
      var status = document.getElementById("status-" + phase);
      if (bar) bar.style.width = "0%";
      if (count) count.textContent = "";
      if (status) status.textContent = "";
    });
    globalStatus.textContent = "ログインしています...";
    globalStatus.className = "status-bar";
  }

  // ---- SSE ----
  function connectSSE() {
    if (eventSource) { eventSource.close(); }
    eventSource = new EventSource("/api/events");

    eventSource.addEventListener("started", function () {
      // pipeline started — already on progress screen
    });

    eventSource.addEventListener("progress", function (e) {
      var d = JSON.parse(e.data);
      updatePhase(d.phase, d.current, d.total, d.message);
    });

    eventSource.addEventListener("2fa_required", function () {
      modal2fa.classList.add("active");
      input2fa.value = "";
      input2fa.focus();
    });

    eventSource.addEventListener("done", function (e) {
      var d = JSON.parse(e.data);
      // Set all bars to 100 %
      ["scrape", "notion", "sheets"].forEach(function (phase) {
        var bar = document.getElementById("bar-" + phase);
        if (bar) bar.style.width = "100%";
      });
      globalStatus.textContent = "完了しました";
      globalStatus.className = "status-bar done";

      doneMessage.textContent = d.notes_count + " 件のハイライトを処理しました。";
      showScreen("done");
      closeSSE();
    });

    eventSource.addEventListener("error", function (e) {
      // SSE spec fires generic "error" on connection loss — check if it's ours
      if (e.data) {
        var d = JSON.parse(e.data);
        errorMessage.textContent = d.message;
        showScreen("error");
        closeSSE();
      }
    });

    eventSource.onerror = function () {
      // Connection lost — try to reconnect after a short delay
      // (The browser's built-in reconnect may also fire)
    };
  }

  function closeSSE() {
    if (eventSource) { eventSource.close(); eventSource = null; }
  }

  // ---- Start pipeline ----
  function startPipeline() {
    var value = inputBooks.value.trim();
    var body = {};
    if (value && parseInt(value, 10) > 0) {
      body.max_books = parseInt(value, 10);
    }

    btnStart.disabled = true;
    btnStart.textContent = "開始中...";

    fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(function (d) { throw new Error(d.error || "Failed to start"); });
        }
        resetProgress();
        showScreen("progress");
        connectSSE();
      })
      .catch(function (err) {
        alert(err.message);
      })
      .finally(function () {
        btnStart.disabled = false;
        btnStart.textContent = "同期を開始";
      });
  }

  // ---- Submit 2FA ----
  function submit2FA() {
    var code = input2fa.value.trim().replace(/\s/g, "");
    if (!code) return;

    btn2fa.disabled = true;
    btn2fa.textContent = "送信中...";

    fetch("/api/2fa", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: code }),
    })
      .then(function (res) {
        if (!res.ok) {
          return res.json().then(function (d) { throw new Error(d.error || "Failed"); });
        }
        modal2fa.classList.remove("active");
      })
      .catch(function (err) {
        alert(err.message);
      })
      .finally(function () {
        btn2fa.disabled = false;
        btn2fa.textContent = "コードを送信";
      });
  }

  // ---- Go back to start ----
  function goToStart() {
    closeSSE();
    inputBooks.value = "";
    showScreen("start");
  }

  // ---- Bind events ----
  btnStart.addEventListener("click", startPipeline);
  btnRestart.addEventListener("click", goToStart);
  btnRetry.addEventListener("click", goToStart);
  btn2fa.addEventListener("click", submit2FA);

  input2fa.addEventListener("keydown", function (e) {
    if (e.key === "Enter") submit2FA();
  });

  inputBooks.addEventListener("keydown", function (e) {
    if (e.key === "Enter") startPipeline();
  });
})();
