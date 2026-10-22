// Vitrina: la app del celular. Sin dependencias; habla con la Mac por /api.
"use strict";

// ---------------------------------------------------------------- idioma
const EN = {
  "Subir": "Upload", "Fotos": "Photos", "Colecciones": "Collections", "Ajustes": "Settings",
  "Escanea el código": "Scan the code",
  "Abre Ajustes → Celular en la Vitrina y escanea el código con la cámara de tu celular.":
    "Open Settings → Phone on the Vitrina and scan the code with your phone's camera.",
  "El código ya venció. Escanea el que aparece ahora en la Vitrina.": "That code expired. Scan the one shown on the Vitrina now.",
  "Sube fotos y videos a la Vitrina.": "Add photos and videos to the Vitrina.",
  "Colección": "Collection", "Sin colección": "No collection", "Nueva": "New",
  "Elegir fotos y videos": "Choose photos and videos",
  "Mantén esta pantalla abierta mientras se suben.": "Keep this screen open while uploading.",
  "Subiendo {a} de {b}": "Uploading {a} of {b}", "Listo: {n} subidas": "Done: {n} uploaded", "No había nada nuevo": "Nothing new to add",
  "Preparando las fotos…": "Getting your photos ready…",
  "El celular las está alistando para subirlas. Con muchas fotos o videos puede tardar un poco.":
    "Your phone is preparing them for upload. With many photos or videos this can take a moment.",
  "En espera": "Waiting", "Lista": "Done", "Ya estaba": "Already there", "No compatible": "Not supported",
  "Error": "Error", "Reintentar": "Retry",
  "Todas": "All", "Seleccionar": "Select", "Cancelar": "Cancel", "Mover": "Move", "Borrar": "Delete",
  "{n} seleccionadas": "{n} selected", "Todavía no hay fotos aquí.": "No photos here yet.",
  "¿Borrar {n}?": "Delete {n}?", "Se mueven a la papelera de la Vitrina.": "They go to the Vitrina's trash.",
  "Mover a…": "Move to…", "Nueva colección": "New collection", "Nombre de la colección": "Collection name",
  "Crear": "Create", "Renombrar": "Rename", "Guardar": "Save", "Ver fotos": "View photos",
  "1 foto": "1 photo", "{n} fotos": "{n} photos", "1 video": "1 video", "{n} videos": "{n} videos",
  "Presentación": "Slideshow", "Pantalla": "Display",
  "Ken Burns": "Ken Burns", "Apagado": "Off", "Solo zoom": "Zoom only", "Zoom y paneo": "Zoom and pan",
  "Un día como hoy": "On this day", "Fecha y lugar": "Date and place", "Reloj": "Clock", "Oculto": "Hidden",
  "Orden aleatorio": "Shuffle", "Volver a la presentación": "Back to slideshow",
  "Idioma": "Language", "Apariencia": "Appearance", "Claro": "Light", "Oscuro": "Dark", "Automático": "Auto",
  "Modo noche": "Night mode", "Nunca": "Never", "Por horario": "Schedule", "Por la luz": "Room light",
  "Horario": "Schedule", "De noche": "At night", "Apagada": "Off", "Reloj ventana": "Window", "Reloj clásico": "Classic",
  "Color del reloj": "Clock color", "Blanco": "White", "Azul": "Blue", "Rojo": "Red",
  "Esta Mac no tiene sensor de luz.": "This Mac has no light sensor.",
  "Vitrina": "Vitrina", "Espacio": "Storage", "{a} libres de {b}": "{a} free of {b}",
  "Contenido": "Content", "Versión": "Version",
  "Desconectar este celular": "Disconnect this phone", "¿Desconectar este celular?": "Disconnect this phone?",
  "Para volver a usarlo tendrás que escanear el código otra vez.": "To use it again you'll need to scan the code again.",
  "Desconectar": "Disconnect", "Cerrar": "Close", "Sin conexión con la Vitrina": "Can't reach the Vitrina",
  "Guardado": "Saved", "Movidas": "Moved", "Borradas": "Deleted", "Ya existe una colección con ese nombre": "A collection with that name already exists",
};
let LANG = "es";
function t(s, vars) {
  let out = LANG === "en" && EN[s] !== undefined ? EN[s] : s;
  if (vars) for (const k in vars) out = out.replace("{" + k + "}", vars[k]);
  return out;
}
const count = (n, one, many) => (n === 1 ? t(one) : t(many, { n }));
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const collName = (c) => (c ? c : t("Sin colección"));

