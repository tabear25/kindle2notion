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
  var connectionSettings = document.getElementById("connection-settings");

  // Installed-app (PWA) entry points: shortcut auto-start, last run, install,
  // share target
  var autoStartNote = document.getElementById("auto-start-note");
  var autoStartText = document.getElementById("auto-start-text");
  var btnCancelAutoStart = document.getElementById("btn-cancel-auto-start");
  var lastRunLine = document.getElementById("last-run");
  var btnInstall = document.getElementById("btn-install");
  var shareNote = document.getElementById("share-note");
  var btnLastTitle = document.getElementById("btn-last-title");

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
    healthWaitStartedAt = 0; // new URL -> restart the cold-start grace period
    backendReady = false;
    checkBackendHealth(true); // supersede a probe still in flight against the old URL
  }

  // ----------------------------------------------------------------
  // Backend health probe
  //
  // Render's free plan sleeps after idle; /healthz both probes and wakes it.
  // But fetch() rejects the same way for a sleeping instance, a wrong URL, a
  // missing CORS entry and mixed content, so showing the wake-up text on every
  // failure left the banner stuck forever on a misconfiguration. Classify the
  // failure first and keep the wake-up wording only while it is plausible.
  // ----------------------------------------------------------------

  var HEALTH_RETRY_MS = 5000; // while the instance may still be waking up
  var HEALTH_SLOW_RETRY_MS = 15000; // after a diagnosed misconfiguration
  // Render holds the request open while a sleeping instance boots, and this
  // image (Playwright + Chromium + gunicorn) regularly needs far longer than
  // a few seconds — a short timeout would abort every wake-up attempt and
  // then misreport the backend as unreachable.
  var HEALTH_TIMEOUT_MS = 45000;
  // The reachability probe only asks "did anything answer?" — it must not eat
  // the wake-up budget the way a full-length deadline did, so it gets its own.
  var PROBE_TIMEOUT_MS = 10000;
  // A Playwright + Chromium + gunicorn image on the free plan regularly needs
  // several minutes; 240s expired mid-boot and flipped the wording to "broken"
  // while the instance was still perfectly healthy.
  var WAKE_GRACE_MS = 420000; // cold start budget before calling it broken
  var WAKING_TEXT = "バックエンドを起動中です（無料プランのためスリープ解除に1〜3分ほどかかります）...";

  var healthCheckTimer = null;
  var healthWaitStartedAt = 0;
  // A probe can stay open for HEALTH_TIMEOUT_MS. Resuming the app or saving
  // new settings starts another check, and the generation counter makes sure
  // a superseded probe can never overwrite the banner or re-arm a timer.
  var healthGeneration = 0;
  var healthProbeInFlight = false;
  // True once the backend answered; start/visibility logic relies on it.
  var backendReady = false;

  function setBanner(message, stateClass) {
    backendBanner.textContent = message;
    backendBanner.className = "result-box banner" + (stateClass ? " " + stateClass : "");
  }

  function hideBanner() {
    backendBanner.className = "result-box banner hidden";
  }

  function waitedSeconds() {
    return healthWaitStartedAt ? Math.round((Date.now() - healthWaitStartedAt) / 1000) : 0;
  }

  function stillWaking() {
    return healthWaitStartedAt > 0 && Date.now() - healthWaitStartedAt < WAKE_GRACE_MS;
  }

  // Problems that no amount of retrying can fix — report instead of polling.
  function apiBaseProblem(base) {
    if (!/^https?:\/\//i.test(base)) {
      return (
        "バックエンドURLの形式が正しくありません: " +
        base +
        "。接続設定に https://<サービス名>.onrender.com の形式で入力してください。"
      );
    }
    if (window.location.protocol === "https:" && /^http:\/\//i.test(base)) {
      return (
        "このページは HTTPS ですが、バックエンドURLが http:// です。ブラウザが通信をブロックするため、https:// のURLを設定してください。"
      );
    }
    return null;
  }

  // Tags its own abort: a request we cut off was accepted and left hanging
  // (the instance is booting), which is a different diagnosis from a request
  // the browser refused outright (wrong URL / CORS / offline).
  function withTimeout(run, timeoutMs) {
    var controller = typeof AbortController === "undefined" ? null : new AbortController();
    var timedOut = false;
    var timer = controller
      ? setTimeout(function () {
          timedOut = true;
          controller.abort();
        }, timeoutMs || HEALTH_TIMEOUT_MS)
      : null;

    function clear() {
      if (timer) {
        clearTimeout(timer);
      }
    }

    return run(controller ? controller.signal : undefined).then(
      function (value) {
        clear();
        return value;
      },
      function (error) {
        clear();
        if (timedOut) {
          var timeoutError = new Error("health probe timed out");
          timeoutError.timedOut = true;
          throw timeoutError;
        }
        throw error;
      }
    );
  }

  // Three-state on purpose. An opaque (mode: "no-cors") response proves only
  // that *something* answered — while an instance boots that something is
  // Render's router, not our app — whereas our own abort means the connection
  // was accepted and left hanging, which is a booting instance. Collapsing all
  // of this to a single false was what reported a waking backend as "gone".
  function probeReachable() {
    return withTimeout(function (signal) {
      return fetch(settings.apiBase + "/healthz", {
        mode: "no-cors",
        cache: "no-store",
        signal: signal,
      });
    }, PROBE_TIMEOUT_MS).then(
      function () {
        return "reachable";
      },
      function (error) {
        return error && error.timedOut ? "timeout" : "unreachable";
      }
    );
  }

  // /healthz proves the app is alive, but it is readable by every origin by
  // design — the API routes are not. So a *network-level* failure here (as
  // opposed to an HTTP status) is the real signature of a missing
  // CORS_ALLOWED_ORIGINS entry, and the only place that diagnosis is sound.
  //
  // Resolves to { problem, pipelineStatus }: problem is a banner or null, and
  // pipelineStatus is the backend's run state when it could be read — it tells
  // a freshly opened app whether a sync is already in progress.
  function verifyApiReachable() {
    return withTimeout(function (signal) {
      return apiFetch("/api/status", { signal: signal, cache: "no-store" });
    }, PROBE_TIMEOUT_MS).then(
      function (response) {
        if (response.status === 401 || response.status === 403) {
          return {
            problem: {
              text:
                "バックエンドには届いていますが、認証で拒否されました（HTTP " +
                response.status +
                "）。接続設定のユーザー名・パスワード（WEB_USERNAME / WEB_PASSWORD）を確認してください。",
              state: "error",
              retryMs: HEALTH_SLOW_RETRY_MS,
            },
            pipelineStatus: null,
          };
        }
        return readPipelineStatus(response).then(function (pipelineStatus) {
          return { problem: null, pipelineStatus: pipelineStatus };
        });
      },
      function (error) {
        if (error && error.timedOut) {
          // slow, not misconfigured — let the next poll decide
          return { problem: null, pipelineStatus: null };
        }
        return {
          problem: {
            text:
              "バックエンドは起動していますが、API 呼び出しが CORS でブロックされています。Render の環境変数 CORS_ALLOWED_ORIGINS に " +
              window.location.origin +
              " を（末尾スラッシュなしで）設定して再デプロイしてください。",
            state: "error",
            retryMs: HEALTH_SLOW_RETRY_MS,
          },
          pipelineStatus: null,
        };
      }
    );
  }

  function readPipelineStatus(response) {
    if (!response.ok) {
      return Promise.resolve(null);
    }
    return response.json().then(
      function (data) {
        return (data && data.status) || null;
      },
      function () {
        return null;
      }
    );
  }

  function bannerForStatus(status) {
    if (status === 401 || status === 403) {
      return {
        text:
          "バックエンドには届いていますが、認証で拒否されました（HTTP " +
          status +
          "）。接続設定のユーザー名・パスワード（WEB_USERNAME / WEB_PASSWORD）を確認してください。",
        state: "error",
        retryMs: HEALTH_SLOW_RETRY_MS,
      };
    }
    if (status === 404) {
      return {
        text:
          "バックエンドURLが違うようです（HTTP 404）。" +
          settings.apiBase +
          "/healthz が見つかりません。接続設定のURLを確認してください。",
        state: "error",
        retryMs: HEALTH_SLOW_RETRY_MS,
      };
    }
    // Reachable only when the failing response itself carries CORS headers.
    // Render's router does not add them to its own 502/503 wake-up pages, so
    // cross-origin cold starts land in bannerForNetworkFailure() instead.
    if (status === 502 || status === 503 || status === 504) {
      if (stillWaking()) {
        return {
          text: WAKING_TEXT + "（HTTP " + status + " / " + waitedSeconds() + "秒経過）",
          state: "",
          retryMs: HEALTH_RETRY_MS,
        };
      }
      return {
        text:
          "バックエンドが起動できていないようです（HTTP " +
          status +
          " が " +
          waitedSeconds() +
          "秒続いています）。Render のログでサービスの状態を確認してください。",
        state: "error",
        retryMs: HEALTH_SLOW_RETRY_MS,
      };
    }
    if (status >= 500) {
      return {
        text:
          "バックエンドがエラーを返しています（HTTP " +
          status +
          "）。Render のログを確認してください。",
        state: "error",
        retryMs: HEALTH_SLOW_RETRY_MS,
      };
    }
    return {
      text:
        "バックエンドが想定外の応答を返しました（HTTP " +
        status +
        "）。URLが別のサービスを指していないか確認してください。",
      state: "error",
      retryMs: HEALTH_SLOW_RETRY_MS,
    };
  }

  // Reached only when /healthz was not readable. Since /healthz always answers
  // `Access-Control-Allow-Origin: *`, that means the Flask app did not answer —
  // so this path is never a CORS misconfiguration, only a question of whether
  // anything is up yet. (verifyApiReachable() owns the CORS diagnosis.)
  function bannerForNetworkFailure(timedOut) {
    if (window.navigator && window.navigator.onLine === false) {
      return Promise.resolve({
        text: "端末がオフラインのようです。ネットワーク接続を確認してください。",
        state: "error",
        retryMs: HEALTH_RETRY_MS,
      });
    }
    if (timedOut) {
      // The request was accepted but never answered — a booting instance
      // looks exactly like this, so keep waiting rather than probing again.
      if (stillWaking()) {
        return Promise.resolve({
          text: WAKING_TEXT + "（応答待ち / " + waitedSeconds() + "秒経過）",
          state: "",
          retryMs: HEALTH_RETRY_MS,
        });
      }
      return Promise.resolve({
        text:
          "バックエンドから応答がありません（" +
          waitedSeconds() +
          "秒経過）。Render のログでサービスが起動できているかを確認してください。",
        state: "error",
        retryMs: HEALTH_SLOW_RETRY_MS,
      });
    }
    return probeReachable().then(function (result) {
      // Inside the cold-start budget every outcome means the same thing: the
      // instance has not finished booting. Say so instead of guessing a fault.
      if (stillWaking()) {
        return {
          text: WAKING_TEXT + "（" + waitedSeconds() + "秒経過）",
          state: "",
          retryMs: HEALTH_RETRY_MS,
        };
      }
      if (result === "reachable") {
        // Something answered, but /healthz was unreadable — so it was the
        // router in front of the app, and the app never came up behind it.
        return {
          text:
            "サーバーは応答していますが、バックエンドのアプリが起動していません（" +
            waitedSeconds() +
            "秒経過）。Render のログでビルドまたは起動が失敗していないか確認してください。",
          state: "error",
          retryMs: HEALTH_SLOW_RETRY_MS,
        };
      }
      if (result === "timeout") {
        return {
          text:
            "バックエンドから応答がありません（" +
            waitedSeconds() +
            "秒経過）。Render のログでサービスが起動できているかを確認してください。",
          state: "error",
          retryMs: HEALTH_SLOW_RETRY_MS,
        };
      }
      return {
        text:
          "バックエンドに接続できません（" +
          waitedSeconds() +
          "秒経過）。" +
          settings.apiBase +
          "/healthz をブラウザで直接開けるか、Render のサービスが停止していないかを確認してください。",
        state: "error",
        retryMs: HEALTH_SLOW_RETRY_MS,
      };
    });
  }

  function applyBanner(banner) {
    setBanner(banner.text, banner.state);
    backendReady = false;
    btnStart.disabled = true;
    if (banner.retryMs > 0) {
      healthCheckTimer = setTimeout(checkBackendHealth, banner.retryMs);
    }
  }

  // force: supersede a probe that is still in flight (new settings, or the
  // start button found the backend asleep). Without it a second check is
  // skipped, since the running probe will report anyway.
  function checkBackendHealth(force) {
    if (healthProbeInFlight && !force) {
      return;
    }
    if (healthCheckTimer) {
      clearTimeout(healthCheckTimer);
      healthCheckTimer = null;
    }
    var generation = ++healthGeneration;
    function isCurrent() {
      return generation === healthGeneration;
    }
    healthProbeInFlight = false;

    if (!settings.apiBase) {
      hideBanner();
      btnStart.disabled = false;
      checkSameOriginPipeline(isCurrent);
      return;
    }

    var problem = apiBaseProblem(settings.apiBase);
    if (problem) {
      applyBanner({ text: problem, state: "error", retryMs: 0 });
      return;
    }

    if (!healthWaitStartedAt) {
      healthWaitStartedAt = Date.now();
      // Only on the first attempt of a wait: on later polls the banner already
      // explains the cold start, and resetting it every cycle would hide that
      // for most of the wait (the probe itself takes far longer than a poll).
      setBanner("バックエンドの状態を確認しています...", "");
    }
    btnStart.disabled = true;
    healthProbeInFlight = true;

    withTimeout(function (signal) {
      // Deliberately not apiFetch: /healthz is unauthenticated server-side, and
      // attaching Authorization would turn this into a preflighted request. The
      // preflight is the first thing to break while the instance is still
      // booting, and its failure is unreadable from JS.
      return fetch(settings.apiBase + "/healthz", { signal: signal, cache: "no-store" });
    }).then(
      function (response) {
        if (!isCurrent()) {
          return undefined;
        }
        if (response.ok) {
          return verifyApiReachable().then(function (result) {
            if (!isCurrent()) {
              return;
            }
            healthProbeInFlight = false;
            if (result.problem) {
              applyBanner(result.problem);
              return;
            }
            healthWaitStartedAt = 0;
            setBanner("バックエンドに接続できました。", "ok");
            btnStart.disabled = false;
            healthCheckTimer = setTimeout(hideBanner, 2000);
            onBackendReady(result.pipelineStatus);
          });
        }
        healthProbeInFlight = false;
        applyBanner(bannerForStatus(response.status));
        return undefined;
      },
      function (error) {
        if (!isCurrent()) {
          return undefined;
        }
        return bannerForNetworkFailure(!!(error && error.timedOut)).then(function (banner) {
          if (!isCurrent()) {
            return;
          }
          healthProbeInFlight = false;
          applyBanner(banner);
        });
      }
    );
  }

  // Same-origin (Flask-served) mode has no wake-up dance, but a freshly
  // opened app still needs to know whether a sync is already running.
  function checkSameOriginPipeline(isCurrent) {
    withTimeout(function (signal) {
      return apiFetch("/api/status", { signal: signal, cache: "no-store" });
    }, PROBE_TIMEOUT_MS)
      .then(readPipelineStatus, function () {
        return null;
      })
      .then(function (pipelineStatus) {
        if (isCurrent()) {
          onBackendReady(pipelineStatus);
        }
      });
  }

  // Runs once per successful health check — the single place where a pending
  // shortcut start fires and a reopened app picks up a run in progress.
  function onBackendReady(pipelineStatus) {
    backendReady = true;
    loadLastRun();
    if (currentScreen !== "start") {
      return; // never yank the user out of the manual form or a result screen
    }
    if (pipelineStatus === "running" || pipelineStatus === "waiting_2fa") {
      clearAutoStart(); // the run the shortcut asked for is already going
      attachToRunningPipeline();
      return;
    }
    if (autoStartPending) {
      clearAutoStart();
      startPipeline();
    }
  }

  // The start button only makes sense once the backend has answered (or when
  // the UI is served by the backend itself).
  function startAllowed() {
    return !settings.apiBase || backendReady;
  }

  var currentScreen = "start";

  function showScreen(name) {
    currentScreen = name;
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
      // Progress resumes only after the login got past the code prompt, so a
      // 2fa_required replayed on reconnect (or on reopening the app) must not
      // leave the code dialog up over a run that has moved on.
      modal2fa.classList.remove("active");
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
      .then(
        function (response) {
          if (response.status === 409) {
            // Already running (a second tap, the shortcut fired twice, another
            // device): show that run instead of failing.
            startRetries = 0;
            attachToRunningPipeline();
            return undefined;
          }
          if (settings.apiBase && isWakingStatus(response.status)) {
            retryStartAfterWake();
            return undefined;
          }
          if (!response.ok) {
            return readStartError(response).then(function (message) {
              throw new Error(message);
            });
          }

          startRetries = 0;
          fullResync.checked = false; // one-shot option
          resetProgress();
          showScreen("progress");
          connectSSE();
          return undefined;
        },
        function (error) {
          if (settings.apiBase) {
            // Render idles out after 15 minutes, so an app left open (or
            // resumed from the background) often finds the backend asleep
            // again. Wake it and start once it answers instead of failing.
            retryStartAfterWake();
            return;
          }
          throw error;
        }
      )
      .catch(function (error) {
        alert(error.message);
      })
      .finally(function () {
        btnStart.disabled = !startAllowed();
        btnStart.textContent = "同期を開始";
      });
  }

  // Each failed start falls back to "wake, then start again". If the backend
  // keeps passing the health check but refusing the start, that loop must end.
  var MAX_START_RETRIES = 3;
  var startRetries = 0;

  function retryStartAfterWake() {
    if (startRetries >= MAX_START_RETRIES) {
      startRetries = 0;
      clearAutoStart();
      throw new Error(
        "バックエンドには接続できていますが、同期を開始できませんでした。少し時間をおいてから、もう一度お試しください。"
      );
    }
    startRetries += 1;
    waitForBackendThenStart();
  }

  // A tap on the button is a fresh attempt, not a continuation of retries.
  function startPipelineByUser() {
    startRetries = 0;
    startPipeline();
  }

  function isWakingStatus(status) {
    return status === 502 || status === 503 || status === 504;
  }

  function readStartError(response) {
    if (response.status === 401 || response.status === 403) {
      connectionSettings.open = true;
      return Promise.resolve(
        "認証で拒否されました（HTTP " +
          response.status +
          "）。接続設定のユーザー名・パスワード（WEB_USERNAME / WEB_PASSWORD）を確認してください。"
      );
    }
    return response.json().then(
      function (data) {
        return (data && data.error) || "同期を開始できませんでした（HTTP " + response.status + "）。";
      },
      function () {
        // Not the API's JSON: most likely a static host serving this page
        // without a backend behind it (Vercel before 接続設定 is saved).
        if (!settings.apiBase) {
          connectionSettings.open = true;
          return (
            "同期を開始できませんでした（HTTP " +
            response.status +
            "）。このページをバックエンドとは別のサーバー（Vercel など）で開いている場合は、下の「接続設定」でバックエンド URL を保存してください。"
          );
        }
        return "同期を開始できませんでした（HTTP " + response.status + "）。";
      }
    );
  }

  function waitForBackendThenStart() {
    backendReady = false;
    healthWaitStartedAt = 0; // a fresh cold start: restart the grace period
    requestAutoStart();
    checkBackendHealth(true);
  }

  // Reopening the app (or a 409 from /api/start) while the server is mid-run:
  // the SSE endpoint replays every event from the start, so the progress
  // screen catches up by itself — including a pending 2FA prompt.
  function attachToRunningPipeline() {
    resetProgress();
    setStatus("実行中の同期に接続しています...");
    showScreen("progress");
    connectSSE();
  }

  // ----------------------------------------------------------------
  // Auto-start (the 「Kindle同期」 home-screen shortcut)
  //
  // Render's free plan needs minutes to wake, so a one-tap sync cannot fire
  // immediately: the request waits for the health check and onBackendReady()
  // starts the run. The wait only advances while the app is visible (Android
  // throttles hidden pages), so the screen is kept on meanwhile. Once the run
  // has started it lives on the server and the app can be closed.
  // ----------------------------------------------------------------

  var autoStartPending = false;
  var wakeLock = null;
  var wakeLockRequested = false;

  function requestAutoStart() {
    autoStartPending = true;
    autoStartText.textContent =
      "バックエンドの準備ができ次第、自動で同期を開始します。開始まではこの画面を開いたままにしてください（開始後は閉じても処理は続きます）。";
    autoStartNote.classList.remove("hidden");
    acquireWakeLock();
  }

  function clearAutoStart() {
    autoStartPending = false;
    autoStartNote.classList.add("hidden");
    releaseWakeLock();
  }

  function acquireWakeLock() {
    if (wakeLock || wakeLockRequested || !navigator.wakeLock || document.visibilityState !== "visible") {
      return;
    }
    wakeLockRequested = true;
    navigator.wakeLock.request("screen").then(
      function (lock) {
        wakeLockRequested = false;
        if (!autoStartPending) {
          lock.release().catch(function () {});
          return;
        }
        wakeLock = lock;
        lock.addEventListener("release", function () {
          if (wakeLock === lock) {
            wakeLock = null; // the browser drops it whenever the app is hidden
          }
        });
      },
      function () {
        // Unsupported or refused: the wait still works, the screen may dim.
        wakeLockRequested = false;
      }
    );
  }

  function releaseWakeLock() {
    if (wakeLock) {
      var lock = wakeLock;
      wakeLock = null;
      lock.release().catch(function () {});
    }
  }

  // ----------------------------------------------------------------
  // Last run — the at-a-glance status a home-screen widget would show
  // ----------------------------------------------------------------

  function formatRunTime(iso) {
    var date = new Date(iso);
    if (isNaN(date.getTime())) {
      return iso || "";
    }
    return date.toLocaleString("ja-JP", {
      month: "numeric",
      day: "numeric",
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function describeRun(run) {
    var when = formatRunTime(run.finished_at);
    if (run.status === "done") {
      var counts = [];
      if (run.notion_added != null) {
        counts.push("Notion 新規 " + run.notion_added + " 件");
      }
      if (run.sheets_new_highlights != null) {
        counts.push("NotebookLM 新規 " + run.sheets_new_highlights + " 件");
      }
      return "前回の同期: " + when + " 完了" + (counts.length ? "（" + counts.join(" / ") + "）" : "");
    }
    var error = run.error ? String(run.error) : "";
    if (error.length > 80) {
      error = error.slice(0, 80) + "…";
    }
    return "前回の同期: " + when + " 失敗" + (error ? "（" + error + "）" : "");
  }

  function loadLastRun() {
    apiFetch("/api/runs", { cache: "no-store" })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (data) {
        var runs = (data && data.available && data.runs) || [];
        var latest = null;
        for (var i = 0; i < runs.length; i++) {
          // Skip runs without an end: one still in progress, or one cut off
          // by an instance restart, says nothing about the last result.
          if (runs[i].finished_at) {
            latest = runs[i];
            break;
          }
        }
        if (!latest) {
          lastRunLine.className = "last-run hidden";
          return;
        }
        lastRunLine.textContent = describeRun(latest);
        lastRunLine.className = "last-run" + (latest.status === "done" ? "" : " error");
      })
      .catch(function () {
        lastRunLine.className = "last-run hidden";
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
    if (startAllowed()) {
      loadLastRun(); // a run may have just finished
    }
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
    shareNote.classList.add("hidden");
    invalidatePreview();
    refreshLastTitleChip();
  }

  // The last book a highlight was added to. Highlights tend to arrive in a
  // run from the same book (one share per passage while reading), so offering
  // it saves retyping — as a one-tap choice, never pre-filled, so a highlight
  // can't land in the wrong book unnoticed.
  var LAST_TITLE_KEY = "k2n_last_manual_title";

  function refreshLastTitleChip() {
    var last = localStorage.getItem(LAST_TITLE_KEY) || "";
    if (!last || manualTitle.value.trim() === last) {
      btnLastTitle.classList.add("hidden");
      return;
    }
    btnLastTitle.textContent = "前回の本を使う: " + last;
    btnLastTitle.classList.remove("hidden");
  }

  function useLastTitle() {
    manualTitle.value = localStorage.getItem(LAST_TITLE_KEY) || "";
    manualMatches.innerHTML = "";
    invalidatePreview();
    refreshLastTitleChip();
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
    var appliedTitle = manualPreviewedPayload.title;
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
        localStorage.setItem(LAST_TITLE_KEY, appliedTitle);
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
    clearAutoStart(); // leaving the start screen cancels a pending shortcut start
    resetManual();
    showScreen("manual");
    manualTitle.focus();
  }

  // ----------------------------------------------------------------
  // Share target: 「共有」 from any Android app (Google Lens on a paper book,
  // a PDF reader, Play Books...) opens the manual form with the text filled in.
  // ----------------------------------------------------------------

  var URL_PATTERN = /https?:\/\/\S+/g;
  var CJK_PATTERN = /[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]/;

  // One shared passage is one highlight. OCR and PDF selections break the
  // text at every printed line, and the form treats each line as a separate
  // highlight, so the wrapped lines are joined back — with no space where
  // either side is Japanese, which is how the original text reads.
  function joinWrappedLines(text) {
    return text.replace(/\s*\n\s*/g, function (match, offset, whole) {
      var before = whole.charAt(offset - 1);
      var after = whole.charAt(offset + match.length);
      return CJK_PATTERN.test(before) || CJK_PATTERN.test(after) ? "" : " ";
    });
  }

  function sharedHighlightText(share) {
    // Apps put the selection in text; title (EXTRA_SUBJECT) is usually a page
    // or book name, so it is only a fallback. Links are never highlight text.
    var text = share.text || share.title || "";
    text = text.replace(/\r\n?/g, "\n").replace(URL_PATTERN, "");
    return joinWrappedLines(text).trim();
  }

  function openManualFromShare(share) {
    goToManual();
    var text = sharedHighlightText(share);
    if (text) {
      manualHighlights.value = text;
      shareNote.textContent =
        "共有されたテキストを 1 件のハイライトとして入力しました。複数に分けるときは改行で区切ってください。本のタイトルを決めたら「内容を確認」へ進みます。";
    } else {
      shareNote.textContent = "共有された内容から本文を取り出せませんでした。ハイライトを直接入力してください。";
    }
    shareNote.classList.remove("hidden");
  }

  // ----------------------------------------------------------------
  // Launch intents: manifest shortcuts (?action=sync|manual) and the share
  // target (?share_title / share_text / share_url). Read once, then removed
  // from the address bar so a reload never re-runs them.
  // ----------------------------------------------------------------

  function consumeLaunchParams() {
    var params = new URLSearchParams(window.location.search);
    var launch = { action: params.get("action") || "", share: null };
    if (params.has("share_text") || params.has("share_title") || params.has("share_url")) {
      launch.share = {
        title: params.get("share_title") || "",
        text: params.get("share_text") || "",
        url: params.get("share_url") || "",
      };
    }
    if (window.location.search) {
      window.history.replaceState(null, "", window.location.pathname + window.location.hash);
    }
    return launch;
  }

  // ----------------------------------------------------------------
  // Install as an app (Android Chrome turns this page into a WebAPK)
  // ----------------------------------------------------------------

  var deferredInstallPrompt = null;

  function isStandalone() {
    return !!(window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault(); // offer our own button instead of the mini-infobar
    deferredInstallPrompt = event;
    if (!isStandalone()) {
      btnInstall.classList.remove("hidden");
    }
  });

  window.addEventListener("appinstalled", function () {
    deferredInstallPrompt = null;
    btnInstall.classList.add("hidden");
  });

  btnInstall.addEventListener("click", function () {
    if (!deferredInstallPrompt) {
      return;
    }
    var promptEvent = deferredInstallPrompt;
    deferredInstallPrompt = null;
    btnInstall.classList.add("hidden");
    var shown = promptEvent.prompt();
    if (shown && shown.catch) {
      shown.catch(function () {}); // already used / dismissed: nothing to do
    }
  });

  // ----------------------------------------------------------------
  // Wiring
  // ----------------------------------------------------------------

  btnGoManual.addEventListener("click", goToManual);
  btnManualBack.addEventListener("click", goToStart);
  btnManualSearch.addEventListener("click", manualSearch);
  btnManualPreview.addEventListener("click", manualPreview);
  btnManualApply.addEventListener("click", manualApply);
  btnLastTitle.addEventListener("click", useLastTitle);
  manualTitle.addEventListener("input", function () {
    invalidatePreview();
    refreshLastTitleChip();
  });
  manualHighlights.addEventListener("input", invalidatePreview);
  manualPhysical.addEventListener("change", invalidatePreview);

  btnStart.addEventListener("click", startPipelineByUser);
  btnCancelAutoStart.addEventListener("click", clearAutoStart);
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
      startPipelineByUser();
    }
  });

  btnSaveSettings.addEventListener("click", saveSettings);

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible") {
      return;
    }
    if (autoStartPending) {
      acquireWakeLock(); // released by the browser while the app was hidden
    }
    // Android throttles timers in hidden apps, so a wake-up wait would only
    // resume at the next (late) poll. Check right away instead.
    if (settings.apiBase && !backendReady) {
      checkBackendHealth();
    }
  });

  var launch = consumeLaunchParams();
  loadSettingsForm();
  if (launch.share) {
    openManualFromShare(launch.share);
  } else if (launch.action === "manual") {
    goToManual();
  } else if (launch.action === "sync") {
    requestAutoStart();
  }
  checkBackendHealth();

  if ("serviceWorker" in navigator && window.isSecureContext) {
    navigator.serviceWorker.register("/sw.js").catch(function () {
      // Not installable without it, but the page itself works the same.
    });
  }
})();
