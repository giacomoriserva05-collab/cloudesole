// popup.js — interfaccia: profili, carta, regole per sito, opzioni.

import {
  loadState, activeOf, newProfile, saveProfiles, saveSettings, saveSites,
  saveCard, saveAllCards, clearCard, runFill, setArmed, emptySite, EMPTY_CARD
} from './runner.js';

const FIELDS = [
  { k: 'firstName', l: 'Nome' },
  { k: 'lastName', l: 'Cognome' },
  { k: 'email', l: 'Email', t: 'email', w: 2 },
  { k: 'phone', l: 'Telefono', t: 'tel', w: 2 },
  { k: 'address1', l: 'Indirizzo (via)', w: 2 },
  { k: 'houseNumber', l: 'Civico' },
  { k: 'address2', l: 'Interno / scala' },
  { k: 'postalCode', l: 'CAP' },
  { k: 'city', l: 'Città' },
  { k: 'province', l: 'Provincia (sigla)' },
  { k: 'country', l: 'Paese', t: 'country' },
  { k: 'company', l: 'Azienda (facoltativo)', w: 2 },
  { k: 'fiscalCode', l: 'Codice fiscale (facoltativo)', w: 2 },
  { k: 'birthDate', l: 'Data di nascita', p: 'gg/mm/aaaa' },
  // Non è un dato dell'indirizzo: compare solo nel blocco di spedizione.
  { k: 'size', l: 'Taglia da aggiungere al carrello', p: '42, 42.5, M', ship: true }
];

const COUNTRIES = [
  ['IT', 'Italia'], ['FR', 'Francia'], ['DE', 'Germania'], ['ES', 'Spagna'],
  ['GB', 'Regno Unito'], ['US', 'Stati Uniti'], ['CH', 'Svizzera'],
  ['AT', 'Austria'], ['BE', 'Belgio'], ['NL', 'Paesi Bassi'],
  ['PT', 'Portogallo'], ['IE', 'Irlanda'], ['SE', 'Svezia'],
  ['DK', 'Danimarca'], ['PL', 'Polonia'], ['GR', 'Grecia']
];

const KEY_LABELS = {
  firstName: 'Nome', lastName: 'Cognome', fullName: 'Nome e cognome',
  email: 'Email', emailConfirm: 'Conferma email', phone: 'Telefono',
  company: 'Azienda', address1: 'Indirizzo', address2: 'Interno / scala',
  houseNumber: 'Civico', postalCode: 'CAP', city: 'Città',
  province: 'Provincia', country: 'Paese', fiscalCode: 'Codice fiscale',
  birthDate: 'Data di nascita', cardNumber: 'Numero carta',
  cardName: 'Titolare carta', cardExp: 'Scadenza', cardExpMonth: 'Mese scadenza',
  cardExpYear: 'Anno scadenza', cardCvc: 'CVC'
};

const CARD_INPUTS = {
  number: '#card-number', name: '#card-name', expMonth: '#card-exp-month',
  expYear: '#card-exp-year', cvc: '#card-cvc'
};

const $ = (sel) => document.querySelector(sel);
let state = null;
let tab = null;
let host = '';

const current = () => activeOf(state);
const cardOf = (id) => Object.assign({}, EMPTY_CARD, state.cards[id] || {});

// ------------------------------------------------------------- costruzione

function buildProfileForm(container, values, isBilling) {
  container.innerHTML = '';
  for (const f of FIELDS) {
    if (isBilling && f.ship) continue;
    const label = document.createElement('label');
    label.className = 'field' + (f.w === 2 ? ' span2' : '');

    const span = document.createElement('span');
    span.textContent = f.l;
    label.appendChild(span);

    let input;
    if (f.t === 'country') {
      input = document.createElement('select');
      for (const [code, name] of COUNTRIES) {
        const o = document.createElement('option');
        o.value = code;
        o.textContent = name;
        input.appendChild(o);
      }
    } else {
      input = document.createElement('input');
      input.type = f.t || 'text';
      if (f.p) input.placeholder = f.p;
    }
    input.dataset.key = f.k;
    input.value = values[f.k] || '';
    label.appendChild(input);
    container.appendChild(label);
  }
}

function readProfileForm(container, base) {
  const out = Object.assign({}, base);
  for (const el of container.querySelectorAll('[data-key]')) out[el.dataset.key] = el.value.trim();
  return out;
}