// ---------------------------------------------------------------- estado
const S = {
  tab: "upload", info: null, photos: [], filter: null,
  selecting: false, selected: new Set(), uploads: [], uploadColl: localStorage.getItem("coll") || "",
};
const $view = document.getElementById("view");

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (r.status === 401) { showWelcome(false); throw new Error("sin emparejar"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.error || "error"), { status: r.status });
  return data;
}

function toast(text) {
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = text;
  document.body.appendChild(el);
  setTimeout(() => { el.style.transition = "opacity .3s"; el.style.opacity = "0"; }, 1800);
  setTimeout(() => el.remove(), 2200);
}

// ---------------------------------------------------------------- arranque
async function start() {
  let me;
  try { me = await (await fetch("/api/me")).json(); } catch { me = { paired: false }; }
  LANG = me.language || "es";
  document.documentElement.lang = LANG;
  if (!me.paired) return showWelcome(new URLSearchParams(location.search).has("vencido"));
  history.replaceState(null, "", "/");
  document.getElementById("tabs").hidden = false;
  document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => go(b.dataset.tab)));
  await refresh();
  try {   // la Vitrina toma la zona horaria del celular (para su reloj)
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz) fetch("/api/timezone", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tz }) });
  } catch {}
  go(sessionStorage.getItem("tab") || "upload");
}

function showWelcome(expired) {
  document.getElementById("tabs").hidden = true;
  $view.innerHTML = `
    <div class="welcome">
      <div class="logo"><svg viewBox="0 0 24 24"><rect x="3" y="4.5" width="18" height="13" rx="2"/><path d="M8 21h8M12 17.5V21"/><path d="m3.5 14.5 4.5-4 3.5 3 3-2.5 6 4.5"/></svg></div>
      <h1>${t("Escanea el código")}</h1>
      <p>${t(expired ? "El código ya venció. Escanea el que aparece ahora en la Vitrina." :
        "Abre Ajustes → Celular en la Vitrina y escanea el código con la cámara de tu celular.")}</p>
    </div>`;
}

async function refresh() {
  const [info, photos] = await Promise.all([api("/api/info"), api("/api/photos")]);
  S.info = info; S.photos = photos;
  if (info.settings.language !== LANG) { LANG = info.settings.language; document.documentElement.lang = LANG; }
  document.querySelectorAll("[data-t]").forEach((el) => (el.textContent = t(el.dataset.t)));
}

function go(tab) {
  S.tab = tab; sessionStorage.setItem("tab", tab);
  if (tab !== "photos") { S.selecting = false; S.selected.clear(); }
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  render();
  window.scrollTo(0, 0);
}

function render() {
  ({ upload: renderUpload, photos: renderPhotos, collections: renderCollections, settings: renderSettings })[S.tab]();
  document.querySelectorAll(".seg").forEach((seg) => placePill(seg, true));
}

// ---------------------------------------------------------------- subir
function chipsHTML(active, withAll, withNew) {
  const cols = S.info.collections;
  let h = `<div class="chips">`;
  if (withAll) h += `<button class="chip ${active === null ? "on" : ""}" data-c="__all">${t("Todas")}</button>`;
  for (const c of cols) {
    if (withAll && !c.name && !c.count) continue;
    h += `<button class="chip ${active === c.name ? "on" : ""}" data-c="${esc(c.name)}">${esc(collName(c.name))}</button>`;
  }
  if (withNew) h += `<button class="chip" data-c="__new">+ ${t("Nueva")}</button>`;
  return h + `</div>`;
}

