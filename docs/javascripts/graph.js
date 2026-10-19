/* code-node's site motion. Puts .cn-motion on <html> (unless the reader asked for less motion), so the CSS can
   animate. Things start when they scroll into view (.cn-in): the graphs draw themselves, the terminal types, and the
   trace steps through the handler's lines, lighting up the path each one takes. A click on a line jumps to it. */

(() => {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const TRACE_STEP_MS = 2200; // how long each line of the trace stays lit
  const TRACE_PAUSE_MS = 7000; // after a click, how long it waits before stepping again
  const TYPE_MS = 70; // per character the terminal types

  if (!reduced) document.documentElement.classList.add("cn-motion");

  function onView(elements, start, threshold = 0.25) {
    if (!("IntersectionObserver" in window)) return elements.forEach(start);
    const seen = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        seen.unobserve(entry.target);
        start(entry.target);
      });
    }, { threshold });
    elements.forEach((el) => seen.observe(el));
  }

  function typeTerminal(term) {
    const command = term.querySelector(".t-cmd");
    const lines = [...term.querySelectorAll(".t-out")];
    if (!command) return;
    const text = command.dataset.type || "";
    let i = 0;
    command.classList.add("typing");
    const typing = setInterval(() => {
      i += 1;
      command.dataset.typed = text.slice(0, i);
      if (i < text.length) return;
      clearInterval(typing);
      setTimeout(() => {
        command.classList.remove("typing");
        lines.forEach((line, n) => setTimeout(() => line.classList.add("shown"), 260 * n));
      }, 380);
    }, TYPE_MS);
  }

  function startTrace(trace) {
    const lines = [...trace.querySelectorAll(".cn-line")];
    const graph = trace.querySelector(".cn-graph");
    if (!lines.length || !graph) return;
    let current = -1;
    let timer = null;

    function light(index) {
      current = index;
      lines.forEach((line, n) => line.classList.toggle("on", n === index));
      const edges = new Set((lines[index].dataset.on || "").split(/\s+/).filter(Boolean));
      const nodes = new Set();
      edges.forEach((edge) => edge.split(">").forEach((node) => nodes.add(node)));
      graph.querySelectorAll(".e").forEach((e) => e.classList.toggle("on", edges.has(e.dataset.edge)));
      graph.querySelectorAll(".n").forEach((n) => n.classList.toggle("on", nodes.has(n.dataset.node)));
      trace.classList.add("tracing");
    }

    function play(delay = TRACE_STEP_MS) {
      clearTimeout(timer);
      timer = setTimeout(function next() {
        light((current + 1) % lines.length);
        timer = setTimeout(next, TRACE_STEP_MS);
      }, delay);
    }

    lines.forEach((line, n) => line.addEventListener("click", () => {
      light(n);
      play(TRACE_PAUSE_MS);
    }));
    light(0);
    if (!reduced) play();
  }

  function progressBar() {
    const bar = document.createElement("div");
    bar.className = "cn-progress";
    document.body.appendChild(bar);
    const update = () => {
      const room = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.setProperty("--p", room > 0 ? Math.min(1, window.scrollY / room) : 0);
    };
    window.addEventListener("scroll", update, { passive: true });
    update();
  }

  function copyButtons() {
    document.querySelectorAll(".cn-copy").forEach((button) => button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        button.textContent = "copied ✓";
      } catch (error) {
        button.textContent = "select it ↖";
      }
      setTimeout(() => { button.textContent = "copy"; }, 1600);
    }));
  }

  function start() {
    const mark = (el) => el.classList.add("cn-in");
    onView([...document.querySelectorAll(".cn-graph, .cn-reveal, .cn-live")], mark, 0.2);
    onView([...document.querySelectorAll(".cn-term")], reduced ? () => {} : typeTerminal, 0.5);
    onView([...document.querySelectorAll(".cn-trace")], startTrace, 0.35);
    if (!reduced) progressBar();
    copyButtons();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
