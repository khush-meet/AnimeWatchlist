const ALL = JSON.parse(document.getElementById("data").textContent);
const $ = id => document.getElementById(id);
const KEY = "animeWatchlistSeen";
let seen = new Set();
try { seen = new Set(JSON.parse(localStorage.getItem(KEY) || "[]")); } catch (e) {}
let path = "all", finish = {};
const TIER = { essential: 0, recommended: 1, optional: 2 };
const hours = x => x.eps * x.mins / 60;
const save = () => { try { localStorage.setItem(KEY, JSON.stringify([...seen])); } catch (e) {} };

function visible() {
  const q = $("q").value.trim().toLowerCase(), type = $("fType").value;
  const g = $("fGenre").value, src = $("fSrc").value, ord = $("fOrder").value;
  let r = ALL.filter(x =>
    (path === "all" || (path === "start" && x.tier === "essential") || (path === "dub" && x.hindi)) &&
    (!q || x.title.toLowerCase().includes(q)) &&
    (type === "all" || (type === "unwatched" ? !seen.has(x.id) : x.kind === type)) &&
    (!g || x.genres.includes(g)) && (!src || x.src === src));
  r.sort(ord === "release" ? (a, b) => a.year - b.year : (a, b) => TIER[a.tier] - TIER[b.tier] || a.year - b.year);
  return r;
}

function render() {
  const rows = visible(), list = $("list");
  list.innerHTML = "";
  rows.forEach(x => {
    const li = document.createElement("li");
    li.className = `item ${x.tier}${seen.has(x.id) ? " done" : ""}`;
    const eps = x.kind === "Movie" ? `${x.mins} min` : `${x.eps} eps`;
    li.innerHTML = `<input type="checkbox" aria-label="Mark ${x.title} as watched" ${seen.has(x.id) ? "checked" : ""}>
      <div><h3></h3><div class="meta"><span class="tag">${x.tier}</span>${x.hindi ? '<span class="tag dub">Hindi dub</span>' : ""}${eps}, ${hours(x).toFixed(1)} h, ${x.year}, ${x.genres.join("/")}${x.note ? "<br>" + x.note : ""}</div></div>
      <div class="fin">${finish[x.id] && !seen.has(x.id) ? "Done by " + finish[x.id] : ""}</div>`;
    li.querySelector("h3").textContent = x.title;
    li.querySelector("input").onchange = e => { e.target.checked ? seen.add(x.id) : seen.delete(x.id); save(); finish = {}; render(); };
    list.appendChild(li);
  });
  $("empty").hidden = rows.length > 0;
  const left = rows.filter(x => !seen.has(x.id));
  $("sTotal").textContent = rows.length;
  $("sSeen").textContent = rows.length - left.length;
  $("sLeft").textContent = left.length;
  $("sHours").textContent = Math.round(left.reduce((s, x) => s + hours(x), 0));
  $("bar").style.width = rows.length ? (100 * (rows.length - left.length) / rows.length) + "%" : "0";
}

function plan() {
  const hpw = Math.max(1, +$("hpw").value || 1), d = new Date();
  let done = 0; finish = {};
  const left = visible().filter(x => !seen.has(x.id));
  left.forEach(x => {
    done += hours(x);
    const dt = new Date(d.getTime() + (done / hpw) * 7 * 864e5);
    finish[x.id] = dt.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  });
  const last = left.length ? finish[left[left.length - 1].id] : null;
  $("planOut").textContent = last
    ? `${left.length} titles, ${Math.round(done)} hours. At ${hpw} h/week you finish on ${last}.`
    : "Nothing left to watch in this view.";
  render();
}

document.querySelectorAll(".paths button").forEach(b => b.onclick = () => {
  path = b.dataset.path; finish = {};
  document.querySelectorAll(".paths button").forEach(x => x.classList.toggle("on", x === b));
  render();
});
["q", "fType", "fGenre", "fSrc", "fOrder"].forEach(id => $(id).addEventListener("input", () => { finish = {}; render(); }));
$("plan").onclick = plan;
render();