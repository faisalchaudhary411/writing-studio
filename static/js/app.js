/* ══════════════════════════════════════════════════════════════════════
   QALAM STUDIO — Frontend Engine
   Toast system · Magnetic UI · AJAX Generation
   ══════════════════════════════════════════════════════════════════════ */

(function() {
  "use strict";

  // ── Toast System ──
  const Toast = {
    container: null,
    init() {
      this.container = document.createElement("div");
      this.container.className = "toast-container";
      document.body.appendChild(this.container);
    },
    show(message, type = "info", duration = 4000) {
      if (!this.container) this.init();
      const toast = document.createElement("div");
      toast.className = `toast ${type}`;
      const icons = { success: "✓", error: "✕", info: "ℹ" };
      toast.innerHTML = `
        <span class="toast-icon">${icons[type] || "ℹ"}</span>
        <span>${message}</span>
        <button class="toast-close">&times;</button>
      `;
      toast.querySelector(".toast-close").addEventListener("click", () => this.dismiss(toast));
      this.container.appendChild(toast);
      setTimeout(() => this.dismiss(toast), duration);
    },
    dismiss(toast) {
      toast.style.animation = "slideInRight 0.3s ease reverse";
      setTimeout(() => toast.remove(), 300);
    }
  };

  // ── Modal System ──
  const Modal = {
    open(id) {
      const el = document.getElementById(id);
      if (el) el.classList.add("active");
    },
    close(id) {
      const el = document.getElementById(id);
      if (el) el.classList.remove("active");
    },
    init() {
      document.querySelectorAll(".modal-overlay").forEach(overlay => {
        overlay.addEventListener("click", e => {
          if (e.target === overlay) overlay.classList.remove("active");
        });
      });
    }
  };

  // ── Navigation Scroll Effect ──
  function initNavScroll() {
    const nav = document.querySelector(".nav-floating");
    if (!nav) return;
    window.addEventListener("scroll", () => {
      nav.classList.toggle("scrolled", window.scrollY > 50);
    });
  }

  // ── Mobile Nav ──
  function initMobileNav() {
    const toggle = document.querySelector(".nav-mobile-toggle");
    const links = document.querySelector(".nav-links");
    if (!toggle || !links) return;
    toggle.addEventListener("click", () => {
      links.classList.toggle("mobile-open");
    });
    // Close mobile nav when clicking a link
    links.querySelectorAll(".nav-link").forEach(link => {
      link.addEventListener("click", () => {
        links.classList.remove("mobile-open");
      });
    });
  }

  // ── Tabs ──
  function initTabs() {
    document.querySelectorAll(".tabs").forEach(tabContainer => {
      const buttons = tabContainer.querySelectorAll(".tab-btn");
      const panels = tabContainer.parentElement.querySelectorAll(".tab-panel");
      buttons.forEach((btn, idx) => {
        btn.addEventListener("click", () => {
          buttons.forEach(b => b.classList.remove("active"));
          panels.forEach(p => p.classList.remove("active"));
          btn.classList.add("active");
          if (panels[idx]) panels[idx].classList.add("active");
        });
      });
      // Activate first tab
      if (buttons.length) buttons[0].click();
    });
  }

  // ── Scroll Reveal ──
  function initReveal() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
        }
      });
    }, { threshold: 0.1 });
    document.querySelectorAll(".reveal").forEach(el => observer.observe(el));
  }

  // ── Copy to Clipboard ──
  function initCopyButtons() {
    document.querySelectorAll(".copy-btn, [data-copy]").forEach(btn => {
      btn.addEventListener("click", () => {
        const target = document.querySelector(btn.dataset.copy);
        const text = target ? target.textContent : btn.dataset.text;
        navigator.clipboard.writeText(text).then(() => {
          Toast.show("Copied to clipboard!", "success");
        });
      });
    });
  }

  // ── API Helper ──
  async function api(endpoint, data, method = "POST") {
    const headers = { "Content-Type": "application/json" };
    // CSRF: only present (and only needed) on admin-authenticated pages —
    // the meta tag is only rendered when logged into /admin. Harmless no-op
    // on public pages where the endpoint doesn't check for it.
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (csrfMeta) headers["X-CSRF-Token"] = csrfMeta.content;
    const opts = { method, headers };
    if (method === "POST" && data) opts.body = JSON.stringify(data);
    try {
      const res = await fetch(endpoint, opts);
      const json = await res.json();
      if (!res.ok && json.error) throw new Error(json.error);
      return json;
    } catch (err) {
      Toast.show(err.message, "error");
      throw err;
    }
  }

  // ── Check remaining daily actions before showing an ad ──
  // BUG FIX: previously every tool button showed the 5s interstitial ad
  // BEFORE checking whether the user had any actions left, so someone who'd
  // already hit their daily limit would sit through the ad only to then see
  // "Daily limit reached" anyway. This checks first.
  async function hasActionsLeft() {
    if (window.IS_PRO) return true;
    try {
      const res = await fetch("/api/actions-left");
      const data = await res.json();
      if (!data.is_pro && data.left <= 0) {
        Toast.show("Daily limit reached. Upgrade to Pro for unlimited access.", "error");
        return false;
      }
      return true;
    } catch (e) {
      return true; // fail open — don't block the user on a network hiccup
    }
  }

  // ── License Key Management ──
  function initLicenseSystem() {
    // Restore from localStorage on load
    const storedKey = localStorage.getItem("qalam_pro_key");
    if (storedKey && !window.IS_PRO) {
      api("/api/restore-pro", { key: storedKey }).then(r => {
        if (r.success) location.reload();
      }).catch(() => {});
    }

    // Activate
    const activateBtn = document.getElementById("activate-license-btn");
    const activateInput = document.getElementById("license-key-input");
    if (activateBtn && activateInput) {
      activateBtn.addEventListener("click", () => {
        const key = activateInput.value.trim();
        if (!key) return Toast.show("Enter a license key", "error");
        activateBtn.disabled = true;
        activateBtn.textContent = "Activating...";
        api("/api/activate-license", { key }).then(r => {
          if (r.valid) {
            localStorage.setItem("qalam_pro_key", key);
            Toast.show("Pro activated!", "success");
            setTimeout(() => location.reload(), 800);
          } else {
            Toast.show(r.error || "Invalid key", "error");
          }
        }).finally(() => {
          activateBtn.disabled = false;
          activateBtn.textContent = "Activate License";
        });
      });
    }

    // Deactivate
    const deactivateBtn = document.getElementById("deactivate-pro-btn");
    if (deactivateBtn) {
      deactivateBtn.addEventListener("click", () => {
        api("/api/deactivate-pro", {}).then(() => {
          localStorage.removeItem("qalam_pro_key");
          Toast.show("Pro deactivated", "info");
          setTimeout(() => location.reload(), 500);
        });
      });
    }
  }

  // ── Urdu Writer ──
  function initUrduWriter() {
    const btn = document.getElementById("generate-urdu-btn");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const topic = document.getElementById("urdu-topic").value.trim();
      if (!topic) return Toast.show("Enter a topic", "error");
      const output = document.getElementById("urdu-output");
      const langStyle = document.getElementById("urdu-lang").value;
      if (!(await hasActionsLeft())) return;
      btn.disabled = true;
      btn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
      if (shouldShowAd()) await showInterstitialAd();
      try {
        const res = await api("/api/generate-urdu", {
          content_type: document.getElementById("urdu-type").value,
          tone: document.getElementById("urdu-tone").value,
          lang_style: langStyle,
          word_count: document.getElementById("urdu-length").value,
          topic
        });
        output.textContent = res.result;
        output.className = "output-box " + (langStyle === "Roman Urdu" ? "ltr" : "urdu");
        output.style.display = "block";
        if (res.warning) Toast.show(res.warning, "error", 7000);
        updateActionsLeft();
      } finally {
        btn.disabled = false;
        btn.textContent = "✍️ Generate Urdu Content";
      }
    });
  }

  // ── Freelancer Toolkit ──
  function initFreelancer() {
    // Proposal
    const propBtn = document.getElementById("generate-proposal-btn");
    if (propBtn) {
      propBtn.addEventListener("click", async () => {
        const service = document.getElementById("prop-service").value.trim();
        const need = document.getElementById("prop-need").value.trim();
        if (!service || !need) return Toast.show("Fill all required fields", "error");
        const lang = document.getElementById("prop-lang").value;
        if (!(await hasActionsLeft())) return;
        propBtn.disabled = true;
        propBtn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
        if (shouldShowAd()) await showInterstitialAd();
        try {
          const res = await api("/api/generate-proposal", {
            platform: document.getElementById("prop-platform").value,
            service, client_need: need,
            your_exp: document.getElementById("prop-exp").value,
            prop_lang: lang
          });
          const out = document.getElementById("proposal-output");
          out.textContent = res.result;
          out.className = "output-box " + (lang === "Pure Urdu" ? "urdu" : "ltr");
          out.style.display = "block";
          if (res.warning) Toast.show(res.warning, "error", 7000);
          updateActionsLeft();
        } finally {
          propBtn.disabled = false;
          propBtn.textContent = "📝 Generate Proposal";
        }
      });
    }

    // Invoice
    const invBtn = document.getElementById("generate-invoice-btn");
    if (invBtn) {
      invBtn.addEventListener("click", async () => {
        const items = [];
        document.querySelectorAll(".invoice-item").forEach(row => {
          const desc = row.querySelector(".inv-desc").value.trim();
          const qty = parseInt(row.querySelector(".inv-qty").value) || 0;
          const rate = parseInt(row.querySelector(".inv-rate").value) || 0;
          if (desc) items.push({ desc, qty, rate });
        });
        if (!items.length) return Toast.show("Add at least one item", "error");
        invBtn.disabled = true;
        try {
          const res = await api("/api/generate-invoice", {
            items,
            your_name: document.getElementById("inv-yname").value,
            your_email: document.getElementById("inv-yemail").value,
            your_phone: document.getElementById("inv-yphone").value,
            client_name: document.getElementById("inv-cname").value,
            client_email: document.getElementById("inv-cemail").value,
            date: document.getElementById("inv-date").value,
            currency: document.getElementById("inv-currency").value,
            note: document.getElementById("inv-note").value
          });
          const out = document.getElementById("invoice-output");
          out.textContent = res.result;
          out.style.display = "block";
          updateActionsLeft();
        } finally {
          invBtn.disabled = false;
        }
      });
    }

    // Add invoice item
    const addItemBtn = document.getElementById("add-invoice-item");
    if (addItemBtn) {
      addItemBtn.addEventListener("click", () => {
        const container = document.getElementById("invoice-items");
        const idx = container.children.length + 1;
        const div = document.createElement("div");
        div.className = "invoice-item grid-3 gap-1 mt-1";
        div.innerHTML = `
          <input type="text" class="form-input inv-desc" placeholder="Item #${idx}">
          <input type="number" class="form-input inv-qty" value="1" min="1">
          <input type="number" class="form-input inv-rate" value="0" min="0" step="100">
        `;
        container.appendChild(div);
      });
    }

    // Email
    const emailBtn = document.getElementById("generate-email-btn");
    if (emailBtn) {
      emailBtn.addEventListener("click", async () => {
        const ctx = document.getElementById("email-ctx").value.trim();
        if (!ctx) return Toast.show("Enter context", "error");
        const lang = document.getElementById("email-lang").value;
        if (!(await hasActionsLeft())) return;
        emailBtn.disabled = true;
        emailBtn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
        if (shouldShowAd()) await showInterstitialAd();
        try {
          const res = await api("/api/generate-email", {
            etype: document.getElementById("email-type").value,
            ectx: ctx,
            elang: lang,
            etone: document.getElementById("email-tone").value
          });
          const out = document.getElementById("email-output");
          out.textContent = res.result;
          out.className = "output-box " + (lang === "Pure Urdu" ? "urdu" : "ltr");
          out.style.display = "block";
          if (res.warning) Toast.show(res.warning, "error", 7000);
          updateActionsLeft();
        } finally {
          emailBtn.disabled = false;
          emailBtn.textContent = "📧 Generate Email";
        }
      });
    }
  }

  // ── Subtitles ──
  function initSubtitles() {
    // Script to SRT
    const srtBtn = document.getElementById("generate-srt-btn");
    if (srtBtn) {
      srtBtn.addEventListener("click", async () => {
        const script = document.getElementById("sub-script").value.trim();
        if (!script) return Toast.show("Paste your script", "error");
        if (!(await hasActionsLeft())) return;
        srtBtn.disabled = true;
        srtBtn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
        if (shouldShowAd()) await showInterstitialAd();
        try {
          const res = await api("/api/generate-srt", {
            script,
            dur: parseInt(document.getElementById("sub-dur").value),
            slang: document.getElementById("sub-lang").value,
            wps: parseInt(document.getElementById("sub-wps").value)
          });
          const out = document.getElementById("srt-output");
          out.value = res.result;
          out.parentElement.style.display = "block";
          updateActionsLeft();
        } finally {
          srtBtn.disabled = false;
          srtBtn.textContent = "🎬 Generate SRT";
        }
      });
    }

    // Translate SRT
    const transBtn = document.getElementById("translate-srt-btn");
    if (transBtn) {
      transBtn.addEventListener("click", async () => {
        const srt = document.getElementById("eng-srt").value.trim();
        if (!srt) return Toast.show("Paste English SRT", "error");
        if (!(await hasActionsLeft())) return;
        transBtn.disabled = true;
        transBtn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
        if (shouldShowAd()) await showInterstitialAd();
        try {
          const res = await api("/api/translate-srt", {
            eng_srt: srt,
            tstyle: document.getElementById("trans-style").value
          });
          const out = document.getElementById("trans-output");
          out.value = res.result;
          out.parentElement.style.display = "block";
          updateActionsLeft();
        } finally {
          transBtn.disabled = false;
          transBtn.textContent = "🔄 Translate to Urdu";
        }
      });
    }
  }

  // ── Urdu Proofreader ──
  function initProofread() {
    const btn = document.getElementById("proofread-btn");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const text = document.getElementById("proof-text").value.trim();
      if (!text) return Toast.show("Paste some text to proofread", "error");
      const lang = document.getElementById("proof-lang").value;
      if (!(await hasActionsLeft())) return;
      btn.disabled = true;
      btn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
      if (shouldShowAd()) await showInterstitialAd();
      try {
        const res = await api("/api/proofread", {
          text,
          lang,
          focus: document.getElementById("proof-focus").value
        });
        const out = document.getElementById("proof-output");
        out.textContent = res.result;
        out.className = "output-box " + (lang === "Roman Urdu" ? "ltr" : "urdu");
        out.style.display = "block";
        const dl = document.getElementById("download-proof-btn");
        if (dl) dl.style.display = "inline-flex";
        if (res.warning) Toast.show(res.warning, "error", 7000);
        updateActionsLeft();
      } finally {
        btn.disabled = false;
        btn.textContent = "🔍 Proofread Text";
      }
    });
  }

  // ── YouTube SEO ──
  function initYoutubeSeo() {
    const btn = document.getElementById("generate-yt-btn");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const topic = document.getElementById("yt-topic").value.trim();
      if (!topic) return Toast.show("Enter a video topic or summary", "error");
      const lang = document.getElementById("yt-lang").value;
      if (!(await hasActionsLeft())) return;
      btn.disabled = true;
      btn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
      if (shouldShowAd()) await showInterstitialAd();
      try {
        const res = await api("/api/generate-youtube-seo", {
          topic,
          lang,
          niche: document.getElementById("yt-niche").value,
          channel: document.getElementById("yt-channel").value.trim()
        });
        const out = document.getElementById("yt-output");
        out.textContent = res.result;
        out.className = "output-box " + (lang === "Pure Urdu (اردو)" ? "urdu" : "ltr");
        out.style.display = "block";
        const dl = document.getElementById("download-yt-btn");
        if (dl) dl.style.display = "inline-flex";
        if (res.warning) Toast.show(res.warning, "error", 7000);
        updateActionsLeft();
      } finally {
        btn.disabled = false;
        btn.textContent = "🚀 Generate Titles, Description & Tags";
      }
    });
  }

  // ── Resume / CV Builder ──
  function initResume() {
    const btn = document.getElementById("generate-cv-btn");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const name = document.getElementById("cv-name").value.trim();
      const role = document.getElementById("cv-role").value.trim();
      if (!name || !role) return Toast.show("Name and target role are required", "error");
      const lang = document.getElementById("cv-lang").value;
      if (!(await hasActionsLeft())) return;
      btn.disabled = true;
      btn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
      if (shouldShowAd()) await showInterstitialAd();
      try {
        const res = await api("/api/generate-resume", {
          name,
          role,
          email: document.getElementById("cv-email").value.trim(),
          phone: document.getElementById("cv-phone").value.trim(),
          location: document.getElementById("cv-location").value.trim(),
          lang,
          summary: document.getElementById("cv-summary").value.trim(),
          experience: document.getElementById("cv-experience").value.trim(),
          education: document.getElementById("cv-education").value.trim(),
          skills: document.getElementById("cv-skills").value.trim(),
          extra: document.getElementById("cv-extra").value.trim()
        });
        const out = document.getElementById("cv-output");
        out.textContent = res.result;
        out.className = "output-box " + (lang === "Pure Urdu (اردو)" ? "urdu" : "ltr");
        out.style.display = "block";
        const dl = document.getElementById("download-cv-btn");
        if (dl) dl.style.display = "inline-flex";
        if (res.warning) Toast.show(res.warning, "error", 7000);
        updateActionsLeft();
      } finally {
        btn.disabled = false;
        btn.textContent = "📄 Generate Resume";
      }
    });
  }

  // ── WhatsApp Business Replies ──
  function initWhatsappReplies() {
    const btn = document.getElementById("generate-wa-btn");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const lang = document.getElementById("wa-lang").value;
      if (!(await hasActionsLeft())) return;
      btn.disabled = true;
      btn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
      if (shouldShowAd()) await showInterstitialAd();
      try {
        const res = await api("/api/generate-whatsapp-replies", {
          biz: document.getElementById("wa-biz").value,
          lang,
          name: document.getElementById("wa-name").value.trim(),
          scenario: document.getElementById("wa-scenario").value,
          details: document.getElementById("wa-details").value.trim()
        });
        const out = document.getElementById("wa-output");
        out.textContent = res.result;
        out.className = "output-box " + (lang === "Pure Urdu (اردو)" ? "urdu" : "ltr");
        out.style.display = "block";
        const dl = document.getElementById("download-wa-btn");
        if (dl) dl.style.display = "inline-flex";
        if (res.warning) Toast.show(res.warning, "error", 7000);
        updateActionsLeft();
      } finally {
        btn.disabled = false;
        btn.textContent = "💬 Generate WhatsApp Replies";
      }
    });
  }

  // ── Script Timing Estimator ──
  function initScriptTiming() {
    const btn = document.getElementById("estimate-timing-btn");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const script = document.getElementById("timing-script").value.trim();
      if (!script) return Toast.show("Paste your script", "error");
      if (!(await hasActionsLeft())) return;
      btn.disabled = true;
      btn.innerHTML = `<span class="loading-dots"><span></span><span></span><span></span></span>`;
      if (shouldShowAd()) await showInterstitialAd();
      try {
        const res = await api("/api/estimate-script-timing", {
          script,
          lang: document.getElementById("timing-lang").value,
          pace: document.getElementById("timing-pace").value,
          target: document.getElementById("timing-target").value
        });
        const out = document.getElementById("timing-output");
        out.textContent = res.result;
        out.className = "output-box ltr";
        out.style.display = "block";
        const dl = document.getElementById("download-timing-btn");
        if (dl) dl.style.display = "inline-flex";
        if (res.warning) Toast.show(res.warning, "error", 7000);
        updateActionsLeft();
      } finally {
        btn.disabled = false;
        btn.textContent = "⏱️ Estimate Timing & Pacing";
      }
    });
  }

  // ── Update Actions Left ──
  function updateActionsLeft() {
    const el = document.getElementById("actions-left");
    if (!el) return;
    fetch("/api/actions-left").then(r => r.json()).then(d => {
      el.textContent = d.is_pro ? "Unlimited" : d.left;
      const ring = document.querySelector(".progress-ring-fill");
      if (ring && !d.is_pro) {
        const pct = d.left / d.total;
        const circumference = 2 * Math.PI * 20;
        ring.style.strokeDasharray = circumference;
        ring.style.strokeDashoffset = circumference * (1 - pct);
      }
    }).catch(() => {});
  }

  // ── Download Helper ──
  function initDownloads() {
    document.querySelectorAll("[data-download]").forEach(btn => {
      btn.addEventListener("click", () => {
        const target = document.querySelector(btn.dataset.download);
        const text = target ? (target.value || target.textContent) : "";
        const filename = btn.dataset.filename || "download.txt";
        const blob = new Blob(["\ufeff" + text], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        Toast.show("Download started!", "success");
      });
    });
  }

  // ── Stepper Navigation ──
  function initStepper() {
    document.querySelectorAll("[data-step]").forEach(btn => {
      btn.addEventListener("click", () => {
        const step = btn.dataset.step;
        document.querySelectorAll(".step-panel").forEach(p => p.classList.remove("active"));
        const panel = document.getElementById("step-" + step);
        if (panel) panel.classList.add("active");
        document.querySelectorAll(".step-dot").forEach((dot, idx) => {
          dot.classList.remove("active", "completed");
          const s = idx + 1;
          if (s < step) dot.classList.add("completed");
          else if (s == step) dot.classList.add("active");
        });
        document.querySelectorAll(".step-label").forEach((lbl, idx) => {
          lbl.classList.remove("active");
          if (idx + 1 == step) lbl.classList.add("active");
        });
        document.querySelectorAll(".step-line").forEach((line, idx) => {
          line.classList.toggle("completed", idx + 1 < step);
        });
      });
    });
  }

  // ── Admin Dashboard ──
  function initAdmin() {
    // Generate keys
    const genBtn = document.getElementById("admin-gen-keys");
    if (genBtn) {
      genBtn.addEventListener("click", async () => {
        const count = document.getElementById("key-count").value;
        genBtn.disabled = true;
        try {
          const res = await api("/admin/api/generate-key", { count }, "POST");
          const list = document.getElementById("generated-keys-list");
          list.innerHTML = res.keys.map(k => `<div class="key-row fresh"><code>${k}</code></div>`).join("");
          Toast.show(`${res.keys.length} key(s) generated!`, "success");
        } finally {
          genBtn.disabled = false;
        }
      });
    }

    // Revoke / Unrevoke / Delete keys
    document.querySelectorAll("[data-key-action]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.keyAction;
        const key = btn.dataset.key;
        const endpoint = `/admin/api/${action}-key`;
        await api(endpoint, { key }, "POST");
        Toast.show("Key updated", "success");
        location.reload();
      });
    });

    // Unlock a locked-out login-attempt IP
    document.querySelectorAll("[data-unlock-ip]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const ip_hash = btn.dataset.unlockIp;
        await api("/admin/api/unlock-login", { ip_hash }, "POST");
        Toast.show("Unlocked", "success");
        location.reload();
      });
    });

    // Approve / Reject requests
    document.querySelectorAll("[data-req-action]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.reqAction;
        const reqId = btn.dataset.reqId;
        const endpoint = `/admin/api/${action}-request`;
        const payload = { req_id: reqId };
        if (action === "approve") {
          const manualKey = document.getElementById(`manual-key-${reqId}`);
          if (manualKey && manualKey.value.trim()) payload.manual_key = manualKey.value.trim();
        }
        const res = await api(endpoint, payload, "POST");
        if (res.success && res.key) {
          Toast.show(`Approved! Key: ${res.key}`, "success");
        } else {
          Toast.show("Request updated", "success");
        }
        location.reload();
      });
    });

    // Delete requests
    document.querySelectorAll("[data-req-delete]").forEach(btn => {
      btn.addEventListener("click", async () => {
        if (!confirm("Delete this record?")) return;
        await api("/admin/api/delete-request", { req_id: btn.dataset.reqDelete }, "POST");
        location.reload();
      });
    });

    // Save limits
    const saveLimitsBtn = document.getElementById("save-limits-btn");
    if (saveLimitsBtn) {
      saveLimitsBtn.addEventListener("click", async () => {
        const data = {};
        document.querySelectorAll("[data-limit]").forEach(el => {
          data[el.dataset.limit] = el.type === "number" ? parseInt(el.value) : el.value;
        });
        const res = await api("/admin/api/save-limits", data);
        Toast.show(res.success ? "Limits saved!" : `Error: ${res.error}`, res.success ? "success" : "error");
      });
    }

    // Blog: write new post
    const createBlogBtn = document.getElementById("create-blog-btn");
    if (createBlogBtn) {
      createBlogBtn.addEventListener("click", async () => {
        const title = document.getElementById("new-blog-title").value.trim();
        const body = document.getElementById("new-blog-body").value.trim();
        if (!title || !body) {
          Toast.show("Title and body are required.", "error");
          return;
        }
        createBlogBtn.disabled = true;
        try {
          const res = await api("/admin/api/save-blog", {
            title,
            category: document.getElementById("new-blog-category").value.trim(),
            excerpt: document.getElementById("new-blog-excerpt").value.trim(),
            body,
            date: new Date().toISOString().slice(0, 10),
            published: document.getElementById("new-blog-published").checked
          });
          if (res.success) {
            Toast.show("Post saved!", "success");
            location.reload();
          } else {
            Toast.show(`Error: ${res.error || "Save failed"}`, "error");
          }
        } finally {
          createBlogBtn.disabled = false;
        }
      });
    }

    // Blog actions
    document.querySelectorAll("[data-blog-action]").forEach(btn => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.blogAction;
        const id = btn.dataset.blogId;
        if (action === "delete") {
          if (!confirm("Delete this post?")) return;
          await api("/admin/api/delete-blog", { id }, "POST");
        } else if (action === "toggle") {
          await api("/admin/api/toggle-blog", { id }, "POST");
        }
        location.reload();
      });
    });

    // Test email
    const testEmailBtn = document.getElementById("test-email-btn");
    if (testEmailBtn) {
      testEmailBtn.addEventListener("click", async () => {
        testEmailBtn.disabled = true;
        try {
          const res = await api("/admin/api/test-email", {}, "POST");
          Toast.show(res.success ? "Test email sent!" : res.error, res.success ? "success" : "error");
        } finally {
          testEmailBtn.disabled = false;
        }
      });
    }
  }

  // ── Ad Frequency Capping ──
  // UX/POLICY FIX: every single generation action showed a full 5-second
  // interstitial with zero capping — a brand-new user's very first click
  // on ANY tool hit an ad before they'd seen the product produce anything,
  // and a heavy user got hit on every action with no let-up. Ad networks
  // also treat this as a "make good" risk: forcing an impression on every
  // single interaction, regardless of a real gap, is the kind of pattern
  // that gets sites flagged in Adsterra/AdSense review. Now: no ad for a
  // session's first 2 free actions (let them see it work first), then at
  // most one ad every 3rd action — with a hard minimum 90-second gap even
  // if the count would trigger one back-to-back (someone spamming the
  // generate button shouldn't get an ad every few seconds).
  const AD_EVERY_N_ACTIONS = 3;
  const AD_MIN_GAP_MS = 90 * 1000;

  function shouldShowAd() {
    if (window.IS_PRO) return false;
    const count = parseInt(sessionStorage.getItem("qs_action_count") || "0", 10) + 1;
    sessionStorage.setItem("qs_action_count", String(count));
    if (count <= 2) return false;
    if (count % AD_EVERY_N_ACTIONS !== 0) return false;
    const lastAd = parseInt(sessionStorage.getItem("qs_last_ad_ts") || "0", 10);
    if (Date.now() - lastAd < AD_MIN_GAP_MS) return false;
    sessionStorage.setItem("qs_last_ad_ts", String(Date.now()));
    return true;
  }

  // ── Interstitial Ad ──
  // BUG FIX: this used to inject the SAME Adsterra script + a container id
  // with an invented "-interstitial" suffix directly into the page DOM. That
  // suffix never matched what invoke.js looks for (so the ad never rendered),
  // and injecting the same zone script again while a banner ad's identical
  // script was already loaded elsewhere on the page caused conflicts. Now it
  // loads an isolated iframe (served by /ads/slot/interstitial) with its own
  // separate document, so the container ID doesn't need to be renamed and
  // doesn't collide with anything else on the page.
  function showInterstitialAd() {
    if (window.IS_PRO) return Promise.resolve();
    return new Promise(resolve => {
      const overlay = document.createElement("div");
      overlay.className = "ad-interstitial active";
      overlay.innerHTML = `
        <div class="ad-box">
          <div class="ad-label">⚡ Sponsored — Preparing Your Content</div>
          <div style="min-height:140px;display:flex;align-items:center;justify-content:center;margin:0.5rem 0">
            <iframe src="/ads/slot/interstitial" style="width:100%;height:140px;border:0;" scrolling="no"></iframe>
          </div>
          <div class="ad-timer" id="ad-timer">Ad closes in 5s…</div>
          <button class="ad-skip" id="ad-skip-btn" disabled>Please wait…</button>
          <div class="ad-pro-link"><a href="/request-pro">Remove ads with Pro →</a></div>
        </div>
      `;
      document.body.appendChild(overlay);

      let s = 5;
      const timer = document.getElementById("ad-timer");
      const btn = document.getElementById("ad-skip-btn");
      const iv = setInterval(() => {
        s--;
        if (s <= 0) {
          clearInterval(iv);
          overlay.remove();
          resolve();
        } else {
          timer.textContent = "Ad closes in " + s + "s…";
          if (s <= 2) {
            btn.disabled = false;
            btn.textContent = "Skip Ad (" + s + ")";
          }
        }
      }, 1000);

      btn.addEventListener("click", () => {
        clearInterval(iv);
        overlay.remove();
        resolve();
      });
    });
  }

  // ── Initialize Everything ──
  document.addEventListener("DOMContentLoaded", () => {
    initNavScroll();
    initMobileNav();
    initTabs();
    initReveal();
    initCopyButtons();
    initLicenseSystem();
    initUrduWriter();
    initFreelancer();
    initSubtitles();
    initProofread();
    initYoutubeSeo();
    initResume();
    initWhatsappReplies();
    initScriptTiming();
    initDownloads();
    initStepper();
    initAdmin();
    Modal.init();

    // Flash messages to toasts
    document.querySelectorAll(".flash-message").forEach(el => {
      const type = el.dataset.type || "info";
      Toast.show(el.textContent, type);
      el.remove();
    });
  });
})();
