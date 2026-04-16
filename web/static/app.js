(function () {
  "use strict";

  var screens = {
    start: document.getElementById("screen-start"),
    progress: document.getElementById("screen-progress"),
    done: document.getElementById("screen-done"),
    error: document.getElementById("screen-error"),
  };

  var btnStart = document.getElementById("btn-start");
  var btnRestart = document.getElementById("btn-restart");
  var btnRetry = document.getElementById("btn-retry");
  var inputBooks = document.getElementById("max-books");

  var modal2fa = document.getElementById("modal-2fa");
  var input2fa = document.getElementById("input-2fa");
  var btn2fa = document.getElementById("btn-2fa");

  var globalStatus = document.getElementById("global-status");
  var doneMessage = document.getElementById("done-message");
  var errorMessage = document.getElementById("error-message");

  var eventSource = null;

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

  function closeSSE() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function connectSSE() {
    closeSSE();
    eventSource = new EventSource("/api/events");

    eventSource.addEventListener("progress", function (event) {
      var data = JSON.parse(event.data);
      updatePhase(data.phase, data.current, data.total, data.message);
    });

    eventSource.addEventListener("2fa_required", function () {
      modal2fa.classList.add("active");
      input2fa.value = "";
      input2fa.focus();
      setStatus("2段階認証コードの入力を待っています...");
    });

    eventSource.addEventListener("done", function (event) {
      var data = JSON.parse(event.data);

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
    });

    eventSource.addEventListener("pipeline_error", function (event) {
      var data = JSON.parse(event.data);
      modal2fa.classList.remove("active");
      errorMessage.textContent = data.message;
      setStatus("エラーが発生しました", "error");
      showScreen("error");
      closeSSE();
    });
  }

  function startPipeline() {
    var value = inputBooks.value.trim();
    var body = {};

    if (value) {
      body.max_books = value;
    }

    btnStart.disabled = true;
    btnStart.textContent = "開始中...";

    fetch("/api/start", {
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

    fetch("/api/2fa", {
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
})();