function buildKeySelect() {
  const sel = $('#ov-key');
  for (const k of Object.keys(KEY_LABELS)) {
    const o = document.createElement('option');
    o.value = k;
    o.textContent = KEY_LABELS[k];
    sel.appendChild(o);
  }
}

// ----------------------------------------------------------------- profili

function renderProfileSelect() {
  const sel = $('#profile-select');
  sel.innerHTML = '';
  for (const p of state.profiles) {
    const o = document.createElement('option');
    o.value = p.id;
    o.textContent = p.name;
    sel.appendChild(o);
  }
  sel.value = state.activeId;
  $('#profile-del').disabled = state.profiles.length < 2;
}

/** Riversa nei campi il profilo attivo (dopo un cambio, una copia, un nuovo). */
function showActiveProfile() {
  const p = current();
  $('#profile-name').value = p.name;
  buildProfileForm($('#form-shipping'), p.shipping, false);
  buildProfileForm($('#form-billing'), p.billing, true);
  $('#billing-enabled').checked = !!p.billing.enabled;
  $('#billing-wrap').classList.toggle('hidden', !p.billing.enabled);

  const card = cardOf(p.id);
  for (const [k, sel] of Object.entries(CARD_INPUTS)) $(sel).value = card[k] || '';
  renderProfileSelect();
}

async function switchProfile(id) {
  await persist();              // il profilo che lascio va salvato com'è ora
  state.activeId = id;
  await saveProfiles(state.profiles, state.activeId);
  showActiveProfile();
  setStatus('Profilo attivo: ' + current().name + '.', 'ok');
}

async function addProfile(copyCurrent) {
  await persist();
  const src = current();
  const p = newProfile(copyCurrent ? src.name + ' (copia)' : 'Nuovo profilo');
  if (copyCurrent) {
    p.shipping = Object.assign({}, src.shipping);
    p.billing = Object.assign({}, src.billing);
    state.cards[p.id] = cardOf(src.id);
    await saveCard(p.id, state.cards[p.id], state.settings.rememberCard);
  }
  state.profiles.push(p);
  state.activeId = p.id;
  await saveProfiles(state.profiles, state.activeId);
  showActiveProfile();
  $('#profile-name').focus();
  $('#profile-name').select();
  setStatus(copyCurrent ? 'Profilo duplicato: dagli un nome.' : 'Profilo creato: dagli un nome.', 'ok');
}

// Eliminazione in due tempi: il primo clic chiede conferma, il secondo esegue.
let confirmTimer = null;
async function deleteProfile(btn) {
  if (state.profiles.length < 2) return;
  if (btn.dataset.armed !== '1') {
    btn.dataset.armed = '1';
    btn.textContent = 'Confermi?';
    btn.classList.add('is-confirming');
    clearTimeout(confirmTimer);
    confirmTimer = setTimeout(() => resetDeleteButton(btn), 4000);
    return;
  }
  resetDeleteButton(btn);
  const gone = current();
  await clearCard(gone.id);
  delete state.cards[gone.id];
  state.profiles = state.profiles.filter((p) => p.id !== gone.id);
  state.activeId = state.profiles[0].id;
  await saveProfiles(state.profiles, state.activeId);
  showActiveProfile();
  setStatus('Profilo "' + gone.name + '" eliminato.', 'ok');
}

function resetDeleteButton(btn) {
  clearTimeout(confirmTimer);
  btn.dataset.armed = '0';
  btn.textContent = 'Elimina';
  btn.classList.remove('is-confirming');
}

// -------------------------------------------------------------- salvataggi

let saveTimer = null;
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(persist, 350);
}

