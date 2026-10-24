// Paperlane page behaviour: maths rendering, subfield filters and the paste-in prompt.
(function () {
  function renderMath() {
    if (!window.renderMathInElement) return;
    window.renderMathInElement(document.querySelector("main"), {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
    });
  }

  function filters() {
    var papers = Array.prototype.slice.call(document.querySelectorAll("article.paper"));
    if (!papers.length) return;
    var groups = document.querySelectorAll("section.group");
    var chips = document.querySelectorAll(".chip");
    var code = document.getElementById("f-code");
    var lean = document.getElementById("f-lean");
    var q = document.getElementById("f-q");
    var count = document.getElementById("f-count");
    var params = new URLSearchParams(location.search);
    var state = {
      cat: params.get("cat") || "",
      code: params.get("code") === "1",
      lean: params.get("lean") === "1",
      q: params.get("q") || "",
    };
    code.checked = state.code;
    lean.checked = state.lean;
    q.value = state.q;

    function apply() {
      var needle = state.q.trim().toLowerCase();
      var shown = 0;
      papers.forEach(function (p) {
        var ok =
          (!state.cat || p.dataset.cats.split(" ").indexOf(state.cat) >= 0) &&
          (!state.code || p.dataset.code) &&
          (!state.lean || p.dataset.lean) &&
          (!needle || p.dataset.text.indexOf(needle) >= 0);
        p.hidden = !ok;
        if (ok) shown++;
      });
      groups.forEach(function (g) {
        var n = g.querySelectorAll("article.paper:not([hidden])").length;
        g.hidden = n === 0;
        g.querySelector(".n").textContent = n;
      });
      chips.forEach(function (c) {
        c.setAttribute("aria-pressed", c.dataset.cat === state.cat ? "true" : "false");
      });
      count.textContent = shown === papers.length ? "" : shown + " shown";
      var out = new URLSearchParams();
      if (state.cat) out.set("cat", state.cat);
      if (state.code) out.set("code", "1");
      if (state.lean) out.set("lean", "1");
      if (state.q) out.set("q", state.q);
      var s = out.toString();
      history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + location.hash);
    }

    chips.forEach(function (c) {
      c.addEventListener("click", function () {
        state.cat = c.dataset.cat;
        apply();
      });
    });
    code.addEventListener("change", function () { state.code = code.checked; apply(); });
    lean.addEventListener("change", function () { state.lean = lean.checked; apply(); });
    q.addEventListener("input", function () { state.q = q.value; apply(); });
    apply();

    // Open the abstract a shared link points at.
    if (location.hash) {
      var target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (target && target.querySelector("details")) target.querySelector("details").open = true;
    }
  }

  function prompt() {
    var box = document.getElementById("prompt");
    if (!box) return;
    var interests = document.getElementById("interests");
    var base = box.dataset.base;
    var saved = localStorage.getItem("paperlane-interests") || "";
    interests.value = saved;
    function update() {
      var i = interests.value.trim() || "X and Y";
      box.value =
        "Read " + base + "/latest-titles.md, Paperlane's index of today's new arXiv mathematics papers. " +
        "My interests are " + i + ". Pick the candidates that fit, read their abstracts in " + base +
        "/latest.md or on arXiv, and tell me which three papers I should read and why.";
      localStorage.setItem("paperlane-interests", interests.value);
    }
    interests.addEventListener("input", update);
    update();
    document.getElementById("copy").addEventListener("click", function (e) {
      box.select();
      (navigator.clipboard ? navigator.clipboard.writeText(box.value) : Promise.reject()).then(
        function () { e.target.textContent = "Copied"; },
        function () { document.execCommand("copy"); e.target.textContent = "Copied"; }
      );
      setTimeout(function () { e.target.textContent = "Copy prompt"; }, 1500);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    filters();
    prompt();
    renderMath();
  });
})();