function renderUpload() {
  const ups = S.uploads;
  const done = ups.filter((u) => u.state !== "wait" && u.state !== "up").length;
  const added = ups.filter((u) => u.state === "added").length;
  const busy = ups.some((u) => u.state === "wait" || u.state === "up");
  const totalBytes = ups.reduce((a, u) => a + u.file.size, 0) || 1;
  const sentBytes = ups.reduce((a, u) => a + (u.state === "up" ? u.sent : u.state === "wait" ? 0 : u.file.size), 0);
  $view.innerHTML = `
    <h1>${t("Subir")}</h1>
    <p class="sub">${t("Sube fotos y videos a la Vitrina.")}</p>
    <div class="section" style="margin-top:8px">${t("Colección")}</div>
    ${chipsHTML(S.uploadColl, false, true)}
    <label class="btn">
      <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>${t("Elegir fotos y videos")}
      <input id="pick" type="file" accept="image/*,image/heic,image/heif,video/*" multiple hidden>
    </label>
    ${S.picking === "wait" ? `<div class="card preparing"><span class="spin"></span>
      <div><div class="title">${t("Preparando las fotos…")}</div>
      <div class="note">${t("El celular las está alistando para subirlas. Con muchas fotos o videos puede tardar un poco.")}</div></div></div>` : ""}
    ${ups.length ? `
      <div class="card uploads">
        <div class="summary">
          <div class="big">${busy ? t("Subiendo {a} de {b}", { a: Math.min(done + 1, ups.length), b: ups.length })
            : added ? t("Listo: {n} subidas", { n: added }) : t("No había nada nuevo")}</div>
          <div class="bar"><i style="width:${(100 * sentBytes / totalBytes).toFixed(1)}%"></i></div>
          ${busy ? `<div class="note" style="margin-top:8px;color:var(--text2);font-size:13px">${t("Mantén esta pantalla abierta mientras se suben.")}</div>` : ""}
        </div>
        ${ups.slice().reverse().map(upRow).join("")}
      </div>` : ""}`;
  const pick = $view.querySelector("#pick");
  pick.addEventListener("click", () => { S.picking = "open"; });
  pick.addEventListener("cancel", () => { S.picking = null; render(); });
  pick.addEventListener("change", (e) => { S.picking = null; addUploads([...e.target.files]); e.target.value = ""; });
  bindChips((c) => { S.uploadColl = c; localStorage.setItem("coll", c); render(); }, true);
}

function upRow(u) {
  const labels = { wait: t("En espera"), added: t("Lista"), duplicate: t("Ya estaba"), unsupported: t("No compatible"), error: t("Error") };
  const pct = u.file.size ? Math.round((100 * u.sent) / u.file.size) : 0;
  const cls = u.state === "added" ? "ok" : u.state === "error" || u.state === "unsupported" ? "err" : "";
  return `<div class="row up" data-u="${u.id}">
    <div class="thumb" style="${u.preview ? `background-image:url(${u.preview})` : ""}"></div>
    <div class="grow"><div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(u.file.name)}</div>
      ${u.state === "up" ? `<div class="bar"><i style="width:${pct}%"></i></div>` : ""}</div>
    <div class="state ${cls}">${u.state === "up" ? pct + "%" : labels[u.state]}</div>
  </div>`;
}

let uploadId = 0, wakeLock = null;
function addUploads(files) {
  for (const file of files) {
    const u = { id: ++uploadId, file, coll: S.uploadColl, state: "wait", sent: 0, preview: null };
    if (file.type.startsWith("image/")) u.preview = URL.createObjectURL(file);
    S.uploads.push(u);
  }
  pump();
  render();
}

let active = 0, redrawQueued = false;
function redrawUploads() {
  if (redrawQueued || S.tab !== "upload") return;
  redrawQueued = true;
  requestAnimationFrame(() => { redrawQueued = false; if (S.tab === "upload") renderUpload(); });
}

async function pump() {
  if (!wakeLock && navigator.wakeLock) { try { wakeLock = await navigator.wakeLock.request("screen"); } catch {} }
  while (active < 2) {
    const u = S.uploads.find((x) => x.state === "wait");
    if (!u) break;
    active++;
    u.state = "up";
    send(u).then((state) => { u.state = state; }).catch(() => { u.state = "error"; }).finally(() => {
      active--; redrawUploads();
      if (!S.uploads.some((x) => x.state === "wait" || x.state === "up")) finished();
      else pump();
    });
  }
  redrawUploads();
}

function send(u) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", "/api/upload");
    x.setRequestHeader("X-Name", encodeURIComponent(u.file.name));
    x.setRequestHeader("X-Collection", encodeURIComponent(u.coll));
    x.setRequestHeader("X-Modified", String(u.file.lastModified || 0));
    x.upload.onprogress = (e) => { u.sent = e.loaded; redrawUploads(); };
    x.onload = () => {
      try { resolve(JSON.parse(x.responseText).status || "error"); } catch { resolve("error"); }
    };
    x.onerror = reject;
    x.send(u.file);
  });
}