async function persist() {
  const p = current();
  p.name = $('#profile-name').value.trim() || p.name;
  p.shipping = readProfileForm($('#form-shipping'), p.shipping);
  p.billing = readProfileForm($('#form-billing'), p.billing);
  p.billing.enabled = $('#billing-enabled').checked;
  await saveProfiles(state.profiles, state.activeId);

  const opt = $('#profile-select').querySelector('option[value="' + p.id + '"]');
  if (opt && opt.textContent !== p.name) opt.textContent = p.name;

  state.settings.fillCard = $('#fill-card').checked;
  state.settings.rememberCard = $('#remember-card').checked;
  state.settings.overwrite = $('#opt-overwrite').checked;
  state.settings.splitHouseNumber = $('#opt-split').checked;
  state.settings.highlight = $('#opt-highlight').checked;
  state.settings.autoFillCheckout = $('#opt-autofill').checked;
  state.settings.shopifyFast = $('#opt-shopify').checked;
  state.settings.afterAdd = $('#opt-after').value;
  const wait = parseInt($('#opt-wait').value, 10);
  state.settings.cartWait = Number.isFinite(wait) ? Math.min(15000, Math.max(300, wait)) : 1500;
  await saveSettings(state.settings);

  if (host) {
    const add = $('#site-add').value.trim();
    const cart = $('#site-cart').value.trim();
    const checkout = $('#site-checkout').value.trim();
    if (add || cart || checkout || state.sites[host]) {
      const cfg = siteCfg();
      cfg.addToCart = add;
      cfg.cartUrl = cart;
      cfg.checkoutUrl = checkout;
      pruneSites();
      await saveSites(state.sites);
    }
  }

  const card = {};
  for (const [k, sel] of Object.entries(CARD_INPUTS)) card[k] = $(sel).value;
  if (Object.values(card).some((v) => String(v).trim())) {
    state.cards[p.id] = card;
    await saveCard(p.id, card, state.settings.rememberCard);
  }
}

// -------------------------------------------------------------- interfaccia

function setStatus(text, kind) {
  const el = $('#status');
  el.textContent = text;
  el.className = 'status' + (kind ? ' ' + kind : '');
}

function siteCfg() {
  if (!host) return emptySite();
  if (!state.sites[host]) state.sites[host] = emptySite();
  return state.sites[host];
}

/** Toglie dalla memoria gli host rimasti senza nessuna impostazione. */
function pruneSites() {
  for (const h of Object.keys(state.sites)) {
    const s = state.sites[h];
    if (!s.rules.length && !s.addToCart && !s.cartUrl) delete state.sites[h];
  }
}

function renderOverrides() {
  const ul = $('#ov-list');
  ul.innerHTML = '';
  const rules = (state.sites[host] ? state.sites[host].rules : []);
  if (!rules.length) {
    const li = document.createElement('li');
    li.textContent = 'Nessuna regola per ' + (host || 'questo sito') + '.';
    ul.appendChild(li);
    return;
  }
  rules.forEach((r, i) => {
    const li = document.createElement('li');
    const left = document.createElement('span');
    left.innerHTML = '<span class="tagkey"></span> <code></code>';
    left.querySelector('.tagkey').textContent = KEY_LABELS[r.key] || r.key;
    left.querySelector('code').textContent = r.selector;
    const del = document.createElement('button');
    del.className = 'del';
    del.textContent = '×';
    del.title = 'Rimuovi';
    del.addEventListener('click', async () => {
      state.sites[host].rules.splice(i, 1);
      pruneSites();
      await saveSites(state.sites);
      renderOverrides();
    });
    li.append(left, del);
    ul.appendChild(li);
  });
}

function renderReport(items, listEl) {
  listEl.innerHTML = '';
  if (!items.length) {
    const li = document.createElement('li');
    li.textContent = 'Nessun campo riconosciuto.';
    listEl.appendChild(li);
    return;
  }
  for (const it of items) {
    const li = document.createElement('li');
    const left = document.createElement('span');
    left.innerHTML = '<span class="tagkey"></span> <code></code>';
    left.querySelector('.tagkey').textContent = KEY_LABELS[it.key] || it.key;
    left.querySelector('code').textContent = it.value;
    const right = document.createElement('code');
    right.textContent = it.section === 'billing' ? 'fatturazione' : '';
    li.append(left, right);
    listEl.appendChild(li);
  }
}

// ------------------------------------------------------- diagnostica

function probeRow(ul, etichetta, valore, tono) {
  const li = document.createElement('li');
  const left = document.createElement('span');
  left.className = 'tagkey';
  left.textContent = etichetta;
  const right = document.createElement('code');
  right.textContent = valore;
  if (tono) right.style.color = tono === 'ok' ? 'var(--accent-ink)' : 'var(--danger)';
  li.append(left, right);
  ul.appendChild(li);
}

