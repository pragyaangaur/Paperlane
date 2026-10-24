// Paperlane page behaviour. Without JavaScript every page still lists its papers and links.
(function () {
  "use strict";
  var body = document.body;
  var prefix = body.dataset.prefix || "";
  var base = (body.dataset.base || location.origin).replace(/\/$/, "");
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) {} },
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function copy(text, button) {
    var label = button.textContent;
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
    var m = s.match(/(?:^|[^\d.])(\d{4}\.\d{4,5})(v\d+)?(?![\d.])/) || s.match(/([a-z][a-z-]*(?:\.[A-Z]{2})?\/\d{7})(v\d+)?/i);
    return m ? { id: m[1], v: m[2] || "" } : null;
  }
  function anchorOf(id) { return id.replace("/", "-"); }

  // Theme: Auto follows the system. The choice is kept on this device.
  function theme() {
    var btn = $("[data-theme-toggle]");
    if (!btn) return;
    var order = ["auto", "light", "dark"];
    var names = { auto: "Auto", light: "Light", dark: "Dark" };
    var current = document.documentElement.dataset.theme || "auto";
    function show() { btn.title = "Theme: " + names[current] + " (click to switch)"; }
    btn.addEventListener("click", function () {
      current = order[(order.indexOf(current) + 1) % order.length];
      if (current === "auto") delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = current;
      store.set("paperlane-theme", current === "auto" ? null : current);
      show();
    });
    show();
  }

  // The header box opens any paper. A paper already on the page is scrolled to and opened.
  function lookupForm() {
    var form = $("form.lookup");
    if (!form) return;
    form.addEventListener("click", function () { $("input", form).focus(); });
    form.addEventListener("submit", function (e) {
      var input = $("input", form);
      var parsed = parseId(input.value);
      if (!parsed) return;
      var here = document.getElementById(anchorOf(parsed.id));
      if (here && here.classList.contains("paper")) {
        e.preventDefault();
        if (here.hidden && window.paperlaneClear) window.paperlaneClear();
        openRow(here, true);
        here.scrollIntoView({ behavior: "smooth", block: "start" });
        history.replaceState(null, "", "#" + here.id);
        return;
      }
      input.value = parsed.id + parsed.v;
    });
  }

  // Home page: field tiles and the big search box.
  function home() {
    if (!body.classList.contains("home")) return;
    // Old links pointed filters at the home page. Send them to today's list.
    if (/[?&](cat|q|code|lean|hide)=/.test(location.search)) { location.replace("today.html" + location.search); return; }
    var tiles = $$(".tile");
    var go = $("#fields-go"), clear = $("#fields-clear");
    var total = go.textContent;
    var saved = (store.get("paperlane-fields") || "").split(",").filter(Boolean);
    tiles.forEach(function (t) { t.setAttribute("aria-pressed", saved.indexOf(t.dataset.cat) >= 0); });
    function update() {
      var on = tiles.filter(function (t) { return t.getAttribute("aria-pressed") === "true"; });
      var n = on.reduce(function (sum, t) { return sum + Number($("em", t).textContent); }, 0);
      var cats = on.map(function (t) { return t.dataset.cat; });
      go.textContent = on.length ? "Show " + (on.length === 1 ? n + " papers" : "papers in " + on.length + " fields") + " →" : total;
      go.href = "today.html" + (on.length ? "?cat=" + cats.join(",") : "");
      clear.hidden = !on.length;
      store.set("paperlane-fields", cats.length ? cats.join(",") : null);
    }
    tiles.forEach(function (t) {
      t.addEventListener("click", function () { t.setAttribute("aria-pressed", t.getAttribute("aria-pressed") !== "true"); update(); });
    });
    clear.addEventListener("click", function () { tiles.forEach(function (t) { t.setAttribute("aria-pressed", "false"); }); update(); });
    update();
    $("#home-search").addEventListener("submit", function (e) {
      var input = $("input", e.target);
      var parsed = parseId(input.value);
      if (parsed) { e.preventDefault(); location.href = "paper.html?id=" + encodeURIComponent(parsed.id + parsed.v); }
      else if (!input.value.trim()) { e.preventDefault(); location.href = "today.html"; }
    });
  }

  // The filter toolbar on a day page.
  function filters() {
    var bar = $("#filters");
    if (!bar) return;
    var papers = $$("article.paper");
    var text = papers.map(function (p) {
      return [".title", ".authors", ".abstract"].map(function (s) { var el = $(s, p); return el ? el.textContent : ""; }).join(" ").concat(" " + p.id).toLowerCase().replace(/\s+/g, " ");
    });
    var groups = $$("section.group");
    var q = $("#f-q"), code = $("#f-code"), lean = $("#f-lean"), sub = $("#f-sub");
    var fieldsBtn = $("#f-fields"), panel = $("#f-panel");
    var catBoxes = $$('input[name="cat"]', panel), kindBoxes = $$('input[name="kind"]', panel);
    var names = {};
    catBoxes.forEach(function (b) { names[b.value] = $("span", b.parentNode).textContent; });
    var kindNames = { cross: "cross-lists", replace: "new versions" };

    var params = new URLSearchParams(location.search);
    q.value = params.get("q") || "";
    code.setAttribute("aria-pressed", params.get("code") === "1");
    lean.setAttribute("aria-pressed", params.get("lean") === "1");
    var cats = (params.get("cat") || "").split(",").filter(Boolean);
    catBoxes.forEach(function (b) { b.checked = cats.indexOf(b.value) >= 0; });
    var hide = (params.get("hide") || "").split(",").filter(Boolean);
    kindBoxes.forEach(function (b) { b.checked = hide.indexOf(b.value) < 0; });

    function pressed(b) { return b.getAttribute("aria-pressed") === "true"; }
    function state() {
      return {
        q: q.value.trim().toLowerCase(),
        code: pressed(code),
        lean: pressed(lean),
        cats: catBoxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; }),
        hide: kindBoxes.filter(function (b) { return !b.checked; }).map(function (b) { return b.value; }),
      };
    }
    function pill(label, onRemove) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "pill";
      b.innerHTML = esc(label) + ' <b aria-hidden="true">×</b>';
      b.setAttribute("aria-label", "Remove " + label);
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
      $("#f-count").textContent = active ? shown + " of " + papers.length + " papers" : papers.length + " papers";
      $("#f-fields-n").textContent = s.cats.length || "";
      fieldsBtn.classList.toggle("on", s.cats.length > 0);
      $$("[data-clear]").forEach(function (b) { if (b.closest(".results")) b.hidden = !active; });
      $("#f-empty").hidden = shown > 0;

      var pills = $("#f-pills");
      pills.innerHTML = "";
      s.cats.forEach(function (c) {
        pills.appendChild(pill(names[c] || c, function () { catBoxes.forEach(function (b) { if (b.value === c) b.checked = false; }); }));
      });
      s.hide.forEach(function (k) {
        pills.appendChild(pill("No " + kindNames[k], function () { kindBoxes.forEach(function (b) { if (b.value === k) b.checked = true; }); }));
      });

      // Someone typed an arXiv id that is not on this day: offer to open it anyway.
      var hint = $("#f-lookup");
      var parsed = parseId(s.q);
      if (parsed && shown === 0) {
        hint.hidden = false;
        $("#f-empty").hidden = true;
        hint.innerHTML = esc(parsed.id) + " is not on this day. <a href=\"" + prefix + "paper.html?id=" + encodeURIComponent(parsed.id + parsed.v) + "\">Open it anyway →</a>";
      } else hint.hidden = true;

      var out = new URLSearchParams();
      if (s.q) out.set("q", q.value.trim());
      if (s.cats.length) out.set("cat", s.cats.join(","));
      if (s.code) out.set("code", "1");
      if (s.lean) out.set("lean", "1");
      if (s.hide.length) out.set("hide", s.hide.join(","));
      var str = out.toString();
      history.replaceState(null, "", location.pathname + (str ? "?" + str.replace(/%2C/g, ",") : "") + location.hash);
    }

    window.paperlaneClear = function () {
      q.value = "";
      code.setAttribute("aria-pressed", "false");
      lean.setAttribute("aria-pressed", "false");
      catBoxes.forEach(function (b) { b.checked = false; });
      kindBoxes.forEach(function (b) { b.checked = true; });
      apply();
    };

    function togglePanel(open) {
      panel.hidden = !open;
      fieldsBtn.setAttribute("aria-expanded", open);
      if (open) setTimeout(function () { sub.focus(); }, 0);
    }
    fieldsBtn.addEventListener("click", function () { togglePanel(panel.hidden); });
    $("#f-done").addEventListener("click", function () { togglePanel(false); });
    $("#f-none").addEventListener("click", function () { catBoxes.forEach(function (b) { b.checked = false; }); apply(); });
    document.addEventListener("click", function (e) { if (!panel.hidden && !e.target.closest(".pop")) togglePanel(false); });
    [code, lean].forEach(function (b) {
      b.addEventListener("click", function () { b.setAttribute("aria-pressed", !pressed(b)); apply(); });
    });
    panel.addEventListener("change", apply);
    q.addEventListener("input", apply);
    sub.addEventListener("input", function () {
      var needle = sub.value.trim().toLowerCase();
      catBoxes.forEach(function (b) {
        b.parentNode.hidden = needle && (b.parentNode.textContent + " " + b.value).toLowerCase().indexOf(needle) < 0;
      });
    });
    $$("[data-clear]").forEach(function (b) { b.addEventListener("click", window.paperlaneClear); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") togglePanel(false);
      if (e.key === "/" && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); q.focus(); }
    });
    apply();
  }

  // Rows open and close. Single paper pages are always open.
  function openRow(row, open) {
    row.classList.toggle("open", open);
    $(".head", row).setAttribute("aria-expanded", open);
  }

  function showMarkdown(panel, name, text, url) {
    panel.innerHTML =
      '<div class="md-bar"><span>' + esc(name) + '</span><button type="button" class="link" data-copy-md>Copy</button>' +
      (url ? '<a href="' + esc(url) + '">Open raw</a>' : "") + "</div><pre></pre>";
    $("pre", panel).textContent = text;
    $("[data-copy-md]", panel).addEventListener("click", function (e) { copy(text, e.target); });
  }

  function rows() {
    var fixed = body.classList.contains("single") || body.classList.contains("lookup-page");
    document.addEventListener("click", function (e) {
      var head = e.target.closest("article.paper .head");
      if (head && !fixed) {
        var row = head.closest("article.paper");
        openRow(row, !row.classList.contains("open"));
        return;
      }
      var btn = e.target.closest("[data-act]");
      if (!btn) return;
      var card = btn.closest("article.paper");
      if (btn.dataset.act === "link") return copy(new URL(btn.dataset.url, location.href).href, btn);
      var panel = $(".md-panel", card);
      var opening = panel.hidden;
      panel.hidden = !opening;
      btn.setAttribute("aria-expanded", opening);
      if (!opening) return;
      if (btn.markdown) return showMarkdown(panel, "Markdown", btn.markdown);
      if (panel.dataset.loaded) return;
      panel.dataset.loaded = "1";
      panel.innerHTML = '<div class="md-bar"><span>Loading…</span></div>';
      fetch(btn.dataset.md).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      }).then(function (t) {
        showMarkdown(panel, btn.dataset.md.split("/").pop(), t, btn.dataset.md);
      }).catch(function () {
        delete panel.dataset.loaded;
        panel.innerHTML = '<div class="md-bar"><span>Could not load the Markdown.</span><a href="' + esc(btn.dataset.md) + '">Open it</a></div>';
      });
    });
    // A shared link to one paper opens it.
    if (location.hash) {
      var target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (target && target.classList.contains("paper")) openRow(target, true);
    }
  }

  // "Ask your AI" dialog.
  function ask() {
    var dlg = $("#ask");
    if (!dlg) return;
    var box = $("#prompt"), interests = $("#interests");
    interests.value = store.get("paperlane-interests") || "";
    function update() {
      var i = interests.value.trim() || "X and Y";
      box.value =
        "Read " + base + "/latest-titles.md, Paperlane's index of today's new maths papers. " +
        "My interests are " + i + ". Pick the candidates that fit, read their abstracts in " + base +
        "/latest.md, and tell me which three papers I should read and why.";
      store.set("paperlane-interests", interests.value || null);
    }
    interests.addEventListener("input", update);
    update();
    $$("[data-open-ask]").forEach(function (b) {
      b.addEventListener("click", function () { dlg.showModal ? dlg.showModal() : dlg.setAttribute("open", ""); interests.focus(); });
    });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
    $("#copy-prompt").addEventListener("click", function (e) { copy(box.value, e.target); });
  }

  // Lookup: Paperlane's own pages first, then open scholarly APIs (arXiv's API blocks browsers).
  var LEAN_RE = /\bLean[ ~]?4\b|\bMathlib\b|\b(?:in|using|with|into) Lean\b|\bLean (?:proof|formali[sz]ation|theorem prover|code|project|library)/;
  var CODE_HOSTS = ["github.com", "gitlab.com", "codeberg.org", "bitbucket.org", "git.sr.ht", "huggingface.co"];

  function getJSON(url) {
    return fetch(url).then(function (r) {
      if (r.status === 429) return new Promise(function (ok) { setTimeout(ok, 1500); }).then(function () { return fetch(url); });
      return r;
    }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }
  function fromSemanticScholar(id) {
    return getJSON("https://api.semanticscholar.org/graph/v1/paper/arXiv:" + id + "?fields=title,abstract,authors,publicationDate").then(function (d) {
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
    var status = $("#lk-status"), title = $("#lk-title"), eyebrow = $("#lk-eyebrow");
    if (!raw) return;
    $("form.lookup input").value = raw;
    var parsed = parseId(raw);
    if (!parsed) {
      status.innerHTML = "That does not look like an arXiv link or id. Try one like <code>2610.30655</code>.";
      return;
    }
    var id = parsed.id, v = parsed.v, anc = anchorOf(id);
    title.textContent = "Opening " + id + v + "…";
    status.textContent = "";
    fetch(prefix + "p/" + anc + ".md", { method: "HEAD" }).then(function (r) {
      if (r.ok) { location.replace(prefix + "p/" + anc + ".html"); return "done"; }
    }).catch(function () {}).then(function (done) {
      if (done) return;
      return fromSemanticScholar(id).then(function (d) {
        if (d && d.abstract) return d;
        return fromOpenAlex(id).then(function (o) { return d ? (o && o.abstract ? Object.assign(d, { abstract: o.abstract }) : d) : o; });
      }).then(render);
    });

    function render(d) {
      var abs = "https://arxiv.org/abs/" + id + v, pdf = "https://arxiv.org/pdf/" + id + v;
      if (!d) {
        title.textContent = "Couldn't load " + id + v;
        status.innerHTML = "The paper may be very new, or the free lookup services may be busy.";
        result.innerHTML = '<div class="actions"><a class="btn primary" href="' + location.href + '">Try again</a><a class="btn" href="' + pdf + '">Open the PDF</a></div>';
        return;
      }
      title.hidden = true;
      status.hidden = true;
      eyebrow.textContent = id + v;
      document.title = d.title + " · Paperlane";
      var text = d.abstract || "";
      var code = findLinks(text).filter(function (u) { try { return CODE_HOSTS.indexOf(new URL(u).hostname.replace(/^www\./, "")) >= 0; } catch (e) { return false; } });
      var mentions = LEAN_RE.test(text);
      var tagHtml = (mentions ? '<span class="tag lean-soft">Lean</span>' : "") + (code.length ? '<span class="tag code">Code</span>' : "");
      var facts = code.map(function (u) { return '<div><dt>Code</dt><dd><a href="' + esc(u) + '" rel="nofollow">' + esc(u.replace(/^https?:\/\//, "")) + "</a></dd></div>"; }).join("") +
        (d.date ? "<div><dt>Date</dt><dd>" + esc(d.date) + "</dd></div>" : "");
      var authors = d.authors.slice(0, 8).join(", ") + (d.authors.length > 8 ? " +" + (d.authors.length - 8) : "");
      result.innerHTML =
        '<article class="paper open" id="' + esc(anc) + '"><div class="head"><span class="title">' + esc(d.title) + '</span><span class="authors">' + esc(authors) +
        '</span><span class="tags">' + tagHtml + '</span></div><div class="body"><p class="abstract">' + (text ? esc(text) : "No abstract is available yet.") + "</p>" +
        '<dl class="facts">' + facts + "</dl>" +
        '<div class="actions"><button type="button" class="btn small" data-act="md" aria-expanded="false">Markdown</button><a class="btn small" href="' + pdf + '">PDF</a>' +
        '<button type="button" class="btn small ghost" data-act="link" data-url="' + esc(location.href) + '">Copy link</button><a class="pid" href="' + abs + '">arXiv ' + esc(id + v) + " ↗</a></div>" +
        '<div class="md-panel" hidden></div></div></article>';
      var notes = code.map(function (u) { return "code " + u; });
      if (mentions) notes.push("abstract mentions Lean");
      var mdBtn = $('[data-act="md"]', result);
      function makeMarkdown() {
        mdBtn.markdown = [
          "# " + d.title, "",
          "- arXiv: " + id + v + " · " + abs + " · PDF " + pdf,
          "- Authors: " + d.authors.join(", "),
        ].concat(d.date ? ["- Date: " + d.date] : [], notes.length ? ["- Signals: " + notes.join("; ")] : [], [
          "- Paperlane: " + base + "/paper.html?id=" + encodeURIComponent(id + v), "", "## Abstract", "", text || "Not available.", "",
        ]).join("\n");
      }
      makeMarkdown();
      renderMath(result);
      // The same Lean check as the daily job, run from the reader's browser.
      code.forEach(function (u, i) {
        var m = u.match(/github\.com\/([^\/]+)\/([^\/#?]+)/i);
        if (!m) return;
        leanCheck(m[1] + "/" + m[2].replace(/\.git$/, "")).then(function (paths) {
          if (!paths || !paths.length) return;
          var tags = $(".tags", result);
          var soft = $(".lean-soft", tags);
          if (soft) soft.remove();
          tags.insertAdjacentHTML("afterbegin", '<span class="tag lean">Lean project</span>');
          notes[i] += " (Lean project: " + paths.slice(0, 2).join(", ") + ")";
          makeMarkdown();
        });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    theme();
    lookupForm();
    home();
    filters();
    rows();
    ask();
    lookupPage();
    renderMath($("main"));
  });
})();