async function finished() {
  if (wakeLock) { try { await wakeLock.release(); } catch {} wakeLock = null; }
  // Las fotos nuevas tardan unos segundos en prepararse en la Mac.
  for (let i = 0; i < 6; i++) {
    await new Promise((r) => setTimeout(r, 2500));
    try { await refresh(); } catch { return; }
    if (S.tab !== "upload") render();
    if (!S.photos.some((p) => !p.r)) break;
  }
}

// ---------------------------------------------------------------- fotos
function renderPhotos() {
  const list = S.photos.filter((p) => S.filter === null || p.c === S.filter);
  const nSel = S.selected.size;
  $view.innerHTML = `
    <div class="head"><h1>${t("Fotos")}</h1>
      <button class="link" id="sel">${S.selecting ? t("Cancelar") : t("Seleccionar")}</button></div>
    <p class="sub">${S.selecting ? t("{n} seleccionadas", { n: nSel }) : summary(list)}</p>
    ${chipsHTML(S.filter, true, false)}
    ${list.length ? `<div class="grid">${list.map(cell).join("")}</div>` : `<div class="empty">${t("Todavía no hay fotos aquí.")}</div>`}`;
  $view.querySelector("#sel").onclick = () => { S.selecting = !S.selecting; S.selected.clear(); render(); };
  bindChips((c) => { S.filter = c; render(); }, false);
  $view.querySelectorAll(".cell").forEach((el) => {
    el.onclick = () => {
      const id = el.dataset.id;
      if (S.selecting) {
        S.selected.has(id) ? S.selected.delete(id) : S.selected.add(id);
        el.classList.toggle("sel");
        $view.querySelector(".sub").textContent = t("{n} seleccionadas", { n: S.selected.size });
        updateActions();
      } else openViewer(id);
    };
  });
  $view.querySelectorAll(".cell img").forEach((img) => {
    if (img.complete) img.classList.add("loaded");
    else img.onload = () => img.classList.add("loaded");
  });
  updateActions();
}

// Barra de Mover / Borrar: aparece al seleccionar algo, sin redibujar la cuadrícula.
function updateActions() {
  let bar = $view.querySelector(".actions");
  const want = S.selecting && S.selected.size > 0;
  if (want && !bar) {
    bar = document.createElement("div");
    bar.className = "actions";
    bar.innerHTML = `<button class="btn soft" id="mv">${t("Mover")}</button><button class="btn del" id="rm">${t("Borrar")}</button>`;
    bar.querySelector("#mv").onclick = () => moveTo([...S.selected]);
    bar.querySelector("#rm").onclick = () => remove([...S.selected]);
    $view.appendChild(bar);
  } else if (!want && bar) bar.remove();
}

function summary(list) {
  const v = list.filter((p) => p.v).length, f = list.length - v;
  return [count(f, "1 foto", "{n} fotos"), v ? count(v, "1 video", "{n} videos") : ""].filter(Boolean).join(" · ");
}

function cell(p) {
  const dur = p.v ? `<span class="dur">${Math.floor(p.dur / 60)}:${String(p.dur % 60).padStart(2, "0")}</span>` : "";
  return `<button class="cell ${S.selected.has(p.id) ? "sel" : ""}" data-id="${p.id}">
    ${p.r ? `<img loading="lazy" src="/t/${p.id}.jpg" alt="">` : ""}${dur}${S.selecting ? `<span class="check"></span>` : ""}</button>`;
}

function openViewer(id) {
  const p = S.photos.find((x) => x.id === id);
  if (!p || !p.r) return;
  const v = document.getElementById("viewer");
  const d = new Date(p.d + "T12:00:00");
  const date = d.toLocaleDateString(LANG === "en" ? "en-US" : "es-MX", { day: "numeric", month: "long", year: "numeric" });
  v.innerHTML = `
    <div class="top"><button class="x" id="vx">${t("Cerrar")}</button>
      <div class="meta">${esc(date)}<br>${esc(p.p ? (p.c ? p.p + " · " + p.c : p.p) : collName(p.c))}</div><span style="width:52px"></span></div>
    <div class="pic"><img src="/s/${p.id}.jpg" alt=""></div>
    <div class="bottom"><button class="btn" id="vm">${t("Mover")}</button><button class="btn del" id="vd">${t("Borrar")}</button></div>`;
  v.hidden = false;
  const close = () => { v.hidden = true; v.innerHTML = ""; };
  v.querySelector("#vx").onclick = close;
  v.querySelector("#vm").onclick = () => moveTo([id], close);
  v.querySelector("#vd").onclick = () => remove([id], close);
}

