// GENERATO da ios-app/tools/sync-js.py — non modificare a mano.
// Sorgente: chrome-extension/shopify.js

// shopify.js — la via veloce: niente pagina da leggere, niente pulsanti da
// aspettare. Shopify espone gli stessi endpoint che usa il negozio stesso,
// e si va dritti al carrello con due richieste.
//
//   GET  /products/<handle>.js   varianti, taglie, disponibilità
//   POST /cart/add.js            aggiunta al carrello
//   GET  /cart.js                stato del carrello
//
// Gira dentro la pagina (mondo isolato), non da codice nativo: così il cookie
// del carrello è già quello del negozio e /checkout si apre pieno. Da Swift
// con URLSession finirebbe in un archivio separato e il carrello resterebbe
// vuoto.
//
// Non aggira nulla: sono le stesse richieste che il sito fa da sé quando
// premi "aggiungi al carrello". Se il negozio non risponde, si torna alla
// via lenta che legge il DOM.

(() => {
  if (globalThis.ShopifyEngine) return;

  const C = () => globalThis.CartCore;

  /** L'handle del prodotto sta nell'indirizzo: /products/<handle> */
  function handleCorrente() {
    const m = location.pathname.match(/\/products\/([^/?#]+)/i);
    return m ? m[1] : null;
  }

  /** Scarica la scheda prodotto in JSON. Se non è Shopify, o se il negozio
   *  ha chiuso l'endpoint, restituisce null e si prosegue dal DOM. */
  async function prodotto(handle) {
    const nome = handle || handleCorrente();
    if (!nome) return null;
    try {
      const r = await fetch(`/products/${encodeURIComponent(nome)}.js`, {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' }
      });
      if (!r.ok) return null;
      const tipo = r.headers.get('content-type') || '';
      if (!/json/i.test(tipo)) return null;      // Supreme risponde HTML qui
      const dati = await r.json();
      return dati && Array.isArray(dati.variants) ? dati : null;
    } catch (e) {
      return null;
    }
  }

  const libere = (p) => (p.variants || []).filter((v) => v.available);

  /** Le etichette sotto cui una variante può nascondere la taglia. */
  function etichette(v) {
    return [v.option1, v.option2, v.option3, v.public_title, v.title]
      .filter((x) => typeof x === 'string' && x.trim());
  }

  /** Sceglie la variante. Senza taglia prende la prima disponibile, come fa
   *  il pilota sul DOM. Stessi alias: M trova Medium, XL trova XLarge. */
  function scegliVariante(p, taglia) {
    const disponibili = libere(p);
    if (!disponibili.length) return { status: 'esaurito' };

    const voluta = String(taglia || '').trim();
    if (!voluta) {
      const v = disponibili[0];
      return { status: 'primo', variante: v, label: etichette(v)[0] || v.title };
    }

    const core = C();
    const canon = core ? core.canonSize(voluta) : voluta.toLowerCase();
    const trovata = disponibili.find((v) =>
      etichette(v).some((e) => (core ? core.canonSize(e) : e.toLowerCase()) === canon));

    if (!trovata) {
      return {
        status: 'mancante',
        disponibili: disponibili.map((v) => etichette(v)[0] || v.title)
      };
    }
    return { status: 'ok', variante: trovata, label: etichette(trovata)[0] || trovata.title };
  }

  /** Aggiunge al carrello. È la stessa richiesta del pulsante del negozio. */
  async function aggiungi(varianteId, quantita) {
    try {
      const r = await fetch('/cart/add.js', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ id: varianteId, quantity: quantita || 1 })
      });
      if (r.ok) return { ok: true };
      // 422 quando la variante è finita fra il controllo e l'aggiunta.
      let motivo = 'il negozio ha rifiutato l\'aggiunta';
      try {
        const e = await r.json();
        if (e && (e.description || e.message)) motivo = e.description || e.message;
      } catch (x) { /* corpo non JSON */ }
      return { ok: false, motivo, stato: r.status };
    } catch (e) {
      return { ok: false, motivo: String((e && e.message) || e) };
    }
  }

  async function carrello() {
    try {
      const r = await fetch('/cart.js', {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' }
      });
      return r.ok ? await r.json() : null;
    } catch (e) {
      return null;
    }
  }

  /** Il giro completo: leggi, scegli, aggiungi. Restituisce sempre un esito
   *  parlante, così chi chiama sa se ripiegare sul DOM o fermarsi e dirlo. */
  async function aggiungiTaglia(taglia) {
    const p = await prodotto();
    if (!p) return { status: 'nonShopify' };

    const scelta = scegliVariante(p, taglia);
    if (scelta.status === 'esaurito' || scelta.status === 'mancante') {
      return Object.assign({ prodotto: p.title }, scelta);
    }

    const esito = await aggiungi(scelta.variante.id, 1);
    if (!esito.ok) {
      return { status: 'rifiutato', motivo: esito.motivo, label: scelta.label };
    }
    return { status: scelta.status, label: scelta.label, prodotto: p.title };
  }

  globalThis.ShopifyEngine = {
    handleCorrente, prodotto, scegliVariante, aggiungi, carrello, aggiungiTaglia
  };
})();
