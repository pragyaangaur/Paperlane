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

  // An issue holds hundreds of abstracts, and typesetting them all at load is the slowest
  // thing on the page. Each card is typeset when it comes near the screen instead. Folded
  // and filtered cards are hidden, so they are never typeset until a reader shows them.
  function lazyMath(root) {
    var cards = $$("article.paper", root);
    if (cards.length < 12 || !("IntersectionObserver" in window)) { renderMath(root); return; }
    var seen = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        seen.unobserve(e.target);
        renderMath(e.target);
      });
    }, { rootMargin: "800px 0px" });
    cards.forEach(function (c) { seen.observe(c); });
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
    // A link from the home page can carry what the reader typed there.
    var given = new URLSearchParams(location.search).get("i");
    if (given) store.set("paperlane-interests", given.trim());
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
  // The home page is one box. Whatever the reader types is ranked against the latest issue as they type.
  function home() {
    if (!body.classList.contains("home")) return;
    if (/[?&](cat|q|code|lean|hide|sort)=/.test(location.search)) { location.replace("today.html" + location.search); return; }
    var root = $("#finder");
    if (!root) return;
    var input = $("#finder-q"), list = $("#finds"), foot = $("#finds-foot"), all = $("#finds-all"), ai = $("#finds-ai");
    var papers = null, ranker = null, loading = null, timer;

    function load() {
      if (!loading) loading = fetch("latest.json").then(function (r) { return r.json(); }).then(function (data) {
        papers = data.papers;
        ranker = new Ranker(papers.map(function (p) {
          return p.title + " " + p.title + " " + p.abstract + " " + (p.authors || []).join(" ");
        }));
      }).catch(function () { loading = null; });
      return loading;
    }
    function show() {
      var query = input.value.trim();
      $$(".tries button", root).forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.try === query); });
      if (!query) { list.innerHTML = ""; foot.hidden = true; root.classList.remove("open"); return; }
      load().then(function () {
        if (!ranker || input.value.trim() !== query) return;
        var ranked = ranker.rank(query).map(function (r, i) { return { r: r, p: papers[i] }; })
          .filter(function (x) { return x.r.score > 0; })
          .sort(function (a, b) { return b.r.score - a.r.score; });
        root.classList.add("open");
        if (!ranked.length) {
          list.innerHTML = '<li class="none">No paper in this issue matches that. Try a broader word.</li>';
          foot.hidden = true;
          return;
        }
        list.innerHTML = ranked.slice(0, 5).map(function (x) {
          var p = x.p, href = "p/" + p.id.replace("/", "-") + ".html";
          return '<li><a href="' + href + '"><span class="t">' + esc(p.title) + '</span><span class="m mono">' +
            esc((p.authors || [])[0] || "") + ((p.authors || []).length > 1 ? " et al." : "") + " · " +
            x.r.hits.slice(0, 3).map(function (h) { return "<mark>" + esc(h) + "</mark>"; }).join(" ") + "</span></a></li>";
        }).join("");
        renderMath(list);
        var n = ranked.length;
        all.textContent = n > 5 ? "see all " + n + " →" : "open in the issue →";
        all.href = "today.html?q=" + encodeURIComponent(query);
        ai.textContent = "have my AI explain these →";
        ai.href = "ask.html?i=" + encodeURIComponent(query);
        foot.hidden = false;
      });
    }
    input.addEventListener("focus", load);
    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(show, 90);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && input.value.trim()) { track("finder-enter"); location.href = "today.html?q=" + encodeURIComponent(input.value.trim()); }
    });
    $$(".tries button", root).forEach(function (b) {
      b.addEventListener("click", function () { input.value = b.dataset.try; track("finder-try"); show(); });
    });
    list.addEventListener("click", function (e) { if (e.target.closest("a")) track("finder-open"); });
  }

  // ---------- The issue page ----------
  // One search box. A query ranks the issue with BM25 and shows only the papers that match, best first.
  // With no query the papers sit under their fields, or in one list by date or length.
  function issue() {
    var bar = $("#filters");
    if (!bar) return;
    var list = $("#list"), flat = $("#flat");
    var papers = $$("article.paper", list);
    var groupOf = papers.map(function (p) { return p.parentNode; });
    var ranker = new Ranker(papers.map(function (p) {
      var title = $(".title", p).textContent;
      return title + " " + title + " " + $(".abstract", p).textContent + " " + $(".authors", p).textContent + " " + $(".tags", p).getAttribute("data-fields");
    }));
    var q = $("#f-q"), code = $("#f-code"), lean = $("#f-lean"), sub = $("#f-sub"), sortSel = $("#f-sort");
    var fieldsBtn = $("#f-fields"), panel = $("#f-panel");
    var catBoxes = $$('input[name="cat"]', panel), kindBoxes = $$('input[name="kind"]', panel);
    var names = {};
    catBoxes.forEach(function (b) { names[b.value] = $("span", b.parentNode).textContent; });
    var kindNames = { cross: "cross-lists", replace: "revised" };
    var lane = (store.get("paperlane-fields") || "").split(",").filter(Boolean);

    // Fields the reader picked before go to the top of the field order.
    lane.slice().reverse().forEach(function (c) {
      var g = $('section.group[data-field="' + c + '"]', list);
      if (g) list.insertBefore(g, list.firstChild);
    });

    var params = new URLSearchParams(location.search);
    // Older links ranked "for me" with ?sort=me&i=...; that is now a plain search.
    q.value = params.get("q") || params.get("i") || "";
    code.setAttribute("aria-pressed", params.get("code") === "1");
    lean.setAttribute("aria-pressed", params.get("lean") === "1");
    var cats = (params.get("cat") || "").split(",").filter(Boolean);
    catBoxes.forEach(function (b) { b.checked = cats.indexOf(b.value) >= 0; });
    var hide = (params.get("hide") || "").split(",").filter(Boolean);
    kindBoxes.forEach(function (b) { b.checked = hide.indexOf(b.value) < 0; });
    var sort = params.get("sort");
    sortSel.value = sort === "newest" || sort === "short" ? sort : "field";

    function pressed(b) { return b.getAttribute("aria-pressed") === "true"; }
    function state() {
      return {
        q: q.value.trim(),
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

    // Long issues fold: each field shows its first few papers, flat lists show a page at a time.
    var FOLD = 3, PAGE = 20;
    var expanded = {}, flatLimit = PAGE;
    var flatMore = $("#flat-more");

    function fold() {
      papers.forEach(function (p) { p.classList.remove("folded"); });
      if (!list.hidden) {
        $$("section.group", list).forEach(function (g) {
          var rows = $$("article.paper:not([hidden])", g);
          var more = $(".more", g), field = g.dataset.field;
          var name = $("h2 span", g).textContent;
          if (rows.length <= FOLD + 1) { more.hidden = true; return; }
          more.hidden = false;
          if (!expanded[field]) {
            rows.slice(FOLD).forEach(function (p) { if (!p.classList.contains("open")) p.classList.add("folded"); });
            more.textContent = (rows.length - FOLD) + " more in " + name + " ↓";
          } else more.textContent = "Show fewer ↑";
        });
        flatMore.hidden = true;
      } else {
        var rows = $$("article.paper:not([hidden])", flat);
        if (rows.length > flatLimit) {
          rows.slice(flatLimit).forEach(function (p) { if (!p.classList.contains("open")) p.classList.add("folded"); });
          flatMore.hidden = false;
          flatMore.textContent = (rows.length - flatLimit) + " more ↓";
        } else flatMore.hidden = true;
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

    // Puts the papers in order and returns which ones the query matched (null when there is no query).
    var lastKey = "";
    function arrange(s) {
      var key = s.q + "|" + sortSel.value;
      if (key !== lastKey) flatLimit = PAGE;
      lastKey = key;
      $$(".why", list.parentNode).forEach(function (w) { w.hidden = true; });
      if (s.q) {
        var ranked = ranker.rank(s.q), parsed = parseId(s.q);
        papers.forEach(function (p, i) {
          var r = ranked[i];
          p._score = r.score + (parsed && p.id === anchorOf(parsed.id) ? 100 : 0);
          var w = $(".why", p);
          if (r.score > 0) {
            w.innerHTML = "matched " + r.hits.slice(0, 4).map(function (h) { return "<mark>" + esc(h) + "</mark>"; }).join(" ");
            w.hidden = false;
          }
        });
        papers.slice().sort(function (a, b) { return b._score - a._score || a.dataset.order - b.dataset.order; })
          .forEach(function (p) { flat.appendChild(p); });
        list.hidden = true;
        flat.hidden = false;
        return function (p) { return p._score > 0; };
      }
      if (sortSel.value === "field") {
        papers.slice().sort(function (a, b) { return a.dataset.order - b.dataset.order; })
          .forEach(function (p) { var g = groupOf[papers.indexOf(p)]; g.insertBefore(p, $(".more", g)); });
        list.hidden = false;
        flat.hidden = true;
        return null;
      }
      var order = sortSel.value === "newest"
        ? papers.slice().sort(function (a, b) { return b.id.localeCompare(a.id); })
        : papers.slice().sort(function (a, b) { return (a.dataset.pages || 1e6) - (b.dataset.pages || 1e6) || a.dataset.order - b.dataset.order; });
      order.forEach(function (p) { flat.appendChild(p); });
      list.hidden = true;
      flat.hidden = false;
      return null;
    }

    function apply() {
      var s = state();
      var matches = arrange(s);
      var shown = 0;
      papers.forEach(function (p) {
        var pc = p.dataset.cats.split(" ");
        var ok =
          (!s.cats.length || s.cats.some(function (c) { return pc.indexOf(c) >= 0; })) &&
          s.hide.indexOf(p.dataset.kind) < 0 &&
          (!s.code || p.dataset.code) &&
          (!s.lean || p.dataset.lean) &&
          (!matches || matches(p));
        p.hidden = !ok;
        if (ok) shown++;
      });
      $$("section.group", list).forEach(function (g) {
        var n = $$("article.paper:not([hidden])", g).length;
        g.hidden = n === 0;
        $(".n", g).textContent = n;
      });
      var active = s.cats.length + s.hide.length + (s.code ? 1 : 0) + (s.lean ? 1 : 0) + (s.q ? 1 : 0);
      $("#f-count").textContent = s.q
        ? (shown === 1 ? "1 paper" : shown + " papers") + " on “" + s.q + "”, best match first"
        : active ? shown + " of " + papers.length + " papers" : papers.length + " papers";
      $(".sort", bar.nextElementSibling).hidden = !!s.q;
      $("#f-fields-n").textContent = s.cats.length || "";
      fieldsBtn.classList.toggle("on", s.cats.length > 0);
      $$("[data-clear]").forEach(function (b) { if (b.closest(".results")) b.hidden = !active; });
      $("#f-empty").hidden = shown > 0;
      fold();

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
      if (s.q) out.set("q", s.q);
      if (s.cats.length) out.set("cat", s.cats.join(","));
      if (s.code) out.set("code", "1");
      if (s.lean) out.set("lean", "1");
      if (s.hide.length) out.set("hide", s.hide.join(","));
      if (sortSel.value !== "field") out.set("sort", sortSel.value);
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
    sortSel.addEventListener("change", function () { track("sort-" + sortSel.value); apply(); });
    panel.addEventListener("change", function () {
      store.set("paperlane-fields", catBoxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; }).join(","));
      apply();
    });
    var timer;
    q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(apply, 120); });
    sub.addEventListener("input", function () {
      var needle = sub.value.trim().toLowerCase();
      catBoxes.forEach(function (b) {
        b.parentNode.hidden = needle && (b.parentNode.textContent + " " + b.value).toLowerCase().indexOf(needle) < 0;
      });
    });
    $$("[data-clear]").forEach(function (b) { b.addEventListener("click", window.paperlaneClear); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") togglePanel(false);
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); q.focus(); }
    });
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
  // The ask page builds a prompt and links that open common assistants with the prompt filled in.
  // ---------- Timezone picker ----------
  // A small searchable list. With no search it shows the reader's own zone and some common ones;
  // typing searches every zone by city, region, country or offset.
  var ZONE_NAMES = { "Asia/Calcutta": "Kolkata", "Asia/Saigon": "Ho Chi Minh City", "Asia/Katmandu": "Kathmandu", "Asia/Rangoon": "Yangon", "Europe/Kiev": "Kyiv", "UTC": "UTC" };
  var COUNTRIES = {
    "india": "Asia/Kolkata Asia/Calcutta", "usa": "America/New_York America/Chicago America/Denver America/Los_Angeles", "united states": "America/New_York America/Chicago America/Denver America/Los_Angeles",
    "eastern": "America/New_York", "central": "America/Chicago", "mountain": "America/Denver", "pacific": "America/Los_Angeles",
    "uk": "Europe/London", "united kingdom": "Europe/London", "england": "Europe/London", "britain": "Europe/London", "france": "Europe/Paris", "germany": "Europe/Berlin",
    "spain": "Europe/Madrid", "italy": "Europe/Rome", "netherlands": "Europe/Amsterdam", "switzerland": "Europe/Zurich", "sweden": "Europe/Stockholm", "poland": "Europe/Warsaw",
    "ireland": "Europe/Dublin", "portugal": "Europe/Lisbon", "greece": "Europe/Athens", "ukraine": "Europe/Kyiv Europe/Kiev", "russia": "Europe/Moscow", "turkey": "Europe/Istanbul",
    "japan": "Asia/Tokyo", "china": "Asia/Shanghai", "korea": "Asia/Seoul", "taiwan": "Asia/Taipei", "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong",
    "australia": "Australia/Sydney Australia/Melbourne Australia/Brisbane Australia/Perth Australia/Adelaide", "new zealand": "Pacific/Auckland",
    "canada": "America/Toronto America/Vancouver America/Halifax America/Edmonton", "brazil": "America/Sao_Paulo", "mexico": "America/Mexico_City", "argentina": "America/Argentina/Buenos_Aires",
    "chile": "America/Santiago", "colombia": "America/Bogota", "peru": "America/Lima", "south africa": "Africa/Johannesburg", "nigeria": "Africa/Lagos", "egypt": "Africa/Cairo", "kenya": "Africa/Nairobi",
    "uae": "Asia/Dubai", "emirates": "Asia/Dubai", "saudi": "Asia/Riyadh", "israel": "Asia/Jerusalem", "iran": "Asia/Tehran", "pakistan": "Asia/Karachi", "bangladesh": "Asia/Dhaka",
    "nepal": "Asia/Kathmandu Asia/Katmandu", "sri lanka": "Asia/Colombo", "vietnam": "Asia/Ho_Chi_Minh Asia/Saigon", "thailand": "Asia/Bangkok", "indonesia": "Asia/Jakarta",
    "malaysia": "Asia/Kuala_Lumpur", "philippines": "Asia/Manila",
  };
  // One or two well-known cities for most offsets, shown in offset order when the search box is empty.
  var COMMON = ["Pacific/Honolulu", "America/Anchorage", "America/Los_Angeles", "America/Denver", "America/Chicago", "America/New_York",
    "America/Sao_Paulo", "Atlantic/Azores", "Europe/London", "Africa/Lagos", "Europe/Paris", "Europe/Berlin", "Africa/Cairo", "Europe/Moscow",
    "Asia/Dubai", "Asia/Karachi", "Asia/Kolkata", "Asia/Calcutta", "Asia/Kathmandu", "Asia/Katmandu", "Asia/Dhaka", "Asia/Bangkok", "Asia/Shanghai", "Asia/Singapore",
    "Asia/Tokyo", "Australia/Sydney", "Pacific/Auckland"];
  function offsetMinutes(label) {
    var m = /([+-])(\d+)(?::(\d+))?/.exec(label || "");
    return m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3] || 0)) : 0;
  }
  function zoneCity(z) { return ZONE_NAMES[z] || z.split("/").pop().replace(/_/g, " "); }
  function zoneRegion(z) { return z.indexOf("/") < 0 ? "" : z.split("/").slice(0, -1).join(" / ").replace(/_/g, " "); }

  function tzPicker(root, zones, detected, offset) {
    var hidden = $("#routine-tz", root), btn = $(".tz-btn", root), pop = $(".tz-pop", root), q = $(".tz-q", root), list = $(".tz-list", root);
    var offs = {}, items = [], active = 0;
    var mins = {};
    zones.forEach(function (z) { offs[z] = offset(z); mins[z] = offsetMinutes(offs[z]); });
    var countryOf = {};
    Object.keys(COUNTRIES).forEach(function (c) { COUNTRIES[c].split(" ").forEach(function (z) { countryOf[z] = (countryOf[z] || "") + " " + c; }); });
    function hay(z) { return (zoneCity(z) + " " + z.replace(/_/g, " ") + " " + (countryOf[z] || "") + " " + offs[z]).toLowerCase(); }
    var hays = {};
    zones.forEach(function (z) { hays[z] = hay(z); });

    function label() {
      var z = hidden.value;
      $(".tz-name", btn).textContent = zoneCity(z);
      $(".tz-off", btn).textContent = offs[z] || "";
    }
    function draw() {
      var needle = q.value.trim().toLowerCase().replace(/^gmt/, "utc");
      if (!needle) {
        // The reader's own zone, then UTC, then the common cities from the most negative offset to the most positive.
        var seen = {};
        seen[detected] = seen.UTC = 1;
        var rest = COMMON.concat(hidden.value).filter(function (z) {
          if (seen[z] || zones.indexOf(z) < 0) return false;
          seen[z] = 1;
          return true;
        }).sort(function (a, b) { return mins[a] - mins[b]; });
        items = [detected, "UTC"].filter(function (z, i, all) { return zones.indexOf(z) >= 0 && all.indexOf(z) === i; }).concat(rest);
      } else {
        var words = needle.split(/\s+/);
        items = zones.filter(function (z) { return words.every(function (w) { return hays[z].indexOf(w) >= 0; }); });
        // A country typed in full comes first, then cities that start with the search, then the rest.
        var rank = function (z) {
          if ((" " + (countryOf[z] || "") + " ").indexOf(" " + needle + " ") >= 0) return 0;
          return zoneCity(z).toLowerCase().indexOf(needle) === 0 ? 1 : 2;
        };
        items.sort(function (a, b) { return rank(a) - rank(b) || mins[a] - mins[b]; });
      }
      active = Math.max(0, items.indexOf(hidden.value));
      list.innerHTML = items.length ? items.map(function (z, i) {
        return '<li role="option" data-z="' + esc(z) + '" aria-selected="' + (z === hidden.value) + '"' + (i === active ? ' class="on"' : "") + '>' +
          '<span class="c">' + esc(zoneCity(z)) + (z === detected ? ' <em class="mono">your zone</em>' : "") + '</span>' +
          '<span class="r mono">' + esc(zoneRegion(z)) + '</span><span class="o mono">' + esc(offs[z]) + "</span></li>";
      }).join("") : '<li class="none mono">No timezone matches that.</li>';
      if (!needle) list.insertAdjacentHTML("beforeend", '<li class="none mono">Type to search all ' + zones.length + " timezones.</li>");
    }
    function mark() {
      $$("li[data-z]", list).forEach(function (li, i) { li.classList.toggle("on", i === active); });
      var on = $("li.on", list);
      if (on) on.scrollIntoView({ block: "nearest" });
    }
    function open(yes) {
      pop.hidden = !yes;
      btn.setAttribute("aria-expanded", yes);
      if (yes) { q.value = ""; draw(); mark(); setTimeout(function () { q.focus(); }, 0); }
    }
    function pick(z) {
      hidden.value = z;
      label();
      open(false);
      btn.focus();
      hidden.dispatchEvent(new Event("change"));
    }
    btn.addEventListener("click", function () { open(pop.hidden); });
    q.addEventListener("input", function () { draw(); active = 0; mark(); });
    q.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(active + 1, items.length - 1); mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(active - 1, 0); mark(); }
      else if (e.key === "Enter") { e.preventDefault(); if (items[active]) pick(items[active]); }
      else if (e.key === "Escape") { open(false); btn.focus(); }
    });
    list.addEventListener("click", function (e) { var li = e.target.closest("li[data-z]"); if (li) pick(li.dataset.z); });
    document.addEventListener("click", function (e) { if (!pop.hidden && !root.contains(e.target)) open(false); });
    label();
  }

  function ask() {
    var root = $("#ask");
    if (!root) return;
    var box = $("#prompt"), interests = $("#interests"), workBox = $("#ask-work");
    var wanted = new URLSearchParams(location.search).get("mode");
    var mode = wanted === "curious" || wanted === "routine" ? wanted : "work";
    var timeBox = $("#ask-time"), timeInput = $("#routine-time"), hint = $("#time-hint"), tzSelect = $("#routine-tz");

    // Every timezone the browser knows, labelled with its current UTC offset. The reader's own zone is chosen first.
    function offsetOf(zone, when) {
      try {
        var part = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "shortOffset" }).formatToParts(when)
          .filter(function (p) { return p.type === "timeZoneName"; })[0];
        return part ? part.value.replace("GMT", "UTC") : "";
      } catch (e) { return ""; }
    }
    var now = new Date();
    var zones = [];
    try { zones = Intl.supportedValuesOf("timeZone").slice(); } catch (e) {}
    if (!zones.length) zones = ["Europe/London", "Europe/Berlin", "America/New_York", "America/Chicago", "America/Los_Angeles", "Asia/Kolkata", "Asia/Shanghai", "Asia/Tokyo", "Australia/Sydney"];
    var detected = "UTC";
    try { detected = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch (e) {}
    var saved = store.get("paperlane-timezone");
    if (zones.indexOf(detected) < 0) zones.unshift(detected);
    if (zones.indexOf("UTC") < 0) zones.unshift("UTC");
    tzSelect.value = saved && zones.indexOf(saved) >= 0 ? saved : detected;
    tzPicker($("#tz"), zones, detected, function (z) { return offsetOf(z, now); });

    function minutesIn(zone, when) {
      var parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(when);
      var h = 0, m = 0;
      parts.forEach(function (p) { if (p.type === "hour") h = Number(p.value); if (p.type === "minute") m = Number(p.value); });
      return h * 60 + m;
    }
    function hhmm(mins) { return String(Math.floor(mins / 60)).padStart(2, "0") + ":" + String(mins % 60).padStart(2, "0"); }
    // Paperlane publishes at about 05:30 UTC. Show that moment in the chosen timezone, using today's date so daylight saving is right.
    function timeHint() {
      var zone = tzSelect.value;
      var publish = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 5, 30));
      var arriveMins = minutesIn(zone, publish);
      var v = (timeInput.value || "07:30").split(":");
      var chosen = Number(v[0]) * 60 + Number(v[1]);
      var place = zoneCity(zone);
      if (chosen < arriveMins) {
        hint.textContent = "A new issue arrives at about " + hhmm(arriveMins) + " in " + place + ". At this time your routine would read the previous issue, so " + hhmm(Math.min(arriveMins + 30, 1439)) + " or later works better.";
        hint.classList.add("warn");
      } else {
        hint.textContent = "A new issue arrives at about " + hhmm(arriveMins) + " in " + place + ", so this time works well.";
        hint.classList.remove("warn");
      }
    }

    function update() {
      if (mode === "curious") {
        box.textContent =
          "Read " + base + "/latest-titles.md, the list of new maths papers from the latest Paperlane issue. " +
          "Pick the two results a curious person with no maths degree would find most surprising, read their abstracts in " +
          base + "/latest.md, and explain each one in plain words with an everyday example.";
      } else if (mode === "routine") {
        var when = timeInput.value || "07:30";
        var mine = interests.value.trim() || "X and Y";
        box.textContent =
          "Set up a routine that runs every weekday at " + when + " " + tzSelect.value + " time (" + offsetOf(tzSelect.value, now) + "). Each time it runs, read " + base +
          "/latest-titles.md, Paperlane's index of the newest maths papers, and check the issue date at the top. " +
          "If it is the same issue as on your last run, reply only: No new Paperlane issue today. " +
          "Otherwise, my interests are " + mine + ". Pick the papers that fit, read their abstracts in " + base +
          "/latest.md, and send me a short briefing with the three papers I should read, one line each on why, and a link to each paper.";
        timeHint();
      } else {
        var i = interests.value.trim() || "X and Y";
        box.textContent =
          "Read " + base + "/latest-titles.md, Paperlane's index of today's new maths papers. " +
          "My interests are " + i + ". Pick the candidates that fit, read their abstracts in " + base +
          "/latest.md, and tell me which three papers I should read and why.";
      }
      workBox.hidden = mode === "curious";
      timeBox.hidden = mode !== "routine";
      $("#ask-note").textContent = mode === "routine"
        ? "Paste it where your assistant sets up scheduled tasks or routines."
        : "Nothing you type here leaves your browser.";
      $$(".modes button", root).forEach(function (b) { b.setAttribute("aria-selected", b.dataset.mode === mode); });
    }
    $$(".modes button", root).forEach(function (b) {
      b.addEventListener("click", function () { mode = b.dataset.mode; update(); if (mode === "work") interests.focus(); });
    });
    interests.addEventListener("input", update);
    timeInput.addEventListener("input", update);
    tzSelect.addEventListener("change", function () { store.set("paperlane-timezone", tzSelect.value); update(); });
    document.addEventListener("interests", update);
    update();
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

  // ---------- Missing pages ----------
  // A link to a paper Paperlane never listed lands on the 404 page. Send it to the lookup instead.
  function notFound() {
    if (!body.classList.contains("notfound")) return;
    var m = /\/p\/([^/]+?)(?:\.html|\.md)?$/.exec(location.pathname) || /\/abs\/([^/]+)$/.exec(location.pathname);
    var parsed = m && parseId(decodeURIComponent(m[1]).replace(/^([a-z-]+(?:\.[A-Z]{2})?)-(\d{7})/, "$1/$2"));
    if (parsed) location.replace(body.dataset.prefix + "paper.html?id=" + encodeURIComponent(parsed.id + parsed.v));
  }

  // On the 404 page, "Read today's issue" sends a big accepted sheet flying across the screen before it opens the issue.
  var BIG_SHEET = '<svg viewBox="0 0 300 360" aria-hidden="true"><path class="s" d="M8 8h220l64 64v280H8z"/><path class="f" d="M228 8v64h64"/>' +
    '<path class="h" d="M40 98h150"/><path class="l" d="M40 62h110M40 98h170M40 132h210M40 162h190M40 192h220M40 222h150M40 282h200M40 312h110"/>' +
    '<rect class="q" x="214" y="302" width="14" height="14"/>' +
    '<g transform="rotate(-12 150 200)"><rect class="st" x="46" y="214" width="208" height="62" rx="8"/><text x="150" y="256" text-anchor="middle">ACCEPTED</text></g></svg>';
  function flyAway() {
    var link = $("[data-fly]");
    if (!link) return;
    link.addEventListener("click", function (e) {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      if (!document.body.animate || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) return;
      e.preventDefault();
      track("easter-egg-404");
      var layer = document.createElement("div");
      layer.className = "flight";
      layer.innerHTML = '<i class="gust"></i><i class="gust"></i><i class="gust"></i><div class="big-sheet">' + BIG_SHEET + "</div>";
      document.body.appendChild(layer);
      var sheet = $(".big-sheet", layer);
      // The last frames fade to plain paper, so the issue page opens on the same colour.
      var paper = getComputedStyle(document.body).backgroundColor;
      layer.animate([{ backgroundColor: "rgba(0,0,0,0)" }, { backgroundColor: "rgba(0,0,0,0)", offset: 0.78 }, { backgroundColor: paper }],
        { duration: 1500, fill: "forwards" });
      var go = function () { location.href = link.href; };
      $$(".gust", layer).forEach(function (g, i) {
        g.animate([{ transform: "translateX(-60vw) scaleX(0.4)", opacity: 0 }, { opacity: 1, offset: 0.4 }, { transform: "translateX(120vw) scaleX(1)", opacity: 0 }],
          { duration: 700, delay: i * 90, easing: "ease-in", fill: "forwards" });
      });
      sheet.animate([
        { transform: "translate(-70vw, 60vh) rotate(-55deg) scale(0.35)", opacity: 0.6 },
        { transform: "translate(-12vw, 6vh) rotate(-14deg) scale(0.9)", opacity: 1, offset: 0.45 },
        { transform: "translate(4vw, -4vh) rotate(8deg) scale(1.05)", offset: 0.7 },
        { transform: "translate(0, 0) rotate(0deg) scale(9)", opacity: 1 },
      ], { duration: 1500, easing: "cubic-bezier(0.45, 0.05, 0.4, 1)", fill: "forwards" }).onfinish = go;
      setTimeout(go, 2200);
    });
  }

  // ---------- Fresh wording ----------
  // "Last night" is right only on the day an issue comes out. After that the page names the day instead.
  function freshWording() {
    var now = new Date();
    var today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
    $$("[data-when]").forEach(function (el) {
      var p = el.dataset.when.split("-").map(Number);
      var issue = Date.UTC(p[0], p[1] - 1, p[2]);
      var days = Math.round((today - issue) / 864e5);
      el.textContent = days <= 0 ? "last night"
        : days === 1 ? "yesterday" : "on " + new Date(issue).toLocaleDateString("en-GB", { weekday: "long", timeZone: "UTC" });
    });
  }

  // ---------- Headline highlights ----------
  // The highlighter box behind an emphasised headline phrase is drawn per line, from the ink of the first
  // letter to the ink of the last, so italic side bearings never leave a gap or an overhang.
  var measureCtx = null;
  function ink(text, font) {
    measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
    measureCtx.font = font;
    var m = measureCtx.measureText(text);
    return { left: -m.actualBoundingBoxLeft, right: m.actualBoundingBoxRight, width: m.width };
  }
  function fitBands() {
    $$("h1 em, h2 em").forEach(function (em) {
      var head = em.closest("h1, h2");
      $$(".band", head).forEach(function (b) { b.remove(); });
      em.classList.remove("fit");
      var cs = getComputedStyle(em);
      if (cs.backgroundImage === "none") return;
      if (!em.dataset.split) {
        em.innerHTML = em.textContent.split(/(\s+)/).map(function (w) { return !w || /^\s+$/.test(w) ? w : '<span class="w">' + esc(w) + "</span>"; }).join("");
        em.dataset.split = "1";
      }
      var font = cs.fontStyle + " " + cs.fontWeight + " " + cs.fontSize + " " + cs.fontFamily;
      var size = parseFloat(cs.fontSize);
      var lines = [];
      $$(".w", em).forEach(function (w) {
        var r = w.getBoundingClientRect(), line = lines[lines.length - 1];
        if (!line || Math.abs(r.top - line.top) > size * 0.4) lines.push(line = { top: r.top, h: r.height, first: w, firstR: r });
        line.last = w; line.lastR = r;
      });
      var box = head.getBoundingClientRect();
      lines.forEach(function (line) {
        var a = line.first.textContent, z = line.last.textContent;
        var start = ink(a.charAt(0), font), end = ink(z.charAt(z.length - 1), font), word = ink(z, font);
        var left = line.firstR.left + start.left;
        var right = line.lastR.left + word.width - end.width + end.right;
        var band = document.createElement("span");
        band.className = "band";
        band.setAttribute("aria-hidden", "true");
        band.style.left = (left - box.left) + "px";
        band.style.width = Math.max(0, right - left) + "px";
        band.style.top = (line.top - box.top + (line.h - size * 0.5) * 0.88) + "px";
        band.style.height = size * 0.5 + "px";
        head.appendChild(band);
      });
      em.classList.add("fit");
    });
  }
  function bands() {
    fitBands();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitBands);
    var t;
    window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(fitBands, 80); });
  }

  // ---------- Sheets in the wind ----------
  // Small sheets of paper drift through the empty margins on wide screens. They move only when the page
  // scrolls: down blows them up and along, up brings them back the way they came.
  var SHEET = '<svg viewBox="0 0 30 36" aria-hidden="true"><path class="s" d="M2.5 2.5h18l7 7v24h-25z"/><path class="f" d="M20.5 2.5v7h7"/>' +
    '<path class="l" d="M7 13h12M7 18.5h15M7 24h9"/></svg>';
  function drift() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var layer = document.createElement("div");
    layer.className = "drift";
    layer.setAttribute("aria-hidden", "true");
    var seed = 7;
    function rnd() { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; }
    var sheets = [];
    for (var i = 0; i < 12; i++) {
      var el = document.createElement("i");
      el.innerHTML = SHEET;
      if (i % 4 === 1) el.classList.add("lit");
      layer.appendChild(el);
      sheets.push({
        el: el, side: i % 2, gx: 0.15 + rnd() * 0.7, y0: rnd(), speed: 0.18 + rnd() * 0.42,
        size: 16 + rnd() * 22, amp: 10 + rnd() * 26, phase: rnd() * 6.28, tilt: -30 + rnd() * 60,
      });
    }
    document.body.appendChild(layer);
    var content = $("main .wrap, main .hero") || $("main");
    var W = 0, H = 0, gutter = 0, left = 0, queued = false;
    function measure() {
      W = window.innerWidth; H = window.innerHeight;
      var box = content.getBoundingClientRect();
      left = box.left; gutter = Math.min(box.left, W - box.right);
      layer.hidden = gutter < 140;
      sheets.forEach(function (sh) { sh.el.style.width = sh.size + "px"; });
      draw();
    }
    function draw() {
      queued = false;
      if (layer.hidden) return;
      var y = window.scrollY;
      sheets.forEach(function (sh) {
        var t = y * sh.speed, span = H + 120;
        var top = (((sh.y0 * span - t) % span) + span) % span - 60;
        var base = sh.side ? W - gutter + sh.gx * (gutter - sh.size) : sh.gx * (gutter - sh.size);
        var x = base + Math.sin(t / 90 + sh.phase) * Math.min(sh.amp, gutter * 0.25);
        var rot = sh.tilt + Math.sin(t / 70 + sh.phase) * 35;
        var flip = 0.45 + 0.55 * Math.abs(Math.cos(t / 120 + sh.phase));
        sh.el.style.transform = "translate3d(" + x.toFixed(1) + "px," + top.toFixed(1) + "px,0) rotate(" + rot.toFixed(1) + "deg) scaleX(" + flip.toFixed(3) + ")";
      });
    }
    window.addEventListener("scroll", function () { if (!queued) { queued = true; requestAnimationFrame(draw); } }, { passive: true });
    window.addEventListener("resize", measure);
    measure();
  }

  // Counts sign-ups by page. The address itself goes only to Kit.
  function signups() {
    $$("form[data-signup]").forEach(function (f) {
      f.addEventListener("submit", function () { track("subscribe-" + f.dataset.signup); });
    });
    // Kit sends new subscribers back here with ?subscribed=1 after they submit the form.
    var form = $("form[data-signup]");
    if (form && new URLSearchParams(location.search).get("subscribed") === "1") {
      var note = document.createElement("p");
      note.className = "signup-done";
      note.textContent = "Almost done. Kit has sent you an email, and you are subscribed once you click the link in it.";
      form.replaceWith(note);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    interestsSync();
    signups();
    notFound();
    flyAway();
    freshWording();
    theme();
    lookupForm();
    home();
    issue();
    rows();
    ask();
    copyButtons();
    lookupPage();
    externalize();
    lazyMath($("main"));
    drift();
    bands();
  });
})();