async function moveTo(ids, after) {
  const opts = S.info.collections.map((c) => ({ label: collName(c.name), value: c.name }));
  opts.push({ label: "+ " + t("Nueva colección"), value: "__new" });
  let c = await sheet(t("Mover a…"), opts);
  if (c === null) return;
  if (c === "__new") { c = await ask(t("Nueva colección"), "", t("Crear")); if (!c) return; }
  await api("/api/move", { ids, collection: c });
  toast(t("Movidas"));
  done(after);
}

async function remove(ids, after) {
  const n = ids.length;
  const ok = await sheet(t("¿Borrar {n}?", { n: count(n, "1 foto", "{n} fotos") }) + " " + t("Se mueven a la papelera de la Vitrina."),
    [{ label: t("Borrar"), value: true, danger: true }]);
  if (!ok) return;
  await api("/api/delete", { ids });
  toast(t("Borradas"));
  done(after);
}

async function done(after) {
  if (after) after();
  S.selecting = false; S.selected.clear();
  await new Promise((r) => setTimeout(r, 400));
  await refresh(); render();
}

// ---------------------------------------------------------------- colecciones
function renderCollections() {
  const cover = {};
  for (const p of S.photos) if (p.r && !(p.c in cover)) cover[p.c] = p.id;
  const cols = S.info.collections.filter((c) => c.name || c.count);
  $view.innerHTML = `
    <div class="head"><h1>${t("Colecciones")}</h1><button class="link" id="new">+ ${t("Nueva")}</button></div>
    <div class="card">${cols.map((c) => `
      <div class="row coll" data-c="${esc(c.name)}">
        <div class="cover" style="${cover[c.name] ? `background-image:url(/t/${cover[c.name]}.jpg)` : ""}"></div>
        <button class="grow" data-open style="text-align:left"><div class="title">${esc(collName(c.name))}</div>
          <div class="note">${count(c.count, "1 foto", "{n} fotos")}</div></button>
        ${c.name ? `<button class="more" data-more aria-label="${t("Renombrar")}">⋯</button>` : ""}
      </div>`).join("")}</div>`;
  $view.querySelector("#new").onclick = async () => {
    const name = await ask(t("Nueva colección"), "", t("Crear"));
    if (!name) return;
    await api("/api/collections/create", { name });
    await refresh(); render();
  };
  $view.querySelectorAll(".coll").forEach((row) => {
    const c = row.dataset.c;
    row.querySelector("[data-open]").onclick = () => { S.filter = c; go("photos"); };
    const more = row.querySelector("[data-more]");
    if (more) more.onclick = async () => {
      const name = await ask(t("Renombrar"), c, t("Guardar"));
      if (!name || name === c) return;
      try { await api("/api/collections/rename", { old: c, new: name }); }
      catch (e) { if (e.status === 409) toast(t("Ya existe una colección con ese nombre")); return; }
      await new Promise((r) => setTimeout(r, 300));
      await refresh(); render();
    };
  });
}

// ---------------------------------------------------------------- ajustes
const OPTS = {
  kenburns: [["off", "Apagado"], ["zoom", "Solo zoom"], ["pan", "Zoom y paneo"]],
  clock: [["off", "Oculto"], ["12", "12 h"], ["24", "24 h"]],
  idle_seconds: [[10, "10 s"], [15, "15 s"], [30, "30 s"], [60, "1 min"]],
  language: [["es", "Español"], ["en", "English"]],
  theme: [["light", "Claro"], ["dark", "Oscuro"], ["auto", "Automático"]],
  night: [["never", "Nunca"], ["schedule", "Por horario"], ["light", "Por la luz"]],
  night_hours: [["22-7", "22–7"], ["23-7", "23–7"], ["0-6", "0–6"]],
  night_style: [["off", "Apagada"], ["window", "Reloj ventana"], ["classic", "Reloj clásico"]],
  night_color: [["white", "Blanco"], ["blue", "Azul"], ["red", "Rojo"]],
};

