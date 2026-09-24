// Deliberately dependency-free: the deployed artifact is three static files.
var AGENT = localStorage.getItem("agentUrl") || "";
var RESULTS = [];

function el(id) { return document.getElementById(id); }

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function rowHtml(r) {
  var cls = r.action === "add" ? "add" : "flag";
  var label = r.action === "add" ? "add" : "review";
  var conf = r.confidence == null ? "—" : Number(r.confidence).toFixed(2);
  var price = r.price == null ? "—" : "$" + Number(r.price).toFixed(2);
  var buy = r.buy || {};
  var src = buy.source && buy.source !== "plan" ? '<span class="src">' + esc(buy.source) + "</span>" : "";
  var product = r.title
    ? esc(r.title)
    : '<span style="color:var(--flag)">' + esc(r.reason || "needs a human") + "</span>";
  return '<tr>' +
    '<td><span class="pill ' + cls + '">' + label + "</span></td>" +
    '<td class="item">' + esc(buy.item || r.query) + src + "</td>" +
    '<td class="prod">' + product + "</td>" +
    '<td class="num">' + conf + "</td>" +
    '<td class="num">' + price + "</td>" +
    "</tr>";
}

function render(results) {
  RESULTS = results;
  el("rows").innerHTML = results.length
    ? results.map(rowHtml).join("")
    : '<tr><td colspan="5" class="empty">No lines to show.</td></tr>';

  var matched = results.filter(function (r) { return r.action === "add"; }).length;
  var review = results.length - matched;
  var priced = results.filter(function (r) { return r.price != null; });
  var total = priced.reduce(function (a, r) { return a + Number(r.price); }, 0);

  el("stats").innerHTML = [
    [results.length, "plan lines"],
    [matched, "auto-matched"],
    [review, "sent to a human"],
    [priced.length ? "$" + total.toFixed(2) : "—", "proposed cart"]
  ].map(function (s) {
    return '<div class="stat"><div class="n">' + s[0] + '</div><div class="k">' + s[1] + "</div></div>";
  }).join("");
}

function setMode(text, live) {
  el("mode").textContent = text;
  el("mode").style.background = live ? "#e6f6ed" : "#eef0ff";
  el("mode").style.color = live ? "#0a7d43" : "#4f46e5";
}

function load(url, live) {
  return fetch(url, { cache: "no-store" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (data) {
      render(data.results || []);
      var s = data.summary || {};
      el("note").innerHTML = "<strong>" + (s.added || 0) + " added to a real cart.</strong> " +
        "Nothing reached checkout — the run ends at the cart page and waits for a person. " +
        "Products shown are the live search results the agent matched on.";
      setMode(live ? "Live agent" : "Recorded run", live);
    })
    .catch(function (err) {
      el("note").innerHTML = "Could not load " + esc(url) + " — " + esc(err.message) + ".";
    });
}

el("match").onclick = function () {
  var q = el("q").value.trim();
  if (!q) return;
  if (!AGENT) {
    el("note").innerHTML = "<strong>Live matching needs the local agent.</strong> " +
      "The agent owns the Walmart session and runs on the machine with the login; " +
      "start it with <code>python -m meal_to_cart.server</code> and a tunnel, then set " +
      "<code>localStorage.agentUrl</code>. The recorded run below is the same code path.";
    return;
  }
  el("note").innerHTML = "Searching Walmart for " + esc(q) + "…";
  fetch(AGENT + "/match?q=" + encodeURIComponent(q))
    .then(function (r) { return r.json(); })
    .then(function (one) {
      if (one.error) { el("note").innerHTML = esc(one.error); return; }
      el("rows").insertAdjacentHTML("afterbegin", rowHtml(one));
      el("note").innerHTML = "<strong>" + esc(one.title || "no match") + "</strong>" +
        (one.price_text ? " · " + esc(one.price_text) : "");
      setMode("Live agent", true);
    })
    .catch(function (e) { el("note").innerHTML = esc(String(e)); });
};

el("live").onclick = function () {
  if (!AGENT) {
    AGENT = window.prompt("URL of the running agent (cloudflared tunnel or http://127.0.0.1:8787):", "");
    if (!AGENT) return;
    localStorage.setItem("agentUrl", AGENT);
  }
  load(AGENT + "/runs/latest", true);
};

load("data/demo-run.json", false);
