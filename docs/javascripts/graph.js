/* The home page's figure: select a line of lambda_handler and the graph lights the path it takes (data-on names the
   edges, "source>target"). Until someone picks a line, it steps through them on its own, unless the reader asked for
   less motion. Without this script the graph is simply all there. */

(() => {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const STEP_MS = 2600; // how long each line stays lit while it steps on its own

  function startTrace(trace) {
    const lines = [...trace.querySelectorAll(".cn-line[data-on]")];
    const graph = trace.querySelector(".cn-graph");
    if (!lines.length || !graph) return;
    let current = -1;
    let timer = null;

    function light(index) {
      current = index;
      lines.forEach((line, n) => line.classList.toggle("on", n === index));
      const edges = new Set(lines[index].dataset.on.split(/\s+/).filter(Boolean));
      const nodes = new Set();
      edges.forEach((edge) => edge.split(">").forEach((node) => nodes.add(node)));
      graph.querySelectorAll(".e").forEach((e) => e.classList.toggle("on", edges.has(e.dataset.edge)));
      graph.querySelectorAll(".n").forEach((n) => n.classList.toggle("on", nodes.has(n.dataset.node)));
      trace.classList.add("tracing");
    }

    function pick(index) {
      clearInterval(timer);
      light(index);
    }

    lines.forEach((line, n) => {
      line.addEventListener("click", () => pick(n));
      line.addEventListener("mouseenter", () => pick(n));
      line.addEventListener("focus", () => pick(n));
    });

    if (reduced) return;
    light(0);
    timer = setInterval(() => light((current + 1) % lines.length), STEP_MS);
  }

  function start() {
    const traces = [...document.querySelectorAll(".cn-trace")];
    if (!("IntersectionObserver" in window)) return traces.forEach(startTrace);
    const seen = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      seen.unobserve(entry.target);
      startTrace(entry.target);
    }), { threshold: 0.35 });
    traces.forEach((trace) => seen.observe(trace));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