function segRow(key, title, enabled = true) {
  const val = S.info.settings[key];
  return `<div class="row stack"><div class="title">${t(title)}</div>
    <div class="seg ${enabled ? "" : "off"}" data-k="${key}"><span class="pill"></span>
      ${OPTS[key].map(([v, l]) => `<button class="${v === val ? "on" : ""}" data-v="${v}">${t(l)}</button>`).join("")}</div></div>`;
}
function switchRow(key, title) {
  return `<button class="row" data-sw="${key}"><span class="grow title">${t(title)}</span>
    <span class="switch ${S.info.settings[key] ? "on" : ""}"></span></button>`;
}
const gb = (b) => (b / 1e9 >= 100 ? Math.round(b / 1e9) : (b / 1e9).toFixed(1)) + " GB";

function renderSettings() {
  const s = S.info.settings, i = S.info;
  const nightOn = s.night !== "never";
  $view.innerHTML = `
    <h1>${t("Ajustes")}</h1>
    <div class="section">${t("Presentación")}</div>
    <div class="card">
      ${segRow("kenburns", "Ken Burns")}
      ${switchRow("memories", "Un día como hoy")}
      ${switchRow("show_info", "Fecha y lugar")}
      ${segRow("clock", "Reloj")}
      ${switchRow("shuffle", "Orden aleatorio")}
      ${segRow("idle_seconds", "Volver a la presentación")}
    </div>
    <div class="section">${t("Pantalla")}</div>
    <div class="card">
      ${segRow("language", "Idioma")}
      ${segRow("theme", "Apariencia")}
      ${segRow("night", "Modo noche")}
      ${s.night === "light" && !i.light_sensor ? `<div class="row"><span class="note">${t("Esta Mac no tiene sensor de luz.")}</span></div>` : ""}
      ${segRow("night_hours", "Horario", s.night === "schedule")}
      ${segRow("night_style", "De noche", nightOn)}
      ${segRow("night_color", "Color del reloj", nightOn && s.night_style === "classic")}
    </div>
    <div class="section">${t("Vitrina")}</div>
    <div class="card">
      ${i.disk ? `<div class="row stack"><div style="display:flex;justify-content:space-between"><span class="title">${t("Espacio")}</span>
        <span class="value">${t("{a} libres de {b}", { a: gb(i.disk.free), b: gb(i.disk.total) })}</span></div>
        <div class="disk"><i style="width:${(100 * (1 - i.disk.free / i.disk.total)).toFixed(1)}%"></i></div></div>` : ""}
      <div class="row"><span class="grow title">${t("Contenido")}</span><span class="value">${count(i.photos, "1 foto", "{n} fotos")} · ${count(i.videos, "1 video", "{n} videos")}</span></div>
      <div class="row"><span class="grow title">${t("Versión")}</span><span class="value">${esc(i.version)}</span></div>
    </div>
    <div class="card" style="margin-top:24px"><button class="row danger" id="unpair">${t("Desconectar este celular")}</button></div>
    <p class="sub" style="text-align:center;margin-top:18px">github.com/Danzelote/Vitrina · ko-fi.com/danzelot</p>`;
  $view.querySelectorAll(".seg").forEach((seg) => seg.querySelectorAll("button").forEach((b) => {
    b.onclick = () => {
      const raw = b.dataset.v, k = seg.dataset.k;
      const v = OPTS[k].find(([x]) => String(x) === raw)[0];
      seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      placePill(seg);
      save({ [k]: v }, ["night", "night_style", "language"].includes(k));
    };
  }));
  $view.querySelectorAll("[data-sw]").forEach((row) => {
    row.onclick = () => {
      const k = row.dataset.sw, v = !S.info.settings[k];
      row.querySelector(".switch").classList.toggle("on", v);
      save({ [k]: v }, false);
    };
  });
  $view.querySelector("#unpair").onclick = async () => {
    const ok = await sheet(t("¿Desconectar este celular?") + " " + t("Para volver a usarlo tendrás que escanear el código otra vez."),
      [{ label: t("Desconectar"), value: true, danger: true }]);
    if (!ok) return;
    await fetch("/api/unpair", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    showWelcome(false);
  };
}

async function save(changes, rerender) {
  Object.assign(S.info.settings, changes);
  try { await api("/api/settings", changes); } catch { toast(t("Sin conexión con la Vitrina")); return; }
  if ("language" in changes) {
    LANG = changes.language; document.documentElement.lang = LANG;
    document.querySelectorAll("[data-t]").forEach((el) => (el.textContent = t(el.dataset.t)));
  }
  if (rerender) setTimeout(render, 280);   // deja terminar la animación de la pastilla
}

function placePill(seg, instant) {
  const on = seg.querySelector("button.on"), pill = seg.querySelector(".pill");
  if (!pill) return;
  if (instant) pill.style.transition = "none";
  if (!on) pill.style.width = "0";
  else {
    pill.style.width = on.offsetWidth + "px";
    pill.style.transform = `translateX(${on.offsetLeft}px)`;
  }
  if (instant) { pill.offsetWidth; pill.style.transition = ""; }
}

// ---------------------------------------------------------------- piezas comunes
function bindChips(onPick, allowNew) {
  $view.querySelectorAll(".chip").forEach((ch) => {
    ch.onclick = async () => {
      const c = ch.dataset.c;
      if (c === "__all") return onPick(null);
      if (c === "__new" && allowNew) {
        const name = await ask(t("Nueva colección"), "", t("Crear"));
        if (!name) return;
        const r = await api("/api/collections/create", { name });
        await refresh();
        return onPick(r.name);
      }
      onPick(c);
    };
  });
}

function sheet(title, options) {
  return new Promise((resolve) => {
    const el = document.getElementById("sheet");
    el.innerHTML = `<div class="shade"></div><div class="panel">
      <div class="card">${title ? `<div class="head2">${esc(title)}</div>` : ""}
        ${options.map((o, k) => `<button class="row" data-k="${k}" style="${o.danger ? "color:var(--red);font-weight:600" : ""}">${esc(o.label)}</button>`).join("")}</div>
      <div class="card"><button class="row cancel">${t("Cancelar")}</button></div></div>`;
    el.hidden = false;
    const close = (v) => { el.hidden = true; el.innerHTML = ""; resolve(v); };
    el.querySelector(".shade").onclick = () => close(null);
    el.querySelector(".cancel").onclick = () => close(null);
    el.querySelectorAll("[data-k]").forEach((b) => (b.onclick = () => close(options[+b.dataset.k].value)));
  });
}

function ask(title, value, okLabel) {
  return new Promise((resolve) => {
    const el = document.getElementById("sheet");
    el.innerHTML = `<div class="shade"></div><div class="panel">
      <div class="card"><div class="head2">${esc(title)}</div>
        <div style="padding:0 16px 16px"><input id="ask" value="${esc(value)}" placeholder="${t("Nombre de la colección")}" maxlength="60"></div>
        <button class="row" id="ok" style="font-weight:600">${esc(okLabel)}</button></div>
      <div class="card"><button class="row cancel">${t("Cancelar")}</button></div></div>`;
    el.hidden = false;
    const input = el.querySelector("#ask");
    setTimeout(() => input.focus(), 50);
    const close = (v) => { el.hidden = true; el.innerHTML = ""; resolve(v); };
    el.querySelector(".shade").onclick = () => close(null);
    el.querySelector(".cancel").onclick = () => close(null);
    el.querySelector("#ok").onclick = () => close(input.value.trim() || null);
    input.onkeydown = (e) => { if (e.key === "Enter") close(input.value.trim() || null); };
  });
}

// Al cerrar el selector de fotos, el celular tarda en entregar los archivos
// (los convierte o los baja de iCloud). Mientras, se avisa en la página.
window.addEventListener("focus", () => {
  if (S.picking === "open") {
    S.picking = "wait";
    if (S.tab === "upload") render();
    setTimeout(() => { if (S.picking === "wait") { S.picking = null; if (S.tab === "upload") render(); } }, 90000);
  }
});
window.addEventListener("resize", () => document.querySelectorAll(".seg").forEach((seg) => placePill(seg, true)));
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && S.info) refresh().then(() => { if (!S.selecting) render(); }).catch(() => {});
});
start();
