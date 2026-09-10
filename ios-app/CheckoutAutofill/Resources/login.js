// login.js — riconosce il modulo di accesso e ci scrive dentro.
//
// Sta separato dal resto apposta: `filler.js` i campi password non li tocca
// mai, in nessun caso, ed è giusto che resti così. Qui invece si scrive una
// password, ma solo quando lo chiedi tu premendo la chiave, e solo dopo che
// il telefono ti ha riconosciuto.
//
// Le credenziali non stanno in `__CA_STATE` e non restano da nessuna parte:
// arrivano come argomenti di questa chiamata e muoiono con essa. Il modulo
// non viene mai inviato: il pulsante "Accedi" lo premi tu.

(() => {
  if (globalThis.LoginEngine) return;

  const visibile = (el) => {
    if (!el || el.disabled || el.readOnly) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) > 0.05;
  };

  const testo = (el) => [
    el.name, el.id, el.getAttribute('autocomplete'), el.placeholder,
    el.getAttribute('aria-label'), el.type
  ].filter(Boolean).join(' ').toLowerCase();

  /** Il campo utente: quello giusto sta di solito prima della password e
   *  dentro lo stesso modulo. Si parte da lì e si allarga solo se serve. */
  function campoUtente(password) {
    const candidati = [];
    const modulo = password.closest('form');
    const ambito = modulo || document;

    for (const el of ambito.querySelectorAll('input')) {
      const t = (el.type || 'text').toLowerCase();
      if (!['text', 'email', 'tel', ''].includes(t)) continue;
      if (!visibile(el)) continue;
      const b = testo(el);
      // Cercare non è accedere: la casella di ricerca si scarta.
      if (/(search|cerca|coupon|sconto|promo|cap\b|postal|zip)/.test(b)) continue;
      candidati.push(el);
    }
    if (!candidati.length) return null;

    // Prima scelta: chi lo dichiara. Poi chi precede la password.
    const dichiarato = candidati.find((el) =>
      /(username|user|email|e-mail|login|account|utente)/.test(testo(el)));
    if (dichiarato) return dichiarato;

    const prima = candidati.filter((el) =>
      el.compareDocumentPosition(password) & Node.DOCUMENT_POSITION_FOLLOWING);
    return prima.length ? prima[prima.length - 1] : candidati[0];
  }

  function password() {
    const tutte = Array.from(document.querySelectorAll('input[type="password"]')).filter(visibile);
    if (!tutte.length) return null;
    // Con due o più campi è una registrazione o un cambio password: non è
    // roba nostra, e riempirla farebbe danni.
    if (tutte.length > 1) return { troppe: true };
    return tutte[0];
  }

  /** Scrive come farebbe una tastiera, altrimenti React se ne accorge e
   *  rimette il campo vuoto al primo clic. Stessa tecnica di filler.js. */
  function scrivi(el, valore) {
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
    el.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
    if (desc && desc.set) desc.set.call(el, ''); else el.value = '';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    if (desc && desc.set) desc.set.call(el, valore); else el.value = valore;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
    try { el.blur(); } catch (e) { /* niente */ }
  }

  /** C'è un modulo di accesso qui? Serve all'app per accendere la chiave. */
  function guarda() {
    const p = password();
    if (!p) return { presente: false };
    if (p.troppe) return { presente: false, motivo: 'piuCampiPassword' };
    const u = campoUtente(p);
    return {
      presente: true,
      utenteTrovato: !!u,
      etichettaUtente: u ? (u.placeholder || u.name || u.id || '').slice(0, 40) : ''
    };
  }

  /** Compila e basta: il modulo non viene inviato. Premere "Accedi" al posto
   *  tuo su una pagina sbagliata significa un tentativo fallito in più, e su
   *  certi siti bastano pochi tentativi per bloccare l'account. */
  function compila(utente, segreto) {
    const p = password();
    if (!p) return { ok: false, motivo: 'nessun campo password in questa pagina' };
    if (p.troppe) return { ok: false, motivo: 'più campi password: sembra una registrazione' };

    const u = campoUtente(p);
    if (u && utente) scrivi(u, utente);
    if (segreto) scrivi(p, segreto);

    return { ok: true, utente: !!(u && utente), password: !!segreto };
  }

  globalThis.LoginEngine = { guarda, compila };
})();
