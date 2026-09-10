// runner.js — stato salvato e avvio della compilazione.
// Usato sia dal popup sia dal service worker (scorciatoia da tastiera).

import { autofillPage } from './filler.js';

export const EMPTY_PROFILE = {
  firstName: '', lastName: '', email: '', phone: '', company: '',
  address1: '', houseNumber: '', address2: '', postalCode: '', city: '',
  province: '', country: 'IT', fiscalCode: '', birthDate: '',
  size: '' // taglia da scegliere sulla scheda prodotto
};

export const EMPTY_CARD = { number: '', name: '', expMonth: '', expYear: '', cvc: '' };

export const DEFAULT_SETTINGS = {
  fillCard: false,        // compila anche i campi carta
  rememberCard: false,    // salva la carta su disco invece che in sessione
  overwrite: false,       // sovrascrive i campi già compilati
  splitHouseNumber: false,// il sito ha un campo civico separato
  highlight: true,        // bordo colorato sui campi toccati
  autoFillCheckout: true, // a estensione attiva, compila da sé arrivato al checkout
  cartWait: 1500,         // ms di attesa fra il clic e l'apertura della pagina
  afterAdd: 'checkout',   // dopo l'aggiunta apre 'checkout' oppure 'cart'
  shopifyFast: true       // su Shopify va per richieste dirette, senza DOM
};

const CARD_FIELDS = Object.keys(EMPTY_CARD);

export function newId() {
  return (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random())).slice(0, 18);
}

export function newProfile(name) {
  return {
    id: newId(),
    name: name || 'Nuovo profilo',
    shipping: Object.assign({}, EMPTY_PROFILE),
    billing: Object.assign({ enabled: false }, EMPTY_PROFILE)
  };
}

function normalizeProfile(p) {
  return {
    id: p.id || newId(),
    name: p.name || 'Senza nome',
    shipping: Object.assign({}, EMPTY_PROFILE, p.shipping || {}),
    billing: Object.assign({ enabled: false }, EMPTY_PROFILE, p.billing || {})
  };
}

/** Legge tutto lo stato. Se trova il vecchio formato a profilo singolo
 *  lo converte in un profilo chiamato "Principale" e ripulisce le chiavi. */
export async function loadState() {
  const local = await chrome.storage.local.get([
    'profiles', 'activeId', 'settings', 'sites', 'cards', 'armed',
    'shipping', 'billing', 'card' // formato precedente
  ]);
  const settings = Object.assign({}, DEFAULT_SETTINGS, local.settings || {});

  let profiles = Array.isArray(local.profiles) ? local.profiles.map(normalizeProfile) : [];
  let cards = local.cards || {};
  let migrated = false;

  if (!profiles.length) {
    const p = normalizeProfile({
      name: 'Principale',
      shipping: local.shipping || {},
      billing: local.billing || {}
    });
    profiles = [p];
    if (local.card) cards = Object.assign({}, cards, { [p.id]: local.card });
    migrated = true;
  }

  let activeId = local.activeId;
  if (!profiles.some((p) => p.id === activeId)) activeId = profiles[0].id;

  if (migrated) {
    await chrome.storage.local.set({ profiles, activeId, cards });
    await chrome.storage.local.remove(['shipping', 'billing', 'card']);
  }

  // Le carte non salvate su disco vivono in memoria di sessione.
  if (!settings.rememberCard) {
    const sess = await chrome.storage.session.get('cards');
    cards = sess.cards || {};
  }

  return {
    profiles, activeId, settings, cards,
    armed: !!local.armed,
    sites: normalizeSites(local.sites)
  };
}

/** Configurazione per sito. Il formato vecchio era un semplice array di regole. */
export function normalizeSites(sites) {
  const out = {};
  for (const host of Object.keys(sites || {})) {
    const v = sites[host];
    out[host] = Array.isArray(v)
      ? { rules: v, addToCart: '', cartUrl: '', checkoutUrl: '' }
      : {
        rules: v.rules || [],
        addToCart: v.addToCart || '',
        cartUrl: v.cartUrl || '',
        checkoutUrl: v.checkoutUrl || ''
      };
  }
  return out;
}

export function emptySite() {
  return { rules: [], addToCart: '', cartUrl: '', checkoutUrl: '' };
}

export async function setArmed(armed) {
  await chrome.storage.local.set({ armed: !!armed });
}

export function activeOf(state) {
  return state.profiles.find((p) => p.id === state.activeId) || state.profiles[0];
}

