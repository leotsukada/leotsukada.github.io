// Leo Tsukada — personal website. No dependencies.
(() => {
  const header = document.querySelector(".site-header");
  const toggle = document.querySelector(".nav__toggle");
  const menu = document.getElementById("nav-menu");

  // Mobile menu
  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(open));
      menu.classList.toggle("is-open", open);
    });
    menu.addEventListener("click", (e) => {
      if (e.target.closest("a") && window.matchMedia("(max-width: 991px)").matches) {
        toggle.setAttribute("aria-expanded", "false");
        menu.classList.remove("is-open");
      }
    });
  }

  // "Links" dropdown
  document.querySelectorAll(".nav__dropdown").forEach((dropdown) => {
    const button = dropdown.querySelector("button");
    const submenu = dropdown.querySelector(".nav__submenu");
    const setOpen = (open) => {
      button.setAttribute("aria-expanded", String(open));
      submenu.hidden = !open;
    };
    button.addEventListener("click", () => setOpen(button.getAttribute("aria-expanded") !== "true"));
    document.addEventListener("click", (e) => { if (!dropdown.contains(e.target)) setOpen(false); });
    dropdown.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { setOpen(false); button.focus(); }
    });
  });

  // Header shadow + back-to-top visibility
  const toTop = document.querySelector(".to-top");
  const onScroll = () => {
    const y = window.scrollY;
    header?.classList.toggle("is-scrolled", y > 10);
    toTop?.classList.toggle("is-visible", y > 600);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  toTop?.addEventListener("click", () => window.scrollTo({ top: 0 }));

  // News carousel
  document.querySelectorAll("[data-carousel]").forEach((carousel) => {
    const track = carousel.querySelector(".carousel__track");
    const prev = carousel.querySelector(".carousel__btn--prev");
    const next = carousel.querySelector(".carousel__btn--next");
    const interval = Number(carousel.dataset.autoplay || 0) * 1000;

    const step = () => {
      const card = track.firstElementChild;
      const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
      return card ? card.getBoundingClientRect().width + gap : track.clientWidth;
    };
    const atEnd = () => track.scrollLeft + track.clientWidth >= track.scrollWidth - 4;
    const update = () => {
      prev.disabled = track.scrollLeft <= 4;
      next.disabled = atEnd();
    };

    prev.addEventListener("click", () => track.scrollBy({ left: -step(), behavior: "smooth" }));
    next.addEventListener("click", () => track.scrollBy({ left: step(), behavior: "smooth" }));
    track.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    update();

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!interval || reduceMotion) return;

    let paused = false;
    const pause = () => { paused = true; };
    const resume = () => { paused = false; };
    carousel.addEventListener("mouseenter", pause);
    carousel.addEventListener("mouseleave", resume);
    carousel.addEventListener("focusin", pause);
    carousel.addEventListener("focusout", resume);
    track.addEventListener("pointerdown", pause);
    track.addEventListener("touchstart", pause, { passive: true });

    setInterval(() => {
      if (paused || document.hidden) return;
      const rect = carousel.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight) return;
      if (atEnd()) track.scrollTo({ left: 0, behavior: "smooth" });
      else track.scrollBy({ left: step(), behavior: "smooth" });
    }, interval);
  });

  // Footer year
  document.querySelectorAll("[data-year]").forEach((el) => { el.textContent = new Date().getFullYear(); });
})();
