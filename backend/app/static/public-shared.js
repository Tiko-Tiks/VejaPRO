/* ===================================================================
   VejaPRO Public Shared JS v1.0
   Sticky header, hamburger, smooth scroll, fade-in, mobile bar
   =================================================================== */
"use strict";

(() => {
  /* ── Sticky header ── */
  const header = document.querySelector(".vp-header");
  if (header) {
    const onScroll = () => {
      if (window.scrollY > 60) {
        header.classList.add("scrolled");
      } else {
        header.classList.remove("scrolled");
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ── Hamburger menu ── */
  const hamburger = document.querySelector(".vp-hamburger");
  const mobileMenu = document.querySelector(".vp-mobile-menu");
  if (hamburger && mobileMenu) {
    hamburger.addEventListener("click", () => {
      const isOpen = mobileMenu.classList.toggle("open");
      hamburger.classList.toggle("open", isOpen);
      document.body.style.overflow = isOpen ? "hidden" : "";
    });
    mobileMenu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        mobileMenu.classList.remove("open");
        hamburger.classList.remove("open");
        document.body.style.overflow = "";
      });
    });
  }

  /* ── Smooth scroll for anchor links ── */
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", (e) => {
      const id = anchor.getAttribute("href");
      if (!id || id === "#") return;
      const target = document.querySelector(id);
      if (target) {
        e.preventDefault();
        const headerH = header ? header.offsetHeight : 0;
        const y = target.getBoundingClientRect().top + window.scrollY - headerH - 16;
        window.scrollTo({ top: y, behavior: "smooth" });
      }
    });
  });

  /* ── Fade-in on scroll (IntersectionObserver) ── */
  const fadeEls = document.querySelectorAll(".vp-fade");
  if (fadeEls.length) {
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
          }
        });
      },
      { threshold: 0.1 },
    );
    fadeEls.forEach((el) => obs.observe(el));
  }

  /* ── Before/After Lightbox utility ── */
  window.VPLightbox = {
    open(item) {
      const lb = document.createElement("div");
      lb.className = "vp-lightbox";
      lb.setAttribute("role", "dialog");
      lb.setAttribute("aria-modal", "true");

      const content = document.createElement("div");
      content.className = "vp-lightbox-content";
      content.addEventListener("click", (e) => e.stopPropagation());

      const closeBtn = document.createElement("button");
      closeBtn.className = "vp-lightbox-close";
      closeBtn.innerHTML = "&#215;";
      closeBtn.setAttribute("aria-label", "Uždaryti");
      closeBtn.addEventListener("click", () => lb.remove());

      if (item.before_url && item.after_url) {
        const slider = this._createSlider(item);
        content.appendChild(slider);
      } else {
        const wrap = document.createElement("div");
        wrap.style.cssText =
          "max-width:1100px;border-radius:12px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.5)";
        const img = document.createElement("img");
        img.src = item.after_url || item.before_url || "";
        img.alt = item.location_tag || "VejaPRO";
        img.style.cssText = "width:100%;height:auto;display:block";
        wrap.appendChild(img);
        content.appendChild(wrap);
      }

      if (item.location_tag) {
        const info = document.createElement("div");
        info.className = "vp-lightbox-info";
        info.textContent = item.location_tag;
        content.appendChild(info);
      }

      content.appendChild(closeBtn);
      lb.appendChild(content);
      lb.addEventListener("click", (e) => {
        if (e.target === lb) lb.remove();
      });

      const onKey = (e) => {
        if (e.key === "Escape") {
          lb.remove();
          document.removeEventListener("keydown", onKey);
        }
      };
      document.addEventListener("keydown", onKey);

      document.body.appendChild(lb);
    },

    _createSlider(item) {
      const wrap = document.createElement("div");
      wrap.className = "vp-lightbox-slider";

      const container = document.createElement("div");
      container.className = "vp-slider-container";

      const beforeImg = document.createElement("img");
      beforeImg.src = item.before_url;
      beforeImg.alt = "Prieš";
      beforeImg.className = "before-image";

      const afterImg = document.createElement("img");
      afterImg.src = item.after_url;
      afterImg.alt = "Po";
      afterImg.className = "after-image";

      const handle = document.createElement("div");
      handle.className = "vp-slider-handle";

      const btn = document.createElement("div");
      btn.className = "vp-slider-btn";
      handle.appendChild(btn);

      const labelBefore = document.createElement("div");
      labelBefore.className = "vp-slider-label before";
      labelBefore.textContent = "Prieš";

      const labelAfter = document.createElement("div");
      labelAfter.className = "vp-slider-label after";
      labelAfter.textContent = "Po";

      container.append(beforeImg, afterImg, handle, labelBefore, labelAfter);
      wrap.appendChild(container);

      let dragging = false;
      const update = (clientX) => {
        const rect = container.getBoundingClientRect();
        const pct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
        handle.style.left = pct + "%";
        afterImg.style.clipPath = `inset(0 ${100 - pct}% 0 0)`;
      };

      const start = (e) => {
        dragging = true;
        update(e.clientX ?? e.touches[0].clientX);
      };
      const move = (e) => {
        if (!dragging) return;
        e.preventDefault();
        update(e.clientX ?? e.touches[0].clientX);
      };
      const stop = () => {
        dragging = false;
      };

      handle.addEventListener("mousedown", start);
      container.addEventListener("mousedown", start);
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", stop);
      handle.addEventListener("touchstart", start, { passive: true });
      container.addEventListener("touchstart", start, { passive: true });
      document.addEventListener("touchmove", move, { passive: false });
      document.addEventListener("touchend", stop);

      return wrap;
    },
  };

  /* ── Form helper: extract error from API response ── */
  window.vpExtractError = async (response) => {
    try {
      const data = await response.json();
      const d = data?.detail;
      if (typeof d === "string") return d;
      if (Array.isArray(d)) return d.map((i) => i.msg || JSON.stringify(i)).join("; ");
      if (d) return JSON.stringify(d);
      return JSON.stringify(data);
    } catch {
      try {
        return await response.text();
      } catch {
        return "";
      }
    }
  };
})();