/** Mostra cosa vedrebbe il pilota su questa pagina, senza toccare niente. */
async function probeAutopilot() {
  const ul = $('#probe-list');
  ul.innerHTML = '';
  const cfg = {
    addToCart: $('#site-add').value.trim(),
    cartUrl: $('#site-cart').value.trim(),
    checkoutUrl: $('#site-checkout').value.trim()
  };
  let res;
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['cartcore.js'] });
    const [out] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (c) => globalThis.CartCore.probe(c),
      args: [cfg]
    });
    res = out && out.result;
  } catch (e) {
    setStatus('Non riesco a leggere questa pagina: ' + (e.message || e), 'err');
    return;
  }
  if (!res || !Array.isArray(res.pulsanti)) {
    setStatus('Nessuna risposta dalla pagina.', 'err');
    return;
  }

  const attivi = res.pulsanti.filter((b) => b.attivo);
  probeRow(ul, 'Pulsante', res.pulsanti.length
    ? res.pulsanti.map((b) => '"' + b.testo + '"' + (b.attivo ? '' : ' (spento)')).join(', ')
    : 'nessuno trovato', res.pulsanti.length ? 'ok' : 'err');
  probeRow(ul, 'Taglie', res.taglie
    ? res.taglie.voci.join(', ')
    : 'nessun selettore in pagina', res.taglie ? 'ok' : '');
  probeRow(ul, 'Carrello', res.carrello, 'ok');
  probeRow(ul, 'Checkout', res.checkout || '—', 'ok');
  probeRow(ul, 'Pagina', res.carrelloOChckout ? 'carrello o checkout'
    : res.indirizzoProdotto ? 'scheda prodotto' : 'indirizzo non da prodotto');

  const taglia = current().shipping.size;
  if (res.taglie && taglia) {
    const libere = res.taglie.voci.filter((v) => !/esaurita/.test(v));
    probeRow(ul, 'La tua taglia', taglia, libere.length ? '' : 'err');
  }
  setStatus(res.pulsanti.length && attivi.length
    ? 'Qui il pilota saprebbe muoversi.'
    : 'Qui manca un pulsante attivo: serve un selettore su misura.',
  res.pulsanti.length && attivi.length ? 'ok' : 'err');
}

// ------------------------------------------------------------- captcha

let captchaTimer = null;

/** Gira dentro la pagina, nel mondo MAIN: `grecaptcha` non è visibile dal
 *  mondo isolato in cui girano gli script dell'estensione. */
async function inPagina(func, args) {
  await chrome.scripting.executeScript({
    target: { tabId: tab.id }, files: ['captcha.js'], world: 'MAIN'
  });
  const [out] = await chrome.scripting.executeScript({
    target: { tabId: tab.id }, world: 'MAIN', func, args: args || []
  });
  return out && out.result;
}

/** Intestazione di un fornitore: si mostra solo quando in pagina ce n'è più
 *  d'uno, altrimenti è rumore. */
function capoRow(ul, testo) {
  const li = document.createElement('li');
  li.className = 'capo';
  li.textContent = testo;
  ul.appendChild(li);
}

function renderFornitore(ul, f, conCapo) {
  if (conCapo) capoRow(ul, f.nome);
  else probeRow(ul, 'Libreria', f.nome, f.gestito ? 'ok' : 'err');

  if (!f.gestito) {
    probeRow(ul, 'Stato', f.versione, 'err');
    probeRow(ul, 'Rinnovo', 'non da qui: API chiusa, va rifatto a mano');
    return;
  }

  probeRow(ul, 'Versione', f.versione, 'ok');
  if (f.sitekey) probeRow(ul, 'Site key', f.sitekey.slice(0, 20) + (f.sitekey.length > 20 ? '…' : ''));
  if (f.widget) {
    probeRow(ul, 'Widget', f.widget + (f.montato ? ' (montato)' : ' (non ancora disegnato)'),
      f.montato ? 'ok' : '');
  }

  const stato = f.valido ? 'valido' : (f.scaduto ? 'scaduto — va rifatto' : 'non ancora risolto');
  probeRow(ul, 'Token', stato, f.valido ? 'ok' : (f.scaduto ? 'err' : ''));
  if (f.valido) probeRow(ul, 'Scade fra', f.restano + ' s di ' + f.ttl, f.restano < 20 ? 'err' : 'ok');
  if (f.tokenLungo) probeRow(ul, 'Lunghezza', f.tokenLungo + ' caratteri');
  probeRow(ul, 'Giro', f.emissioni + ' emessi, ' + f.scadenze + ' scaduti, ' + f.rinnovi + ' rifatti');
}

