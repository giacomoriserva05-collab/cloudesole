// bridge.js — il pilota automatico dentro l'app iOS.
// È il gemello di chrome-extension/autopilot.js: stessa sequenza, stessi
// freni. Cambia da dove arriva lo stato (lo inietta l'app, non chrome.storage)
// e come si compila (chiamata diretta a __CA_FILL, senza service worker).
// Gira in un mondo isolato della WKWebView: la pagina non vede questi dati.
// Non preme mai un pulsante di pagamento o di conferma ordine.

(() => {
  if (globalThis.__CA_BRIDGE) return;
  globalThis.__CA_BRIDGE = true;

  const C = globalThis.CartCore;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Lo stato lo scrive l'app prima che la pagina parta, e lo aggiorna quando
  // cambi profilo o impostazioni senza ricaricare.
  let stato = globalThis.__CA_STATE || null;
  globalThis.__CA_setState = (s) => { stato = s; };

  function versoApp(messaggio) {
    try {
      webkit.messageHandlers.autofill.postMessage(messaggio);
    } catch (e) {
      // Fuori dall'app (banco di prova nel browser) si finisce qui.
      if (globalThis.__CA_TEST) globalThis.__CA_TEST.push(messaggio);
    }
  }

  const avviso = (testo, tono) => versoApp({ type: 'toast', text: testo, tone: tono || 'ok' });

  // ------------------------------------------------------ stato per il sito

  function perQuestoSito() {
    const fuori = { addToCart: '', cartUrl: '', checkoutUrl: '', rules: [] };
    const siti = (stato && stato.sites) || {};
    for (const chiave of Object.keys(siti)) {
      if (location.hostname !== chiave && !location.hostname.endsWith('.' + chiave)) continue;
      const s = siti[chiave] || {};
      if (s.addToCart) fuori.addToCart = s.addToCart;
      if (s.cartUrl) fuori.cartUrl = s.cartUrl;
      if (s.checkoutUrl) fuori.checkoutUrl = s.checkoutUrl;
      if (s.rules) fuori.rules.push(...s.rules);
    }
    return fuori;
  }

  function configurazioneCompilazione(sito) {
    const s = (stato && stato.settings) || {};
    return {
      mode: 'fill',
      data: {
        shipping: (stato.profile && stato.profile.shipping) || {},
        billing: (stato.profile && stato.profile.billing) || { enabled: false },
        card: s.fillCard ? (stato.card || null) : null
      },
      options: {
        fillCard: !!s.fillCard,
        overwrite: !!s.overwrite,
        splitHouseNumber: !!s.splitHouseNumber,
        highlight: s.highlight !== false
      },
      overrides: sito.rules
    };
  }

  // ------------------------------------------------------------ compilazione

  /** Compila la pagina. Restituisce il risultato grezzo del motore. */
  function compilaOra(sito) {
    if (typeof globalThis.__CA_FILL !== 'function') return null;
    try {
      return globalThis.__CA_FILL(configurazioneCompilazione(sito || perQuestoSito()));
    } catch (e) {
      versoApp({ type: 'log', text: 'errore in compilazione: ' + (e && e.message) });
      return null;
    }
  }

  // Niente segno permanente sul checkout: tornarci sopra, ricaricarlo o
  // passare al passo dopo deve poter ricompilare. I campi già pieni non
  // vengono toccati, quindi insistere non fa danni.
  async function suCheckout(sito) {
    const s = (stato && stato.settings) || {};
    if (!s.autoFillCheckout) return;
    const partenza = location.href;

    for (let i = 0; i < 10; i++) {
      const res = compilaOra(sito);
      if (location.href !== partenza) return;
      if (res) {
        const messi = (res.filled || []).filter((f) => f.ok !== false).length;
        if (messi > 0) {
          versoApp({ type: 'filled', count: messi, fields: res.filled });
          avviso(messi + ' campi compilati. Controlla e conferma tu.');
          return;
        }
        if (res.skipped > 0) return;   // già pieni: la pagina è a posto
      }
      await sleep(1000);
    }
  }

  // ----------------------------------------------------------- scheda prodotto

  const PREFIX = '__ca_done__';
  const qui = () => location.pathname + location.search;
  const gia = (tag) => { try { return sessionStorage.getItem(PREFIX + tag + qui()) === '1'; } catch (e) { return false; } };
  const segna = (tag) => { try { sessionStorage.setItem(PREFIX + tag + qui(), '1'); } catch (e) { /* privata */ } };

  async function suProdotto(sito) {
    if (gia('add:')) return;
    const s = (stato && stato.settings) || {};
    const taglia = (stato.profile && stato.profile.shipping && stato.profile.shipping.size) || '';

    const partenza = location.href;
    let pulsanti = [];
    for (let i = 0; i < 15; i++) {
      pulsanti = C.addButtons(sito.addToCart);
      if (pulsanti.length) break;
      await sleep(400);
      if (location.href !== partenza) return;
    }
    if (!pulsanti.length) return;                    // non è una scheda prodotto

    if (pulsanti.length > 1 && !C.PRODUCT_URL.test(location.pathname) && !sito.addToCart) {
      avviso('più prodotti in questa pagina: aggiungi tu al carrello.', 'warn');
      segna('add:');
      return;
    }

    const esito = C.chooseSize(taglia);

    if (esito.status === 'mancante') {
      const lista = (esito.disponibili || []).slice(0, 8).join(', ');
      avviso('taglia ' + taglia + ' non disponibile. Ci sono: ' + (lista || 'nessuna') + '.', 'err');
      segna('add:');
      return;
    }
    if (esito.status === 'esaurito') {
      avviso('tutte le taglie sono esaurite.', 'err');
      segna('add:');
      return;
    }
    if (esito.status === 'ok' || esito.status === 'primo') await sleep(600);

    let bersaglio = null;
    for (let i = 0; i < 8; i++) {
      bersaglio = C.addButtons(sito.addToCart).find(C.enabled);
      if (bersaglio) break;
      await sleep(300);
    }
    if (!bersaglio) {
      avviso('il pulsante "aggiungi al carrello" è rimasto disattivato.', 'err');
      segna('add:');
      return;
    }

    segna('add:');
    bersaglio.click();

    const verso = s.afterAdd === 'cart' ? 'il carrello' : 'il checkout';
    const detta = esito.status === 'ok' ? 'taglia ' + esito.label + ' aggiunta'
      : esito.status === 'primo' ? 'aggiunta la prima taglia libera (' + esito.label + ')'
        : 'aggiunto al carrello';
    versoApp({ type: 'added', size: esito.label || '', status: esito.status });
    avviso(detta + ', apro ' + verso + '…');

    await sleep(Math.max(300, Number(s.cartWait) || 1500));
    const meta = s.afterAdd === 'cart' ? C.cartUrl(sito.cartUrl) : C.checkoutUrl(sito.checkoutUrl);
    if (meta !== location.href) location.href = meta;
  }

  // ---------------------------------------------------------- orchestrazione

  let occupato = false;
  let ultimoUrl = '';

  async function passa() {
    if (occupato) return;
    occupato = true;
    try {
      if (!stato || !stato.armed) return;
      const sito = perQuestoSito();
      if (C.isCartOrCheckout()) await suCheckout(sito);
      else await suProdotto(sito);
    } catch (e) {
      versoApp({ type: 'log', text: 'errore: ' + (e && e.message) });
    } finally {
      occupato = false;
    }
  }

  function guarda() {
    if (occupato) return;                 // l'indirizzo nuovo si riprende dopo
    if (location.href === ultimoUrl) return;
    ultimoUrl = location.href;
    passa();
  }

  // --------------------------------------------------- comandi dall'app

  /** "Compila adesso": una passata sola, anche a pilota spento. */
  globalThis.__CA_fillNow = () => {
    const res = compilaOra(perQuestoSito());
    if (!res) return { filled: 0, skipped: 0 };
    const messi = (res.filled || []).filter((f) => f.ok !== false).length;
    return { filled: messi, skipped: res.skipped || 0, scanned: res.scanned || 0, fields: res.filled || [] };
  };

  /** Diagnostica: cosa vede in pagina, senza toccare niente. */
  globalThis.__CA_probe = () => {
    const sito = perQuestoSito();
    const base = C.probe(sito);
    let anteprima = [];
    try {
      const cfg = configurazioneCompilazione(sito);
      cfg.mode = 'preview';
      const res = globalThis.__CA_FILL(cfg);
      anteprima = (res && res.filled) || [];
    } catch (e) { anteprima = []; }
    return Object.assign(base, { campi: anteprima });
  };

  guarda();
  setInterval(guarda, 700);
  addEventListener('popstate', guarda);
})();
