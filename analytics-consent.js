(() => {
  "use strict";

  const MEASUREMENT_ID = "G-ZPBQJ6137L";
  const STORAGE_KEY = "datalabx.analytics-consent.v1";
  const GRANTED = "granted";
  const DENIED = "denied";
  let analyticsLoaded = false;

  function readChoice() {
    try {
      const value = window.localStorage.getItem(STORAGE_KEY);
      return value === GRANTED || value === DENIED ? value : null;
    } catch (_) {
      return null;
    }
  }

  function saveChoice(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, value);
      return window.localStorage.getItem(STORAGE_KEY) === value;
    } catch (_) {
      return false;
    }
  }

  function loadAnalytics() {
    if (analyticsLoaded || readChoice() !== GRANTED) return;
    analyticsLoaded = true;

    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("consent", "default", {
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied",
      analytics_storage: "denied"
    });
    window.gtag("consent", "update", { analytics_storage: "granted" });
    window.gtag("js", new Date());
    window.gtag("config", MEASUREMENT_ID, {
      allow_google_signals: false,
      allow_ad_personalization_signals: false
    });

    const script = document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${MEASUREMENT_ID}`;
    script.dataset.dataLabAnalytics = "true";
    document.head.appendChild(script);
  }

  function createControls() {
    const panel = document.createElement("section");
    panel.className = "analytics-consent";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "アクセス解析の設定");
    panel.innerHTML = '<p>サイト改善のため、同意いただいた場合に限りGoogle Analyticsを使用します。広告用の保存領域とシグナルは使用しません。詳しくは<a href="/privacy.html">プライバシーポリシー</a>をご確認ください。</p><div class="analytics-consent__actions"><button type="button" class="analytics-consent__accept">アクセス解析を許可</button><button type="button" class="analytics-consent__deny">拒否して続ける</button></div>';
    document.body.appendChild(panel);

    const settings = document.createElement("button");
    settings.type = "button";
    settings.className = "analytics-settings";
    settings.textContent = "アクセス解析設定";
    const footer = document.querySelector("footer .container") || document.querySelector("footer");
    if (footer) footer.appendChild(settings);

    panel.querySelector(".analytics-consent__accept").addEventListener("click", () => {
      if (!saveChoice(GRANTED)) return;
      panel.hidden = true;
      loadAnalytics();
    });
    panel.querySelector(".analytics-consent__deny").addEventListener("click", () => {
      const wasLoaded = analyticsLoaded;
      saveChoice(DENIED);
      if (window.gtag) window.gtag("consent", "update", { analytics_storage: "denied" });
      panel.hidden = true;
      if (wasLoaded) window.location.reload();
    });
    settings.addEventListener("click", () => {
      panel.hidden = false;
      panel.querySelector("button").focus();
    });

    panel.hidden = readChoice() !== null;
  }

  document.addEventListener("DOMContentLoaded", () => {
    createControls();
    if (readChoice() === GRANTED) loadAnalytics();
  });
})();