function renderCaptcha(res) {
  const ul = $('#captcha-list');
  ul.innerHTML = '';
  const azioni = $('#captcha-actions');
  const pickWrap = $('#captcha-pick-wrap');
  const pick = $('#captcha-pick');

  if (!res || !res.presente || !res.fornitori.length) {
    probeRow(ul, 'Captcha', 'nessuno in questa pagina');
    azioni.classList.add('hidden');
    fermaOrologioCaptcha();
    return;
  }

  const molti = res.fornitori.length > 1;
  for (const f of res.fornitori) renderFornitore(ul, f, molti);

  const rifacibili = res.fornitori.filter((f) => f.gestito);
  if (!rifacibili.length) {
    azioni.classList.add('hidden');
    fermaOrologioCaptcha();
    return;
  }

  // La tendina serve solo quando c'è davvero una scelta da fare.
  if (rifacibili.length > 1) {
    const prima = pick.value;
    pick.innerHTML = '';
    for (const f of rifacibili) {
      const o = document.createElement('option');
      o.value = f.id;
      o.textContent = f.nome;
      pick.appendChild(o);
    }
    if (rifacibili.some((f) => f.id === prima)) pick.value = prima;
    pickWrap.classList.remove('hidden');
  } else {
    pick.innerHTML = '';
    const o = document.createElement('option');
    o.value = rifacibili[0].id;
    o.textContent = rifacibili[0].nome;
    pick.appendChild(o);
    pickWrap.classList.add('hidden');
  }
  azioni.classList.remove('hidden');
}

function riassunto(res) {
  if (!res || !res.presente) return { testo: 'Nessun captcha qui.', tono: 'ok' };
  const gestiti = res.fornitori.filter((f) => f.gestito);
  if (!gestiti.length) {
    const nomi = res.fornitori.map((f) => f.nome).join(', ');
    return { testo: nomi + ': lo vedo ma non posso rifarlo da qui.', tono: 'err' };
  }
  const f = gestiti.find((x) => x.scaduto) || gestiti.find((x) => !x.valido) || gestiti[0];
  if (f.scaduto) return { testo: f.nome + ': token scaduto, va rifatta la verifica.', tono: 'err' };
  if (!f.valido) return { testo: f.nome + ' ' + f.versione + ': verifica non ancora fatta.', tono: 'err' };
  return { testo: f.nome + ' ' + f.versione + ', token valido per altri ' + f.restano + ' s.', tono: 'ok' };
}

async function probeCaptcha(silenzioso) {
  let res;
  try {
    res = await inPagina(() => globalThis.CaptchaCore.probe());
  } catch (e) {
    fermaOrologioCaptcha();
    if (!silenzioso) setStatus('Non riesco a leggere questa pagina: ' + (e.message || e), 'err');
    return null;
  }
  renderCaptcha(res);
  if (!silenzioso) {
    const r = riassunto(res);
    setStatus(r.testo, r.tono);
  }
  return res;
}

async function renewCaptcha() {
  const id = $('#captcha-pick').value;
  if (!id) return;
  let res;
  try {
    res = await inPagina((quale) => globalThis.CaptchaCore.rinnova(quale), [id]);
  } catch (e) {
    setStatus('Rinnovo fallito: ' + (e.message || e), 'err');
    return;
  }
  if (!res || !res.ok) {
    setStatus('Non si può rifare: ' + ((res && res.motivo) || 'motivo sconosciuto'), 'err');
    return;
  }
  // Dove il token arriva dalla rete serve un attimo prima di rileggerlo.
  setTimeout(() => probeCaptcha(true), res.sfida ? 300 : 1500);
  setStatus(res.nome + ': ' + res.azione, res.sfida ? '' : 'ok');
}

function fermaOrologioCaptcha() {
  clearInterval(captchaTimer);
  captchaTimer = null;
  const c = $('#captcha-auto');
  if (c) c.checked = false;
}

// --------------------------------------------- stato reale del pilota

/** Non quello che crede il popup: quello che il service worker ha davvero
 *  registrato. È qui che si vede se una vecchia registrazione è rimasta
 *  appesa dopo un aggiornamento dei file. */
