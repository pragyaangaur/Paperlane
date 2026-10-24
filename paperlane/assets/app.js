// Paperlane page behaviour. Everything here is optional: without JavaScript every paper still shows, with its links.
(function () {
  "use strict";
  var body = document.body;
  var prefix = body.dataset.prefix || "";
  var base = (body.dataset.base || location.origin).replace(/\/$/, "");
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function copy(text, button, label) {
    var done = function () {
      button.textContent = "Copied";
      setTimeout(function () { button.textContent = label; }, 1400);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, done);
    else done();
  }

  function renderMath(el) {
    if (!window.renderMathInElement || !el) return;
    window.renderMathInElement(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
    });
  }

  // arXiv ids: new style 2610.30655, old style math/0601001, with or without a version.
  function parseId(raw) {
    var s = (raw || "").trim();
    try { s = decodeURIComponent(s); } catch (e) {}
    var m = s.match(/(\d{4}\.\d{4,5})(v\d+)?/) || s.match(/([a-z][a-z-]*(?:\.[A-Z]{2})?\/\d{7})(v\d+)?/i);
    return m ? { id: m[1], v: m[2] || "" } : null;
  }
  function anchorOf(id) { return id.replace("/", "-"); }

  // Theme: Auto follows the system, and the choice is remembered on this device.
  function theme() {
    var btn = $("[data-theme-toggle]");
    if (!btn) return;
    var order = ["auto", "light", "dark"];
    var names = { auto: "Auto", light: "Light", dark: "Dark" };
    var current = document.documentElement.dataset.theme || "auto";
    function show() { btn.querySelector("span").textContent = names[current]; btn.title = "Theme: " + names[current] + ". Click to switch."; }
    btn.addEventListener("click", function () {
      current = order[(order.indexOf(current) + 1) % order.length];
      if (current === "auto") { delete document.documentElement.dataset.theme; localStorage.removeItem("paperlane-theme"); }
      else { document.documentElement.dataset.theme = current; localStorage.setItem("paperlane-theme", current); }
      show();
    });
    show();
  }

  // The header box opens any paper. A paper on the current page is scrolled to directly.
  function lookupForm() {
    var form = $("form.lookup");
    if (!form) return;
    form.addEventListener("submit", function (e) {
      var input = form.querySelector("input");
      var parsed = parseId(input.value);
      if (!parsed) return; // the lookup page explains what it expects
      var here = document.getElementById(anchorOf(parsed.id));
      if (here && here.classList.contains("paper")) {
        e.preventDefault();
        if (here.hidden && window.paperlaneClear) window.paperlaneClear();
        here.scrollIntoView({ behavior: "smooth", block: "start" });
        history.replaceState(null, "", "#" + here.id);
        here.classList.add("expanded");
        return;
      }
      input.value = parsed.id + parsed.v;
    });
  }

  // Filters on a day page.
  function filters() {
    var aside = $("#filters");
    if (!aside) return;
    var papers = $$("article.paper");
    // Search only the parts a reader means: id, title, authors and abstract.
    var text = papers.map(function (p) {
      return [".aid", "h3", ".authors", ".abstract"].map(function (sel) { var el = $(sel, p); return el ? el.textContent : ""; }).join(" ").toLowerCase().replace(/\s+/g, " ");
    });
    var groups = $$("section.group");
    var q = $("#f-q"), code = $("#f-code"), lean = $("#f-lean"), sub = $("#f-sub");
    var catBoxes = $$('input[name="cat"]', aside), kindBoxes = $$('input[name="kind"]', aside);
    var names = {};
    catBoxes.forEach(function (b) { names[b.value] = b.parentNode.querySelector("span").textContent; });
    var kindNames = { new: "New papers", cross: "Cross-lists", replace: "New versions" };

    var params = new URLSearchParams(location.search);
    q.value = params.get("q") || "";
    code.checked = params.get("code") === "1";
    lean.checked = params.get("lean") === "1";
    var cats = (params.get("cat") || "").split(",").filter(Boolean);
    catBoxes.forEach(function (b) { b.checked = cats.indexOf(b.value) >= 0; });
    var hide = (params.get("hide") || "").split(",").filter(Boolean);
    kindBoxes.forEach(function (b) { b.checked = hide.indexOf(b.value) < 0; });

    function state() {
      return {
        q: q.value.trim().toLowerCase(),
        code: code.checked,
        lean: lean.checked,
        cats: catBoxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; }),
        hide: kindBoxes.filter(function (b) { return !b.checked; }).map(function (b) { return b.value; }),
      };
    }

    function pill(label, onRemove) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "pill";
      b.innerHTML = esc(label) + " <b aria-hidden=\"true\">×</b>";
      b.setAttribute("aria-label", "Remove filter " + label);
      b.addEventListener("click", function () { onRemove(); apply(); });
      return b;
    }

    function apply() {
      var s = state();
      var words = s.q.split(" ").filter(Boolean);
      var shown = 0;
      papers.forEach(function (p, i) {
        var pc = p.dataset.cats.split(" ");
        var ok =
          (!s.cats.length || s.cats.some(function (c) { return pc.indexOf(c) >= 0; })) &&
          s.hide.indexOf(p.dataset.kind) < 0 &&
          (!s.code || p.dataset.code) &&
          (!s.lean || p.dataset.lean) &&
          words.every(function (w) { return text[i].indexOf(w) >= 0; });
        p.hidden = !ok;
        if (ok) shown++;
      });
      groups.forEach(function (g) {
        var n = $$("article.paper:not([hidden])", g).length;
        g.hidden = n === 0;
        $(".n", g).textContent = n;
      });

      var active = s.cats.length + s.hide.length + (s.code ? 1 : 0) + (s.lean ? 1 : 0) + (s.q ? 1 : 0);
      $("#f-count").textContent = active ? "Showing " + shown + " of " + papers.length + " papers" : papers.length + " papers";
      $("#f-badge").textContent = active || "";
      $("#f-empty").hidden = shown > 0;

      var pills = $("#f-pills");
      pills.innerHTML = "";
      if (s.q) pills.appendChild(pill("“" + q.value.trim() + "”", function () { q.value = ""; }));
      if (s.code) pills.appendChild(pill("Has code", function () { code.checked = false; }));
      if (s.lean) pills.appendChild(pill("Lean", function () { lean.checked = false; }));
      s.cats.forEach(function (c) {
        pills.appendChild(pill(names[c] || c, function () { catBoxes.forEach(function (b) { if (b.value === c) b.checked = false; }); }));
      });
      s.hide.forEach(function (k) {
        pills.appendChild(pill("Hiding " + kindNames[k].toLowerCase(), function () { kindBoxes.forEach(function (b) { if (b.value === k) b.checked = true; }); }));
      });

      // Someone typed an arXiv id that is not on this day: offer to open it anyway.
      var hint = $("#f-lookup");
      var parsed = parseId(s.q);
      if (parsed && shown === 0) {
        hint.hidden = false;
        hint.innerHTML = "arXiv:" + esc(parsed.id) + " is not on this day. <a href=\"" + prefix + "paper.html?id=" + encodeURIComponent(parsed.id + parsed.v) + "\">Open it anyway</a>.";
        $("#f-empty").hidden = true;
      } else hint.hidden = true;

      var out = new URLSearchParams();
      if (s.q) out.set("q", q.value.trim());
      if (s.code) out.set("code", "1");
      if (s.lean) out.set("lean", "1");
      if (s.cats.length) out.set("cat", s.cats.join(","));
      if (s.hide.length) out.set("hide", s.hide.join(","));
      var str = out.toString();
      history.replaceState(null, "", location.pathname + (str ? "?" + str : "") + location.hash);
    }

    window.paperlaneClear = function () {
      q.value = "";
      code.checked = lean.checked = false;
      catBoxes.forEach(function (b) { b.checked = false; });
      kindBoxes.forEach(function (b) { b.checked = true; });
      apply();
    };

    aside.addEventListener("change", apply);
    q.addEventListener("input", apply);
    sub.addEventListener("input", function () {
      var needle = sub.value.trim().toLowerCase();
      catBoxes.forEach(function (b) {
        var label = b.parentNode;
        label.hidden = needle && (label.textContent + " " + b.value).toLowerCase().indexOf(needle) < 0;
      });
    });
    $$("[data-clear]").forEach(function (b) { b.addEventListener("click", window.paperlaneClear); });
    $$("[data-open-filters]").forEach(function (b) { b.addEventListener("click", function () { body.classList.add("filters-open"); }); });
    $$("[data-close-filters]").forEach(function (b) { b.addEventListener("click", function () { body.classList.remove("filters-open"); }); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") body.classList.remove("filters-open");
      if (e.key === "/" && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); q.focus(); }
    });
    apply();
  }

  // Buttons on each paper card.
  function showMarkdown(panel, name, text) {
    panel.innerHTML =
      '<div class="md-bar"><span>' + esc(name) + '</span><button type="button" class="link" data-copy-md>Copy Markdown</button>' +
      (panel.dataset.url ? '<a href="' + esc(panel.dataset.url) + '">Open raw</a>' : "") + "</div><pre></pre>";
    $("pre", panel).textContent = text;
    $("[data-copy-md]", panel).addEventListener("click", function (e) { copy(text, e.target, "Copy Markdown"); });
  }

  function cards() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("button.act");
      if (!btn) return;
      var card = btn.closest("article.paper");
      var act = btn.dataset.act;
      if (act === "expand") {
        var open = card.classList.toggle("expanded");
        btn.textContent = open ? "Show less" : "Read abstract";
        btn.setAttribute("aria-expanded", open);
      } else if (act === "md") {
        var panel = $(".md-panel", card);
        var opening = panel.hidden;
        panel.hidden = !opening;
        btn.setAttribute("aria-expanded", opening);
        if (!opening || panel.dataset.loaded) return;
        panel.dataset.loaded = "1";
        if (btn.markdown) return showMarkdown(panel, "Markdown made in your browser", btn.markdown);
        panel.dataset.url = btn.dataset.md;
        panel.innerHTML = '<div class="md-bar"><span>Loading…</span></div>';
        fetch(btn.dataset.md).then(function (r) {
          if (!r.ok) throw new Error(r.status);
          return r.text();
        }).then(function (t) {
          showMarkdown(panel, btn.dataset.md.split("/").pop(), t);
        }).catch(function () {
          delete panel.dataset.loaded;
          panel.innerHTML = '<div class="md-bar"><span>Could not load the Markdown.</span><a href="' + esc(btn.dataset.md) + '">Open it directly</a></div>';
        });
      } else if (act === "link") {
        copy(new URL(btn.dataset.url, location.href).href, btn, "Copy link");
      }
    });
    // A shared link to one paper opens its abstract.
    if (location.hash) {
      var target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (target && target.classList.contains("paper")) {
        target.classList.add("expanded");
        var b = $('[data-act="expand"]', target);
        if (b) { b.textContent = "Show less"; b.setAttribute("aria-expanded", "true"); }
      }
    }
  }

  // The "Ask your AI" dialog.
  function ask() {
    var dlg = $("#ask");
    if (!dlg) return;
    var box = $("#prompt"), interests = $("#interests");
    interests.value = localStorage.getItem("paperlane-interests") || "";
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
    $$("[data-open-ask]").forEach(function (b) {
      b.addEventListener("click", function () { dlg.showModal ? dlg.showModal() : dlg.setAttribute("open", ""); interests.focus(); });
    });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
    $("#copy-prompt").addEventListener("click", function (e) { copy(box.value, e.target, "Copy prompt"); });
  }

  // The lookup page: Paperlane's archive first, then open scholarly APIs, since arXiv's API blocks browsers.
  var LEAN_RE = /\bLean[ ~]?4\b|\bMathlib\b|\b(?:in|using|with|into) Lean\b|\bLean (?:proof|formali[sz]ation|theorem prover|code|project|library)/;
  var CODE_HOSTS = ["github.com", "gitlab.com", "codeberg.org", "bitbucket.org", "git.sr.ht", "huggingface.co"];

  function getJSON(url) {
    return fetch(url).then(function (r) {
      if (r.status === 429) return new Promise(function (ok) { setTimeout(ok, 1500); }).then(function () { return fetch(url); });
      return r;
    }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }

  function fromSemanticScholar(id) {
    return getJSON("https://api.semanticscholar.org/graph/v1/paper/arXiv:" + id + "?fields=title,abstract,authors,publicationDate,venue").then(function (d) {
      if (!d || !d.title) return null;
      return { source: "Semantic Scholar", title: d.title, abstract: d.abstract || "", date: d.publicationDate || "", authors: (d.authors || []).map(function (a) { return a.name; }) };
    });
  }

  function fromOpenAlex(id) {
    return getJSON("https://api.openalex.org/works/doi:10.48550/arxiv." + id.toLowerCase()).then(function (d) {
      if (!d || !d.title) return null;
      var words = [];
      Object.keys(d.abstract_inverted_index || {}).forEach(function (w) {
        d.abstract_inverted_index[w].forEach(function (i) { words[i] = w; });
      });
      return {
        source: "OpenAlex", title: d.title, abstract: words.join(" "), date: d.publication_date || "",
        authors: (d.authorships || []).map(function (a) { return a.author && a.author.display_name; }).filter(Boolean),
      };
    });
  }

  function findLinks(text) {
    var out = [];
    (text.match(/https?:\/\/[^\s<>"'{}|\\^`]+|(?:github\.com|gitlab\.com|codeberg\.org|bitbucket\.org)\/[^\s<>"'{}|\\^`]+/gi) || []).forEach(function (u) {
      u = u.replace(/[.,;:!?'")\]}]+$/, "");
      if (!/^http/i.test(u)) u = "https://" + u;
      if (out.indexOf(u) < 0) out.push(u);
    });
    return out;
  }

  function leanCheck(repo) {
    return getJSON("https://api.github.com/repos/" + repo + "/git/trees/HEAD?recursive=1").then(function (t) {
      if (!t) return null;
      return (t.tree || []).filter(function (x) { return /(^|\/)(lean-toolchain|lakefile\.lean|lakefile\.toml)$/.test(x.path); }).map(function (x) { return x.path; });
    });
  }

  function lookupPage() {
    var result = $("#lk-result");
    if (!result) return;
    var raw = new URLSearchParams(location.search).get("id");
    var status = $("#lk-status"), title = $("#lk-title");
    if (!raw) return;
    $("form.lookup input").value = raw;
    var parsed = parseId(raw);
    if (!parsed) {
      status.innerHTML = "That does not look like an arXiv link or id. Try one like <code>2610.30655</code> or <code>https://arxiv.org/abs/2610.30655</code>.";
      return;
    }
    var id = parsed.id, v = parsed.v, anc = anchorOf(id);
    title.textContent = "arXiv:" + id + v;
    status.textContent = "Looking in Paperlane's archive…";
    fetch(prefix + "p/" + anc + ".md", { method: "HEAD" }).then(function (r) {
      if (r.ok) { location.replace(prefix + "p/" + anc + ".html"); return "done"; }
    }).catch(function () {}).then(function (done) {
      if (done) return;
      status.textContent = "Not in Paperlane's archive yet. Fetching the details…";
      return fromSemanticScholar(id).then(function (d) {
        if (d && d.abstract) return d;
        return fromOpenAlex(id).then(function (o) { return d ? (o && o.abstract ? Object.assign(d, { abstract: o.abstract }) : d) : o; });
      }).then(function (d) { render(d); });
    });

    function render(d) {
      var abs = "https://arxiv.org/abs/" + id + v, pdf = "https://arxiv.org/pdf/" + id + v;
      if (!d) {
        title.textContent = "arXiv:" + id + v;
        status.innerHTML = "This paper is not in Paperlane's archive, and the open databases did not answer. It may be very new, or the free services may be busy.";
        result.innerHTML = '<div class="actions"><a class="act" href="' + abs + '">Open on arXiv</a><a class="act" href="' + pdf + '">PDF</a><a class="act" href="' + location.href + '">Try again</a></div>';
        return;
      }
      status.innerHTML = "Not listed by Paperlane yet, so these details come from " + esc(d.source) + ". Categories and comments are on arXiv.";
      var text = d.abstract || "";
      var links = findLinks(text);
      var code = links.filter(function (u) { try { return CODE_HOSTS.indexOf(new URL(u).hostname.replace(/^www\./, "")) >= 0; } catch (e) { return false; } });
      var badges = code.map(function (u) { return '<a class="sig code" href="' + esc(u) + '" rel="nofollow">code: ' + esc(u.replace(/^https?:\/\//, "")) + "</a>"; }).join("");
      if (LEAN_RE.test(text)) badges += '<span class="sig mention">mentions Lean</span>';
      var authors = d.authors.slice(0, 8).join(", ") + (d.authors.length > 8 ? " and " + (d.authors.length - 8) + " more" : "");
      result.innerHTML =
        '<article class="paper expanded" id="' + esc(anc) + '"><div class="top"><a class="aid" href="' + abs + '">arXiv:' + esc(id + v) + "</a>" + badges + "</div>" +
        "<h3><a href=\"" + abs + "\">" + esc(d.title) + "</a></h3><p class=\"authors\">" + esc(authors) + "</p>" +
        '<div class="abstract"><p>' + (text ? esc(text) : "No abstract was available from " + esc(d.source) + ". Read it on arXiv.") + "</p>" +
        (d.date ? '<p class="note"><b>Date</b> ' + esc(d.date) + "</p>" : "") + "</div>" +
        '<div class="actions"><button type="button" class="act" data-act="md" aria-expanded="false">Markdown</button><a class="act" href="' + pdf + '">PDF</a><a class="act" href="' + abs + '">arXiv</a>' +
        '<button type="button" class="act" data-act="link" data-url="' + esc(location.href) + '">Copy link</button></div><div class="md-panel" hidden></div></article>';
      var notes = code.map(function (u) { return "code " + u; });
      if (LEAN_RE.test(text)) notes.push("abstract mentions Lean");
      var mdBtn = $('[data-act="md"]', result);
      function makeMarkdown() {
        mdBtn.markdown = [
          "# " + d.title, "",
          "Not listed by Paperlane yet. Details come from " + d.source + ", and the full text is on arXiv.", "",
          "- arXiv: " + id + v + " · " + abs + " · PDF " + pdf,
          "- Authors: " + d.authors.join(", "),
        ].concat(d.date ? ["- Date: " + d.date] : [], notes.length ? ["- Signals: " + notes.join("; ")] : [], [
          "- Paperlane: " + base + "/paper.html?id=" + encodeURIComponent(id + v), "", "## Abstract", "", text || "Not available.", "",
        ]).join("\n");
      }
      makeMarkdown();
      renderMath(result);

      // Same Lean check as the daily job, run from the reader's browser.
      code.forEach(function (u, i) {
        var m = u.match(/github\.com\/([^\/]+)\/([^\/#?]+)/i);
        if (!m) return;
        var repo = m[1] + "/" + m[2].replace(/\.git$/, "");
        leanCheck(repo).then(function (paths) {
          if (!paths || !paths.length) return;
          var tag = document.createElement("a");
          tag.className = "sig lean";
          tag.href = u;
          tag.title = "Lean project: found " + paths.slice(0, 3).join(", ");
          tag.textContent = "Lean project";
          $$(".sig.code", result)[i].before(tag);
          notes[i] += " (Lean project: " + paths.slice(0, 3).join(", ") + ")";
          makeMarkdown();
        });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    theme();
    lookupForm();
    filters();
    cards();
    ask();
    lookupPage();
    renderMath($("main"));
  });
})();
