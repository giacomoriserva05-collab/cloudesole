// background.js — accende e spegne il pilota automatico, gestisce la
// scorciatoia da tastiera e risponde alle richieste di compilazione.

import { runFill } from './runner.js';

const SCRIPT_ID = 'autopilot';
const FILES = ['cartcore.js', 'shopify.js', 'autopilot.js'];

async function badge(tabId, text, color) {
  try {
    const target = tabId ? { tabId } : {};
    await chrome.action.setBadgeBackgroundColor(Object.assign({ color }, target));
    await chrome.action.setBadgeText(Object.assign({ text }, target));
    if (tabId) setTimeout(() => chrome.action.setBadgeText({ tabId, text: '' }), 4000);
  } catch (e) { /* la scheda può essere già chiusa */ }
}

async function registered() {
  try {
    return await chrome.scripting.getRegisteredContentScripts({ ids: [SCRIPT_ID] });
  } catch (e) { return []; }
}

/** Fa entrare il pilota nelle schede già aperte, così accendere l'estensione
 *  basta e non serve ricaricare le pagine a mano. */
async function injectIntoOpenTabs() {
  let tabs = [];
  try { tabs = await chrome.tabs.query({}); } catch (e) { return; }
  for (const t of tabs) {
    if (!t.id || !t.url || !/^https?:/i.test(t.url)) continue;
    try {
      await chrome.scripting.executeScript({ target: { tabId: t.id }, files: FILES });
    } catch (e) { /* scheda non accessibile: pazienza */ }
  }
}

// Le chiamate arrivano da più parti insieme (interruttore, permesso concesso,
// avvio di Chrome). Senza una coda, una che parte da uno stato vecchio può
// cancellare la registrazione appena scritta da un'altra: era il motivo per
// cui il pilota andava riattivato a mano.
let coda = Promise.resolve();
function inCoda(fn) {
  const next = coda.then(fn, fn);
  coda = next.catch(() => {});
  return next;
}

async function doSync() {
  const { armed } = await chrome.storage.local.get('armed');
  const granted = await chrome.permissions.contains({ origins: ['<all_urls>'] });
  const wanted = !!armed && granted;
  const now = await registered();
  const attuale = now.length ? (now[0].js || []).join(',') : '';
  const giusto = wanted && attuale === FILES.join(',');

  if (!giusto) {
    // La registrazione sopravvive ai riavvii: una versione vecchia resterebbe
    // appesa dopo un aggiornamento dei file, quindi si riscrive da zero.
    if (now.length) {
      try { await chrome.scripting.unregisterContentScripts({ ids: [SCRIPT_ID] }); } catch (e) { /* già sparita */ }
    }
    if (wanted) {
      await chrome.scripting.registerContentScripts([{
        id: SCRIPT_ID,
        js: FILES,
        matches: ['<all_urls>'],
        runAt: 'document_idle',
        allFrames: false
      }]);
      await injectIntoOpenTabs();
    }
  }

  await chrome.action.setBadgeText({ text: wanted ? 'ON' : '' });
  await chrome.action.setBadgeBackgroundColor({ color: '#16a34a' });
  return wanted;
}

export function syncAutopilot() {
  return inCoda(doSync);
}

/** Stato reale, non quello che crede il popup. Si ripara da solo: se risulta
 *  acceso e autorizzato ma lo script non c'è, lo rimette. */
async function status() {
  const { armed } = await chrome.storage.local.get('armed');
  const granted = await chrome.permissions.contains({ origins: ['<all_urls>'] });
  let now = await registered();

  if (!!armed && granted && !now.length) {
    await syncAutopilot();
    now = await registered();
  }
  return {
    armed: !!armed,
    granted,
    registered: now.length > 0,
    files: now.length ? now[0].js : []
  };
}

chrome.runtime.onStartup.addListener(() => { syncAutopilot(); });
chrome.runtime.onInstalled.addListener(() => { syncAutopilot(); });

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.armed) syncAutopilot();
});

// Il permesso può arrivare dopo l'attivazione, se il popup si chiude
// mentre Chrome mostra la richiesta.
chrome.permissions.onAdded.addListener(() => { syncAutopilot(); });
chrome.permissions.onRemoved.addListener(() => { syncAutopilot(); });

chrome.runtime.onMessage.addListener((msg, sender, respond) => {
  if (!msg) return;

  if (msg.type === 'STATUS') {
    status().then(respond);
    return true;
  }
  if (msg.type === 'SYNC') {
    syncAutopilot().then(() => status()).then(respond);
    return true;
  }
  // Richiesta di compilazione che arriva dal pilota automatico.
  if (msg.type !== 'FILL') return;
  if (!sender.tab || !sender.tab.id) { respond({ error: 'Scheda sconosciuta.' }); return; }
  runFill(sender.tab, 'fill').then((res) => {
    if (res.error) respond({ error: res.error });
    else respond({ filled: res.filled.filter((f) => f.ok !== false).length, skipped: res.skipped });
  }).catch((e) => respond({ error: String((e && e.message) || e) }));
  return true; // risposta asincrona
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== 'fill-now') return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) return;

  const res = await runFill(tab, 'fill');
  if (res.error) {
    await badge(tab.id, '!', '#dc2626');
    return;
  }
  const ok = res.filled.filter((f) => f.ok !== false).length;
  await badge(tab.id, String(ok), ok ? '#16a34a' : '#d97706');
});
