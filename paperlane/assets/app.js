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
    set: function (k, v) { try { v == null || v === "" ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) {} },
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function copy(text, button) {
    var label = button.textContent;
    var done = function () {
      button.textContent = "copied";
      setTimeout(function () { button.textContent = label; }, 1400);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, done);
    else done();
  }

  // Visitor counting with GoatCounter, if the site was built with a GoatCounter code.
  // No cookies and no personal data; events record which features people use.
  function track(name) {
    try {
      if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path: "event/" + name, title: name, event: true });
    } catch (e) {}
  }

  // Links that leave Paperlane (arXiv, PDFs, code) open in a new tab.
  function externalize(root) {
    $$('a[href^="http"]', root || document).forEach(function (a) {
      if (a.host === location.host) return;
      a.target = "_blank";
      if (!/noopener/.test(a.rel)) a.rel = (a.rel + " noopener").trim();
    });
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

  // ---------- Ranking ----------
  // BM25 over titles (counted twice), abstracts and field names, with a bonus when a phrase
  // from the reader's interests appears word for word. Everything runs in the browser.
  var STOP = {};
  ("a an and are as at be been by can for from has have in into is it its of on or our that the their them then there these this those to "
    + "via we what when where which while who with without also both each such than other some any all not only one two three new using use used "
    + "show shows shown prove proves proved study studies paper papers result results give gives given case cases work way well first second")
    .split(" ").forEach(function (w) { STOP[w] = 1; });

  function stem(w) {
    w = w.replace(/our(s|ing|ed)?$/, "or$1").replace(/is(e|es|ed|ing|ation|ations)$/, "iz$1");
    var rules = ["izations", "ization", "ations", "ation", "nesses", "ness", "ments", "ment", "ities", "ity", "ically", "ical", "ings", "ing", "ied", "ies", "ed"];
    for (var i = 0; i < rules.length; i++) {
      var s = rules[i];
      if (w.length - s.length >= 4 && w.slice(-s.length) === s) { w = w.slice(0, -s.length) + (s === "ies" || s === "ied" ? "y" : ""); break; }
    }
    if (/(s|x|z|ch|sh|o)es$/.test(w) && w.length > 5) w = w.slice(0, -2);
    else if (/[^su]s$/.test(w) && !/is$/.test(w) && w.length > 4) w = w.slice(0, -1);
    return w;
  }
  function tokens(text) {
    return (text || "").toLowerCase().replace(/\\[a-z]+/g, " ").replace(/[^a-z0-9]+/g, " ").split(" ")
      .filter(function (t) { return t.length > 2 && !STOP[t]; }).map(stem);
  }
  function Ranker(docs) {
    var df = {}, total = 0;
    this.docs = docs.map(function (text) {
      var seq = tokens(text), tf = {};
      seq.forEach(function (t) { tf[t] = (tf[t] || 0) + 1; });
      Object.keys(tf).forEach(function (t) { df[t] = (df[t] || 0) + 1; });
      total += seq.length;
      return { seq: seq, tf: tf, len: seq.length };
    });
    this.df = df;
    this.avg = total / Math.max(1, docs.length);
    this.n = docs.length;
  }
  Ranker.prototype.idf = function (t) {
    var d = this.df[t] || 0;
    return Math.log(1 + (this.n - d + 0.5) / (d + 0.5));
  };
  // Returns, for every document, {score, hits: [query words that matched, best first]}.
  Ranker.prototype.rank = function (query) {
    var self = this, k1 = 1.2, b = 0.75;
    var phrases = query.split(/[,;]+/).map(function (ph) {
      var words = ph.toLowerCase().match(/[a-z0-9]+/g) || [];
      return words.filter(function (w) { return w.length > 2 && !STOP[w]; }).map(function (w) { return { word: w, t: stem(w) }; });
    }).filter(function (ph) { return ph.length; });
    var terms = {};
    phrases.forEach(function (ph) { ph.forEach(function (q) { terms[q.t] = terms[q.t] || q.word; }); });
    return this.docs.map(function (d) {
      var score = 0, hits = [];
      Object.keys(terms).forEach(function (t) {
        var f = d.tf[t];
        if (!f) return;
        var s = self.idf(t) * (f * (k1 + 1)) / (f + k1 * (1 - b + b * d.len / self.avg));
        score += s;
        hits.push({ word: terms[t], s: s });
      });
      phrases.forEach(function (ph) {
        for (var i = 0; i + 1 < ph.length; i++) {
          for (var j = 0; j + 1 < d.seq.length; j++) {
            if (d.seq[j] === ph[i].t && d.seq[j + 1] === ph[i + 1].t) { score += 0.5 * (self.idf(ph[i].t) + self.idf(ph[i + 1].t)); break; }
          }
        }
      });
      hits.sort(function (x, y) { return y.s - x.s; });
      return { score: score, hits: hits.map(function (h) { return h.word; }) };
    });
  };

  // ---------- Shared bits ----------
  function interestsSync() {
    var inputs = $$("[data-interests]");
    var saved = store.get("paperlane-interests") || "";
    inputs.forEach(function (i) { i.value = saved; });
    inputs.forEach(function (i) {
      i.addEventListener("input", function () {
        inputs.forEach(function (o) { if (o !== i) o.value = i.value; });
        store.set("paperlane-interests", i.value.trim());
        document.dispatchEvent(new CustomEvent("interests"));
      });
    });
  }

  // Light is the default. The switch turns dark on and off and remembers it on this device.
  function theme() {
    var btn = $("[data-theme-toggle]");
    if (!btn) return;
    var root = document.documentElement;
    function show() {
      var dark = root.dataset.theme === "dark";
      btn.title = dark ? "Light mode" : "Dark mode";
      btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    }
    btn.addEventListener("click", function () {
      if (root.dataset.theme === "dark") { delete root.dataset.theme; store.set("paperlane-theme", null); }
      else { root.dataset.theme = "dark"; store.set("paperlane-theme", "dark"); }
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
      if (here && here.classList.contains("paper") && $(".head", here)) {
        e.preventDefault();
        if (here.hidden && window.paperlaneClear) window.paperlaneClear();
        openRow(here, true);
        if (window.paperlaneReveal) window.paperlaneReveal(here);
        here.scrollIntoView({ behavior: "smooth", block: "start" });
        history.replaceState(null, "", "#" + here.id);
        return;
      }
      input.value = parsed.id + parsed.v;
    });
  }

  // ---------- Home ----------
  function home() {
    if (!body.classList.contains("home")) return;
    if (/[?&](cat|q|code|lean|hide|sort)=/.test(location.search)) { location.replace("today.html" + location.search); return; }
    var boxes = $$(".ix");
    var go = $("#lane-go");
    var saved = (store.get("paperlane-fields") || "").split(",").filter(Boolean);
    boxes.forEach(function (t) { t.setAttribute("aria-pressed", saved.indexOf(t.dataset.cat) >= 0); });
    function update() {
      var cats = boxes.filter(function (t) { return t.getAttribute("aria-pressed") === "true"; }).map(function (t) { return t.dataset.cat; });
      var interests = (store.get("paperlane-interests") || "").trim();
      var params = [];
      if (cats.length) params.push("cat=" + cats.join(","));
      if (interests) params.push("sort=me");
      go.href = "today.html" + (params.length ? "?" + params.join("&") : "");
      go.textContent = cats.length || interests ? "Open my lane →" : "Open today's issue →";
      store.set("paperlane-fields", cats.join(","));
    }
    go.addEventListener("click", function () { track("open-lane"); });
    boxes.forEach(function (t) {
      t.addEventListener("click", function () { t.setAttribute("aria-pressed", t.getAttribute("aria-pressed") !== "true"); update(); });
    });
    document.addEventListener("interests", update);
    update();
  }

  // ---------- The issue page ----------
  function issue() {
    var bar = $("#filters");
    if (!bar) return;
    var list = $("#list"), flat = $("#flat");
    var papers = $$("article.paper", list);
    var groupOf = papers.map(function (p) { return p.parentNode; });
    var text = papers.map(function (p) {
      return [".title", ".authors", ".abstract"].map(function (s) { var el = $(s, p); return el ? el.textContent : ""; }).join(" ").concat(" " + p.id).toLowerCase().replace(/\s+/g, " ");
    });
    // Ranking text: the title counts twice, then the abstract and the field names.
    var ranker = new Ranker(papers.map(function (p) {
      var title = $(".title", p).textContent;
      return title + " " + title + " " + $(".abstract", p).textContent + " " + $(".tags", p).getAttribute("data-fields");
    }));
    var q = $("#f-q"), code = $("#f-code"), lean = $("#f-lean"), sub = $("#f-sub"), why = $("#f-why");
    var fieldsBtn = $("#f-fields"), panel = $("#f-panel"), meBox = $("#f-me"), interests = $("#f-interests");
    var catBoxes = $$('input[name="cat"]', panel), kindBoxes = $$('input[name="kind"]', panel);
    var seg = $$(".seg button");
    var names = {};
    catBoxes.forEach(function (b) { names[b.value] = $("span", b.parentNode).textContent; });
    var kindNames = { cross: "cross-lists", replace: "revised" };
    var lane = (store.get("paperlane-fields") || "").split(",").filter(Boolean);

    // Your own fields go to the top of the field order.
    lane.slice().reverse().forEach(function (c) {
      var g = $('section.group[data-field="' + c + '"]', list);
      if (g) list.insertBefore(g, list.firstChild);
    });

    var params = new URLSearchParams(location.search);
    q.value = params.get("q") || "";
    code.setAttribute("aria-pressed", params.get("code") === "1");
    lean.setAttribute("aria-pressed", params.get("lean") === "1");
    var cats = (params.get("cat") || "").split(",").filter(Boolean);
    catBoxes.forEach(function (b) { b.checked = cats.indexOf(b.value) >= 0; });
    var hide = (params.get("hide") || "").split(",").filter(Boolean);
    kindBoxes.forEach(function (b) { b.checked = hide.indexOf(b.value) < 0; });
    // A shared lane link can carry its interests.
    if (params.get("i")) {
      store.set("paperlane-interests", params.get("i"));
      $$("[data-interests]").forEach(function (el) { el.value = params.get("i"); });
    }
    var sort = params.get("sort") || (store.get("paperlane-interests") ? "me" : "field");

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

    // Long issues fold: each field shows its first few papers, flat orders show a page at a time.
    var FOLD = 3, PAGE = 25;
    var expanded = {}, flatLimit = PAGE;
    var flatMore = $("#flat-more"), jump = $("#jump");

    function fold(s) {
      var folding = !s.q;
      papers.forEach(function (p) { p.classList.remove("folded"); });
      if (!list.hidden) {
        $$("section.group", list).forEach(function (g) {
          var rows = $$("article.paper:not([hidden])", g);
          var more = $(".more", g), field = g.dataset.field;
          var name = $("h2 span", g).textContent;
          if (rows.length <= FOLD + 1) { more.hidden = true; return; }
          more.hidden = false;
          if (folding && !expanded[field]) {
            rows.slice(FOLD).forEach(function (p) { if (!p.classList.contains("open")) p.classList.add("folded"); });
            more.textContent = "Show all " + rows.length + " in " + name + " ↓";
          } else more.textContent = "Show fewer in " + name + " ↑";
        });
        flatMore.hidden = true;
      } else {
        var rows = $$("article.paper:not([hidden])", flat);
        if (folding && rows.length > flatLimit) {
          rows.slice(flatLimit).forEach(function (p) { if (!p.classList.contains("open")) p.classList.add("folded"); });
          flatMore.hidden = false;
          flatMore.textContent = "Show " + Math.min(PAGE, rows.length - flatLimit) + " more · " + (rows.length - flatLimit) + " left ↓";
        } else flatMore.hidden = true;
      }
      if (jump) {
        jump.hidden = !!list.hidden;
        $$("a", jump).forEach(function (a) {
          var g = document.getElementById(a.getAttribute("href").slice(1));
          a.hidden = !g || g.hidden;
          if (g) $("em", a).textContent = $(".n", g).textContent;
        });
      }
    }
    // Make sure one paper is on screen even if it sits in a folded part of the list.
    window.paperlaneReveal = function (row) {
      if (!row.classList.contains("folded")) return;
      var g = row.closest("section.group");
      if (g && g.dataset.field) expanded[g.dataset.field] = true;
      flatLimit = Infinity;
      apply();
    };
    $$("section.group .more", list).forEach(function (b) {
      b.addEventListener("click", function () {
        var g = b.closest("section.group"), field = g.dataset.field;
        expanded[field] = !expanded[field];
        apply();
        if (!expanded[field]) g.scrollIntoView({ block: "start" });
        track("show-all-field");
      });
    });
    flatMore.addEventListener("click", function () { flatLimit += PAGE; apply(); track("show-more"); });

    var meQuery = "";
    function arrange() {
      flatLimit = PAGE;
      seg.forEach(function (b) { b.setAttribute("aria-checked", b.dataset.sort === sort); });
      meBox.hidden = sort !== "me";
      $$(".why", list.parentNode).forEach(function (w) { w.hidden = true; });
      var query = interests.value.trim();
      meQuery = "";
      if (sort === "field" || (sort === "me" && !query)) {
        // Put every paper back in its field, in submission order.
        papers.slice().sort(function (a, b) { return a.dataset.order - b.dataset.order; })
          .forEach(function (p) { var g = groupOf[papers.indexOf(p)]; g.insertBefore(p, $(".more", g)); });
        list.hidden = false;
        flat.hidden = true;
        why.innerHTML = sort === "me"
          ? "Type what you work on and the list is ranked as you type."
          : "Grouped by main field, largest first" + (lane.length ? ", with your fields on top" : "") + ". Within a field, in order of submission.";
        return;
      }
      var order;
      if (sort === "me") {
        var ranked = ranker.rank(query);
        papers.forEach(function (p, i) {
          var r = ranked[i];
          p._score = r.score;
          var w = $(".why", p);
          if (r.score > 0) {
            w.innerHTML = "matched " + r.hits.slice(0, 4).map(function (h) { return "<mark>" + esc(h) + "</mark>"; }).join(" ");
            w.hidden = false;
          }
        });
        order = papers.slice().sort(function (a, b) { return b._score - a._score || a.dataset.order - b.dataset.order; });
        meQuery = query;
      } else if (sort === "newest") {
        order = papers.slice().sort(function (a, b) { return b.id.localeCompare(a.id); });
        why.textContent = "Latest submissions first.";
      } else {
        order = papers.slice().sort(function (a, b) { return (a.dataset.pages || 1e6) - (b.dataset.pages || 1e6) || a.dataset.order - b.dataset.order; });
        why.textContent = "Fewest pages first, as stated by the authors. Papers without a page count go last.";
      }
      order.forEach(function (p) { flat.appendChild(p); });
      list.hidden = true;
      flat.hidden = false;
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
      $$("section.group", list).forEach(function (g) {
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
      fold(s);
      if (meQuery) {
        var matched = papers.filter(function (p) { return !p.hidden && p._score > 0; }).length;
        why.innerHTML = "Ranked for <b>“" + esc(meQuery) + "”</b> with BM25 over titles and abstracts, in your browser. " +
          (matched === 1 ? "1 paper matches" : matched + " papers match") + ", and the rest follow in field order.";
      }

      var pills = $("#f-pills");
      pills.innerHTML = "";
      s.cats.forEach(function (c) {
        pills.appendChild(pill(names[c] || c, function () { catBoxes.forEach(function (b) { if (b.value === c) b.checked = false; }); }));
      });
      s.hide.forEach(function (k) {
        pills.appendChild(pill("no " + kindNames[k], function () { kindBoxes.forEach(function (b) { if (b.value === k) b.checked = true; }); }));
      });

      var hint = $("#f-lookup");
      var parsed = parseId(s.q);
      if (parsed && shown === 0) {
        hint.hidden = false;
        $("#f-empty").hidden = true;
        hint.innerHTML = esc(parsed.id) + " is not in this issue. <a href=\"" + prefix + "paper.html?id=" + encodeURIComponent(parsed.id + parsed.v) + "\">Open it anyway →</a>";
      } else hint.hidden = true;

      var out = new URLSearchParams();
      if (s.q) out.set("q", q.value.trim());
      if (s.cats.length) out.set("cat", s.cats.join(","));
      if (s.code) out.set("code", "1");
      if (s.lean) out.set("lean", "1");
      if (s.hide.length) out.set("hide", s.hide.join(","));
      if (sort !== "field") out.set("sort", sort);
      if (meQuery) out.set("i", meQuery);
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
    seg.forEach(function (b) {
      b.addEventListener("click", function () {
        sort = b.dataset.sort;
        track("sort-" + sort);
        arrange();
        apply();
        if (sort === "me" && !interests.value.trim()) interests.focus();
      });
    });
    var timer;
    document.addEventListener("interests", function () {
      clearTimeout(timer);
      timer = setTimeout(function () { if (sort === "me") { arrange(); apply(); } }, 120);
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
    arrange();
    apply();
  }

  // ---------- Paper entries ----------
  function openRow(row, open) {
    row.classList.toggle("open", open);
    var head = $(".head", row);
    if (head) head.setAttribute("aria-expanded", open);
  }

  function showMarkdown(panel, name, text, url) {
    panel.innerHTML =
      '<div class="md-bar"><span>' + esc(name) + '</span><button type="button" class="link" data-copy-md>copy</button>' +
      (url ? '<a href="' + esc(url) + '">raw</a>' : "") + "</div><pre></pre>";
    $("pre", panel).textContent = text;
    $("[data-copy-md]", panel).addEventListener("click", function (e) { track("copy-markdown"); copy(text, e.target); });
  }

  function rows() {
    document.addEventListener("click", function (e) {
      var head = e.target.closest("article.paper .head");
      if (head) {
        var row = head.closest("article.paper");
        if (!row.classList.contains("open")) track("open-paper");
        openRow(row, !row.classList.contains("open"));
        return;
      }
      var out = e.target.closest("a.pid, a.act[href*='/pdf/']");
      if (out) { track(/\/pdf\//.test(out.href) ? "open-pdf" : "open-arxiv"); return; }
      var btn = e.target.closest("[data-act]");
      if (!btn) return;
      var card = btn.closest("article.paper");
      if (btn.dataset.act === "link") { track("copy-link"); return copy(new URL(btn.dataset.url, location.href).href, btn); }
      var panel = $(".md-panel", card);
      var opening = panel.hidden;
      panel.hidden = !opening;
      btn.setAttribute("aria-expanded", opening);
      if (!opening) return;
      track("open-markdown");
      if (btn.markdown) return showMarkdown(panel, "paper.md", btn.markdown);
      if (panel.dataset.loaded) return;
      panel.dataset.loaded = "1";
      panel.innerHTML = '<div class="md-bar"><span>loading…</span></div>';
      fetch(btn.dataset.md).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      }).then(function (t) {
        showMarkdown(panel, btn.dataset.md.split("/").pop(), t, btn.dataset.md);
      }).catch(function () {
        delete panel.dataset.loaded;
        panel.innerHTML = '<div class="md-bar"><span>could not load the Markdown</span><a href="' + esc(btn.dataset.md) + '">open it</a></div>';
      });
    });
    if (location.hash) {
      var target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (target && target.classList.contains("paper")) openRow(target, true);
    }
  }

  // ---------- Ask your AI ----------
  function ask() {
    var dlg = $("#ask");
    if (!dlg) return;
    var box = $("#prompt"), interests = $("#interests"), workBox = $("#ask-work");
    var mode = "work";
    function update() {
      if (mode === "curious") {
        box.textContent =
          "Read " + base + "/latest-titles.md, the list of new maths papers from the latest Paperlane issue. " +
          "Pick the two results a curious person with no maths degree would find most surprising, read their abstracts in " +
          base + "/latest.md, and explain each one in plain words with an everyday example.";
      } else {
        var i = interests.value.trim() || "X and Y";
        box.textContent =
          "Read " + base + "/latest-titles.md, Paperlane's index of today's new maths papers. " +
          "My interests are " + i + ". Pick the candidates that fit, read their abstracts in " + base +
          "/latest.md, and tell me which three papers I should read and why.";
      }
      workBox.hidden = mode === "curious";
      $$(".modes button", dlg).forEach(function (b) { b.setAttribute("aria-selected", b.dataset.mode === mode); });
    }
    $$(".modes button", dlg).forEach(function (b) {
      b.addEventListener("click", function () { mode = b.dataset.mode; update(); });
    });
    interests.addEventListener("input", update);
    document.addEventListener("interests", update);
    update();
    $$("[data-open-ask]").forEach(function (b) {
      b.addEventListener("click", function () { track("open-ask-ai"); update(); dlg.showModal ? dlg.showModal() : dlg.setAttribute("open", ""); if (mode === "work") interests.focus(); });
    });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
    $("#copy-prompt").addEventListener("click", function (e) { track("copy-prompt-" + mode); copy(box.textContent, e.target); });
  }

  // Copy buttons that copy the text of another element, such as the curious prompt on the home page.
  function copyButtons() {
    $$("[data-copy-from]").forEach(function (b) {
      b.addEventListener("click", function () {
        var src = $(b.dataset.copyFrom);
        if (!src) return;
        track("copy-curious-prompt");
        copy(src.textContent, b);
      });
    });
  }

  // ---------- Lookup ----------
  // Paperlane's own pages first, then open scholarly APIs, because arXiv's API blocks browsers.
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
      return { title: d.title, abstract: d.abstract || "", date: d.publicationDate || "", authors: (d.authors || []).map(function (a) { return a.name; }) };
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
        title: d.title, abstract: words.join(" "), date: d.publication_date || "",
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
  function authorsText(a) {
    if (a.length <= 2) return a.join(" and ");
    var shown = a.slice(0, 12), rest = a.length - shown.length;
    return rest ? shown.join(", ") + " and " + rest + " more" : shown.slice(0, -1).join(", ") + " and " + shown[shown.length - 1];
  }

  function lookupPage() {
    var pageEl = $("#lk-page");
    if (!pageEl) return;
    var raw = new URLSearchParams(location.search).get("id");
    var status = $("#lk-status"), title = $("#lk-title");
    if (!raw) return;
    $("form.lookup input").value = raw;
    var parsed = parseId(raw);
    if (!parsed) {
      status.innerHTML = "That does not look like an arXiv link or id. Try one like <code>2610.30655</code>.";
      return;
    }
    var id = parsed.id, v = parsed.v, anc = anchorOf(id);
    track("lookup");
    title.innerHTML = "Opening <em>" + esc(id + v) + "</em>…";
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
        title.innerHTML = "Couldn't open <em>" + esc(id + v) + "</em>";
        status.innerHTML = "The paper may be very new, or the free lookup services may be busy.";
        $("#lk-result").innerHTML = '<p class="actions mono"><a class="act" href="' + esc(location.href) + '">try again</a><a class="act" href="' + pdf + '">pdf</a></p>';
        return;
      }
      document.title = d.title + " · Paperlane";
      var text = d.abstract || "";
      var code = findLinks(text).filter(function (u) { try { return CODE_HOSTS.indexOf(new URL(u).hostname.replace(/^www\./, "")) >= 0; } catch (e) { return false; } });
      var mentions = LEAN_RE.test(text);
      var tags = ['<span>' + esc(id + v) + "</span>"];
      if (code.length) tags.push('<span class="t-code">code</span>');
      if (mentions) tags.push('<span class="t-lean soft">□ lean</span>');
      var facts = code.map(function (u) { return '<div><dt class="mono">code</dt><dd><a href="' + esc(u) + '" rel="nofollow">' + esc(u.replace(/^https?:\/\//, "")) + "</a></dd></div>"; }).join("") +
        (d.date ? '<div><dt class="mono">date</dt><dd>' + esc(d.date) + "</dd></div>" : "");
      pageEl.classList.add("paper", "open");
      pageEl.id = anc;
      pageEl.innerHTML =
        '<p class="kicker mono">not yet in an issue</p><h1 class="title">' + esc(d.title) + '</h1><p class="authors">' + esc(authorsText(d.authors)) + "</p>" +
        '<p class="tags mono">' + tags.join('<span class="sep"> · </span>') + '</p><h2 class="abs-h">Abstract</h2>' +
        '<p class="abstract">' + (text ? esc(text) : "No abstract is available yet.") + '</p><dl class="facts">' + facts + "</dl>" +
        '<div class="actions mono"><button type="button" class="act" data-act="md" aria-expanded="false">markdown</button><a class="act" href="' + pdf + '">pdf</a>' +
        '<button type="button" class="act" data-act="link" data-url="' + esc(location.href) + '">copy link</button><a class="pid" href="' + abs + '">arXiv:' + esc(id + v) + " ↗</a></div>" +
        '<div class="md-panel" hidden></div>';
      var notes = code.map(function (u) { return "code " + u; });
      if (mentions) notes.push("abstract mentions Lean");
      var mdBtn = $('[data-act="md"]', pageEl);
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
      externalize(pageEl);
      renderMath(pageEl);
      code.forEach(function (u, i) {
        var m = u.match(/github\.com\/([^\/]+)\/([^\/#?]+)/i);
        if (!m) return;
        leanCheck(m[1] + "/" + m[2].replace(/\.git$/, "")).then(function (paths) {
          if (!paths || !paths.length) return;
          var t = $(".tags", pageEl);
          var soft = $(".t-lean.soft", t);
          if (soft) soft.outerHTML = '<span class="t-lean">∎ lean</span>';
          else t.insertAdjacentHTML("beforeend", '<span class="sep"> · </span><span class="t-lean">∎ lean</span>');
          notes[i] += " (Lean project: " + paths.slice(0, 2).join(", ") + ")";
          makeMarkdown();
        });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    interestsSync();
    theme();
    lookupForm();
    home();
    issue();
    rows();
    ask();
    copyButtons();
    lookupPage();
    externalize();
    renderMath($("main"));
  });
})();