async function renderEngineState() {
  const el = $('#engine-state');
  let s = null;
  try { s = await chrome.runtime.sendMessage({ type: 'STATUS' }); } catch (e) { s = null; }
  if (!s) {
    el.textContent = "Non riesco a parlare con il motore: ricarica l'estensione da chrome://extensions.";
    return s;
  }
  if (!s.armed) el.textContent = 'Pilota spento: nessuno script gira sulle pagine.';
  else if (!s.granted) el.textContent = 'Acceso ma senza accesso ai siti: non può agire.';
  else if (!s.registered) el.textContent = 'Acceso ma lo script non risulta installato: premi qui sotto.';
  else el.textContent = 'Pilota installato e funzionante (' + (s.files || []).join(' + ') + ').';
  return s;
}

// ------------------------------------------------------ interruttore

function renderPower() {
  const on = !!state.armed;
  const btn = $('#power');
  btn.textContent = on ? 'Attivo — premi per fermare' : "Attiva l'estensione";
  btn.classList.toggle('is-on', on);
  document.querySelector('.dot').classList.toggle('off', !on);
  $('#power-hint').textContent = on
    ? 'Aggiunge al carrello da solo'
    : 'Nessuna azione automatica';
}

async function togglePower() {
  if (state.armed) {
    state.armed = false;
    await setArmed(false);
    renderPower();
    await renderEngineState();
    setStatus('Estensione ferma: non tocca più nessuna pagina.', 'ok');
    return;
  }
  // Per agire da sola su una pagina che non hai aperto col popup serve
  // l'accesso ai siti: senza, resta spenta.
  state.armed = true;
  await setArmed(true);
  renderPower();
  const granted = await chrome.permissions.contains({ origins: ['<all_urls>'] });
  if (!granted) {
    const ok = await chrome.permissions.request({ origins: ['<all_urls>'] });
    if (!ok) {
      state.armed = false;
      await setArmed(false);
      renderPower();
      setStatus('Senza accesso ai siti non può agire da sola. Attivazione annullata.', 'err');
      return;
    }
    $('#grant-state').textContent = 'Accesso agli iframe: attivo.';
    $('#grant').disabled = true;
  }
  // Si aspetta che il service worker abbia davvero registrato lo script,
  // altrimenti chiudere il popup subito dopo lascerebbe il pilota a metà.
  try { await chrome.runtime.sendMessage({ type: 'SYNC' }); } catch (e) { /* mostrato sotto */ }
  const s = await renderEngineState();
  setStatus(s && s.registered
    ? 'Attiva, anche sulle schede già aperte. Apri la scheda prodotto.'
    : 'Accesa, ma lo script non risulta installato: guarda la scheda Opzioni.',
  s && s.registered ? 'ok' : 'err');
}

async function doRun(mode) {
  await persist();
  setStatus(mode === 'preview' ? 'Analisi in corso…' : 'Compilazione in corso…');
  const res = await runFill(tab, mode);
  if (res.error) { setStatus(res.error, 'err'); return; }

  if (mode === 'preview') {
    renderReport(res.filled, $('#preview-list'));
    setStatus(res.filled.length + ' campi riconosciuti su ' + res.scanned + ' esaminati.', 'ok');
    return;
  }
  const ok = res.filled.filter((f) => f.ok !== false);
  if (!ok.length) {
    setStatus('Nessun campo compilato su ' + res.scanned + ' esaminati. Prova "Analizza la pagina" nella scheda Sito.', 'err');
    return;
  }
  const n = ok.length;
  setStatus(n + (n === 1 ? ' campo compilato' : ' campi compilati') +
            ' con "' + res.profile + '". Controlla e conferma tu l\'ordine.', 'ok');
}

// ------------------------------------------------------------------- avvio

