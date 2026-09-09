// autopilot.js — content script registrato solo quando l'estensione è attiva.
// Sulla scheda prodotto sceglie la taglia, aggiunge al carrello e apre il
// checkout. Sul carrello o sul checkout compila i campi.
// Non preme mai un pulsante di pagamento o di conferma ordine.
// Il riconoscimento vive in cartcore.js, caricato subito prima di questo.

(() => {
  if (window.top !== window.self) return;              // solo frame principale
  if (!globalThis.CartCore) {
    console.warn('[Checkout Autofill] cartcore.js non caricato: ricarica l\'estensione da chrome://extensions.');
    return;
  }
  // Il pilota può essere iniettato mentre già gira (accensione a schede
  // aperte): senza questa guardia partirebbero due sorveglianti.
  if (globalThis.__checkoutAutofillRunning) return;
  globalThis.__checkoutAutofillRunning = true;

  const C = globalThis.CartCore;
  const PREFIX = '__checkout_autofill__';
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Il segno è per indirizzo completo: così un altro prodotto nella stessa
  // scheda riparte, e ogni passo del checkout viene compilato di nuovo.
  const here = () => location.pathname + location.search;
  function already(tag) {
    try { return sessionStorage.getItem(PREFIX + tag + here()) === '1'; } catch (e) { return false; }
  }
  function mark(tag) {
    try { sessionStorage.setItem(PREFIX + tag + here(), '1'); } catch (e) { /* modalità privata */ }
  }

  async function readState() {
    const s = await chrome.storage.local.get(['armed', 'settings', 'sites', 'profiles', 'activeId']);
    const settings = Object.assign(
      { autoFillCheckout: true, cartWait: 1500, afterAdd: 'checkout' },
      s.settings || {}
    );
    const profiles = s.profiles || [];
    const profile = profiles.find((p) => p.id === s.activeId) || profiles[0] || null;

    const site = { addToCart: '', cartUrl: '', checkoutUrl: '' };
    const sites = s.sites || {};
    for (const key of Object.keys(sites)) {
      if (location.hostname !== key && !location.hostname.endsWith('.' + key)) continue;
      const cfg = Array.isArray(sites[key]) ? {} : sites[key];
      if (cfg.addToCart) site.addToCart = cfg.addToCart;
      if (cfg.cartUrl) site.cartUrl = cfg.cartUrl;
      if (cfg.checkoutUrl) site.checkoutUrl = cfg.checkoutUrl;
    }

    return {
      armed: !!s.armed,
      settings,
      site,
      size: profile && profile.shipping ? String(profile.shipping.size || '').trim() : ''
    };
  }

  // ------------------------------------------------------ carrello e cassa

  // Qui niente segno permanente: tornare sullo stesso checkout, ricaricarlo o
  // passare al passo successivo deve poter compilare di nuovo. Ricompilare non
  // fa danni, perché i campi già pieni non vengono toccati.
  async function handleCheckout(st) {
    if (!st.settings.autoFillCheckout) return;
    const partenza = location.href;

    // Il checkout monta i campi a pezzi: si riprova finché non ne trova.
    for (let i = 0; i < 10; i++) {
      const res = await chrome.runtime.sendMessage({ type: 'FILL' }).catch(() => null);
      if (location.href !== partenza) return;         // si è cambiato passo
      if (res && res.error) { C.toast(res.error, 'warn'); return; }
      if (res && res.filled > 0) {
        C.toast(res.filled + ' campi compilati. Controlla e conferma tu.');
        return;
      }
      // Riconosciuti ma già pieni: la pagina è a posto, non c'è altro da fare.
      if (res && res.skipped > 0) return;
      await sleep(1000);
    }
  }

  // ------------------------------------------------------ scheda prodotto

  async function handleProduct(st) {
    if (already('add:')) return;

    // Il pulsante può arrivare dopo. Si accettano anche quelli disabilitati:
    // diversi negozi li sbloccano solo dopo la scelta della taglia.
    const partenza = location.href;
    let buttons = [];
    for (let i = 0; i < 15; i++) {
      buttons = C.addButtons(st.site.addToCart);
      if (buttons.length) break;
      await sleep(400);
      if (location.href !== partenza) return;         // si è cambiata pagina
    }
    if (!buttons.length) return;                      // non è una scheda prodotto

    if (buttons.length > 1 && !C.PRODUCT_URL.test(location.pathname) && !st.site.addToCart) {
      C.toast('più prodotti in questa pagina: aggiungi tu al carrello.', 'warn');
      mark('add:');
      return;
    }

    const esito = C.chooseSize(st.size);

    if (esito.status === 'mancante') {
      const lista = (esito.disponibili || []).slice(0, 8).join(', ');
      C.toast('taglia ' + st.size + ' non disponibile. Ci sono: ' + (lista || 'nessuna') + '.', 'err');
      mark('add:');
      return;
    }
    if (esito.status === 'esaurito') {
      C.toast('tutte le taglie sono esaurite.', 'err');
      mark('add:');
      return;
    }
    if (esito.status === 'ok' || esito.status === 'primo') await sleep(600);

    let target = null;
    for (let i = 0; i < 8; i++) {
      target = C.addButtons(st.site.addToCart).find(C.enabled);
      if (target) break;
      await sleep(300);
    }
    if (!target) {
      C.toast('il pulsante "aggiungi al carrello" è rimasto disattivato.', 'err');
      mark('add:');
      return;
    }

    mark('add:');
    target.click();

    const verso = st.settings.afterAdd === 'cart' ? 'il carrello' : 'il checkout';
    const detta = esito.status === 'ok' ? 'taglia ' + esito.label + ' aggiunta'
      : esito.status === 'primo' ? 'aggiunta la prima taglia libera (' + esito.label + ')'
        : 'aggiunto al carrello';
    C.toast(detta + ', apro ' + verso + '…');

    await sleep(Math.max(300, Number(st.settings.cartWait) || 1500));
    const dest = st.settings.afterAdd === 'cart'
      ? C.cartUrl(st.site.cartUrl)
      : C.checkoutUrl(st.site.checkoutUrl);
    if (dest !== location.href) location.href = dest;
  }

  // ---------------------------------------------------------- orchestrazione

  let busy = false;
  let lastUrl = '';

  async function route() {
    if (busy) return;
    busy = true;
    try {
      const st = await readState();
      if (!st.armed) return;
      if (C.isCartOrCheckout()) await handleCheckout(st);
      else await handleProduct(st);
    } catch (e) {
      console.warn('[Checkout Autofill]', e);
    } finally {
      busy = false;
    }
  }

  // Molti negozi cambiano pagina senza ricaricare: il content script non
  // ripartirebbe, quindi l'indirizzo va tenuto d'occhio.
  function watch() {
    // Finché una corsa è in ballo non si segna niente: l'indirizzo nuovo
    // verrebbe consumato a vuoto e non tornerebbe più.
    if (busy) return;
    if (location.href === lastUrl) return;
    lastUrl = location.href;
    route();
  }

  watch();
  setInterval(watch, 700);
  addEventListener('popstate', watch);
})();