export async function saveProfiles(profiles, activeId) {
  await chrome.storage.local.set({ profiles, activeId });
}

export async function saveSettings(settings) {
  await chrome.storage.local.set({ settings });
}

export async function saveSites(sites) {
  await chrome.storage.local.set({ sites });
}

async function readCards(remember) {
  const bag = remember
    ? await chrome.storage.local.get('cards')
    : await chrome.storage.session.get('cards');
  return bag.cards || {};
}

/** La carta di un profilo va in sessione (sparisce alla chiusura di Chrome)
 *  se non è stato scelto esplicitamente di ricordarla su disco. */
export async function saveCard(profileId, card, remember) {
  const clean = {};
  for (const k of CARD_FIELDS) clean[k] = String(card[k] || '').trim();
  clean.number = clean.number.replace(/[^0-9]/g, '');

  const cards = Object.assign({}, await readCards(remember), { [profileId]: clean });
  if (remember) {
    await chrome.storage.local.set({ cards });
    await chrome.storage.session.remove('cards');
  } else {
    await chrome.storage.session.set({ cards });
    await chrome.storage.local.remove('cards');
  }
}

/** Sposta tutte le carte quando cambia la scelta "ricorda su questo computer". */
export async function saveAllCards(cards, remember) {
  if (remember) {
    await chrome.storage.local.set({ cards });
    await chrome.storage.session.remove('cards');
  } else {
    await chrome.storage.session.set({ cards });
    await chrome.storage.local.remove('cards');
  }
}

export async function clearCard(profileId) {
  for (const area of [chrome.storage.local, chrome.storage.session]) {
    const bag = await area.get('cards');
    if (!bag.cards) continue;
    delete bag.cards[profileId];
    await area.set({ cards: bag.cards });
  }
}

function hostOf(url) {
  try { return new URL(url).hostname; } catch (e) { return ''; }
}

/** Configurazione valida per l'host corrente, sottodomini compresi. */
export function siteConfigFor(sites, host) {
  const merged = emptySite();
  for (const key of Object.keys(sites || {})) {
    if (host !== key && !host.endsWith('.' + key)) continue;
    const s = sites[key];
    merged.rules.push(...(s.rules || []));
    if (s.addToCart) merged.addToCart = s.addToCart;
    if (s.cartUrl) merged.cartUrl = s.cartUrl;
    if (s.checkoutUrl) merged.checkoutUrl = s.checkoutUrl;
  }
  return merged;
}

/** Regole manuali valide per l'host corrente (anche sui sottodomini). */
export function overridesFor(sites, host) {
  return siteConfigFor(sites, host).rules;
}

export async function runFill(tab, mode = 'fill') {
  const state = await loadState();
  const profile = activeOf(state);
  const host = hostOf(tab.url || '');

  if (!profile.shipping.firstName && !profile.shipping.email && !profile.shipping.address1) {
    return { error: 'Il profilo "' + profile.name + '" è vuoto: compila la scheda Profilo.' };
  }

  const payload = {
    mode,
    data: {
      shipping: profile.shipping,
      billing: profile.billing,
      card: state.settings.fillCard ? (state.cards[profile.id] || EMPTY_CARD) : null
    },
    options: {
      fillCard: !!state.settings.fillCard,
      overwrite: !!state.settings.overwrite,
      splitHouseNumber: !!state.settings.splitHouseNumber,
      highlight: state.settings.highlight !== false
    },
    overrides: overridesFor(state.sites, host)
  };

  let frames;
  try {
    frames = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      world: 'MAIN',
      injectImmediately: true,
      func: autofillPage,
      args: [payload]
    });
  } catch (e) {
    // Ripiego sul solo frame principale: di solito manca il permesso sugli iframe.
    try {
      frames = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        world: 'MAIN',
        injectImmediately: true,
        func: autofillPage,
        args: [payload]
      });
    } catch (e2) {
      return { error: 'Impossibile agire su questa pagina: ' + (e2.message || e2) };
    }
  }

  const filled = [];
  let scanned = 0, skipped = 0, frameCount = 0;
  for (const f of frames || []) {
    if (!f || !f.result) continue;
    frameCount++;
    scanned += f.result.scanned || 0;
    skipped += f.result.skipped || 0;
    for (const item of f.result.filled || []) filled.push(item);
  }

  return { host, mode, profile: profile.name, frames: frameCount, scanned, skipped, filled };
}