async function init() {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try { host = new URL(tab.url).hostname; } catch (e) { host = ''; }
  $('#host').textContent = host || 'scheda non compatibile';

  state = await loadState();
  buildKeySelect();
  showActiveProfile();

  $('#fill-card').checked = !!state.settings.fillCard;
  $('#remember-card').checked = !!state.settings.rememberCard;
  $('#opt-overwrite').checked = !!state.settings.overwrite;
  $('#opt-split').checked = !!state.settings.splitHouseNumber;
  $('#opt-highlight').checked = state.settings.highlight !== false;
  $('#opt-autofill').checked = state.settings.autoFillCheckout !== false;
  $('#opt-shopify').checked = state.settings.shopifyFast !== false;
  $('#opt-wait').value = state.settings.cartWait || 1500;
  $('#opt-after').value = state.settings.afterAdd === 'cart' ? 'cart' : 'checkout';
  $('#card-wrap').classList.toggle('hidden', !state.settings.fillCard);

  const cfg = state.sites[host] || emptySite();
  $('#site-add').value = cfg.addToCart || '';
  $('#site-cart').value = cfg.cartUrl || '';
  $('#site-checkout').value = cfg.checkoutUrl || '';

  renderPower();
  renderOverrides();

  // Schede
  for (const t of document.querySelectorAll('.tab')) {
    t.addEventListener('click', () => {
      for (const x of document.querySelectorAll('.tab')) x.classList.toggle('is-active', x === t);
      for (const p of document.querySelectorAll('.panel')) {
        p.classList.toggle('is-active', p.dataset.panel === t.dataset.tab);
      }
    });
  }

  document.body.addEventListener('input', scheduleSave);
  document.body.addEventListener('change', scheduleSave);

  // Profili
  $('#profile-select').addEventListener('change', (e) => switchProfile(e.target.value));
  $('#profile-new').addEventListener('click', () => addProfile(false));
  $('#profile-dup').addEventListener('click', () => addProfile(true));
  $('#profile-del').addEventListener('click', (e) => deleteProfile(e.currentTarget));

  $('#billing-enabled').addEventListener('change', (e) => {
    $('#billing-wrap').classList.toggle('hidden', !e.target.checked);
  });
  $('#fill-card').addEventListener('change', (e) => {
    $('#card-wrap').classList.toggle('hidden', !e.target.checked);
  });
  $('#remember-card').addEventListener('change', async (e) => {
    await saveAllCards(state.cards, e.target.checked);
  });

  $('#clear-card').addEventListener('click', async () => {
    const p = current();
    await clearCard(p.id);
    delete state.cards[p.id];
    for (const sel of Object.values(CARD_INPUTS)) $(sel).value = '';
    setStatus('Carta del profilo "' + p.name + '" cancellata.', 'ok');
  });

  $('#ov-add').addEventListener('click', async () => {
    const selector = $('#ov-selector').value.trim();
    if (!selector || !host) return;
    try { document.querySelector(selector); } catch (e) {
      setStatus('Selettore CSS non valido.', 'err');
      return;
    }
    siteCfg().rules.push({ selector, key: $('#ov-key').value });
    await saveSites(state.sites);
    $('#ov-selector').value = '';
    renderOverrides();
  });

  $('#preview').addEventListener('click', () => doRun('preview'));
  $('#fill').addEventListener('click', () => doRun('fill'));
  $('#power').addEventListener('click', togglePower);
  $('#probe').addEventListener('click', probeAutopilot);
  $('#captcha').addEventListener('click', () => probeCaptcha(false));
  $('#captcha-renew').addEventListener('click', renewCaptcha);
  $('#captcha-auto').addEventListener('change', (e) => {
    if (!e.target.checked) { clearInterval(captchaTimer); captchaTimer = null; return; }
    // Il conto alla rovescia lo tiene la pagina; qui si ridisegna e basta.
    captchaTimer = setInterval(() => probeCaptcha(true), 1000);
  });
  $('#resync').addEventListener('click', async () => {
    try { await chrome.runtime.sendMessage({ type: 'SYNC' }); } catch (e) { /* mostrato sotto */ }
    const s = await renderEngineState();
    setStatus(s && s.registered ? 'Pilota reinstallato, schede aperte comprese.'
      : 'Il pilota non risulta installato: controlla interruttore e permessi.',
    s && s.registered ? 'ok' : 'err');
  });
  renderEngineState();

  const granted = await chrome.permissions.contains({ origins: ['<all_urls>'] });
  $('#grant-state').textContent = granted ? 'Accesso agli iframe: attivo.' : 'Accesso agli iframe: non concesso.';
  $('#grant').disabled = granted;
  $('#grant').addEventListener('click', async () => {
    const ok = await chrome.permissions.request({ origins: ['<all_urls>'] });
    $('#grant-state').textContent = ok ? 'Accesso agli iframe: attivo.' : 'Permesso rifiutato.';
    $('#grant').disabled = ok;
  });
}

init();
