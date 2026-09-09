// cartcore.js — riconoscimento di pulsante "aggiungi al carrello", selettore
// delle taglie e indirizzo del carrello. Script classico (niente import): gira
// nel mondo isolato dell'estensione e si espone su globalThis.CartCore, così
// lo usano sia il pilota automatico sia la diagnostica del popup.

(() => {
  if (globalThis.CartCore) return;

  const DIACRITICS = new RegExp('[' + String.fromCharCode(768) + '-' + String.fromCharCode(879) + ']', 'g');

  const norm = (s) => String(s || '')
    .normalize('NFD').replace(DIACRITICS, '')
    .toLowerCase().replace(/\s+/g, ' ').trim();

  // ------------------------------------------------------------- taglie

  // Ogni riga è una taglia e i modi in cui i negozi la scrivono.
  const ALIASES = {
    xxs: ['xxs', '2xs', 'xxsmall'],
    xs: ['xs', 'xsmall', 'extrasmall'],
    s: ['s', 'small', 'piccola'],
    m: ['m', 'medium', 'med', 'media'],
    l: ['l', 'large', 'grande'],
    xl: ['xl', 'xlarge', 'extralarge'],
    xxl: ['xxl', '2xl', 'xxlarge'],
    xxxl: ['xxxl', '3xl', 'xxxlarge'],
    os: ['os', 'onesize', 'tagliaunica', 'unica', 'tu', 'onesizefitsall', 'universale']
  };

  const SIZE_KEY = /^(xxs|xs|s|m|l|xl|xxl|xxxl|os|\d{1,2}(\.\d)?)$/;

  /** Riduce "XLarge", "EU 42,5", "Taglia M" alla stessa forma di "xl", "42.5", "m". */
  function canonSize(raw) {
    let t = norm(raw)
      .replace(/[()\[\]]/g, ' ')
      .replace(/\b(eu|it|uk|us|eur|fr|taglia|size|misura|talla)\b/g, ' ')
      .replace(',', '.')
      .trim();
    const num = t.match(/^(\d{1,2}(?:\.\d)?)$/);
    if (num) return num[1].replace(/\.0$/, '');
    const compact = t.replace(/[\s\-_/]/g, '');
    for (const key of Object.keys(ALIASES)) {
      if (ALIASES[key].includes(compact)) return key;
    }
    return compact;
  }

  const isSizeLike = (raw) => SIZE_KEY.test(canonSize(raw));

  const SOLD_OUT = /(esaurit|sold ?out|out of stock|non disponibil|unavailable|not available|disabled|nicht verfugbar)/;

  function optionSoldOut(o) {
    if (o.disabled) return true;
    return SOLD_OUT.test(norm(o.textContent + ' ' + (o.className || '')));
  }

  function elementSoldOut(el) {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return true;
    const cls = typeof el.className === 'string' ? el.className : '';
    const blob = norm([cls, el.getAttribute('aria-label'), el.title, el.innerText].filter(Boolean).join(' '));
    if (SOLD_OUT.test(blob)) return true;
    const cs = getComputedStyle(el);
    return cs.textDecorationLine === 'line-through' || Number(cs.opacity) < 0.45;
  }

  function visible(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) > 0.05;
  }

  const SIZE_HINT = /(taglia|size|misura|talla|grosse|pointure|variant)/;

  /** Il selettore delle taglie, come <select> o come griglia di pulsanti. */
  function sizeChooser() {
    const selects = Array.from(document.querySelectorAll('select'));
    // Prima quelle che si vedono: un <select> nascosto è spesso un residuo.
    selects.sort((a, b) => (visible(b) ? 1 : 0) - (visible(a) ? 1 : 0));

    for (const sel of selects) {
      const hint = norm([sel.name, sel.id, sel.getAttribute('aria-label'),
        sel.getAttribute('data-testid'), typeof sel.className === 'string' ? sel.className : ''
      ].filter(Boolean).join(' '));

      const real = Array.from(sel.options).filter((o) => {
        const t = norm(o.textContent);
        if (!t) return false;
        if (!o.value && /^(seleziona|scegli|choose|select|taglia|size|--)/.test(t)) return false;
        return true;
      });
      if (real.length < 1) continue;

      const sizey = real.filter((o) => isSizeLike(o.textContent)).length;
      // Vale come selettore di taglie se lo dice il nome, oppure se le voci
      // stesse sembrano taglie (è il caso di Supreme: Small/Medium/XLarge).
      if (!SIZE_HINT.test(hint) && sizey < Math.max(1, Math.ceil(real.length / 2))) continue;

      return {
        kind: 'select',
        el: sel,
        options: real.map((o) => ({
          node: o,
          label: o.textContent.trim(),
          canon: canonSize(o.textContent),
          disabled: optionSoldOut(o)
        }))
      };
    }

    // Griglia di pulsanti/etichette: almeno due voci che sembrano taglie.
    const sel = 'button, label, li, a, span, div, [role="radio"], [role="option"], [role="button"]';
    const found = [];
    const seen = new Set();
    for (const el of document.querySelectorAll(sel)) {
      if (el.children.length > 1) continue;
      const text = (el.innerText || el.textContent || '').trim();
      if (!text || text.length > 12) continue;
      if (!isSizeLike(text)) continue;
      if (!visible(el)) continue;
      const canon = canonSize(text);
      if (seen.has(canon)) continue;      // evita etichetta + input gemelli
      seen.add(canon);
      found.push({ node: el, label: text, canon, disabled: elementSoldOut(el) });
    }
    if (found.length >= 2) return { kind: 'buttons', el: found[0].node.parentElement, options: found };
    return null;
  }

  function applyOption(chooser, option) {
    if (chooser.kind === 'select') {
      const sel = chooser.el;
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
      sel.focus();
      setter.call(sel, option.node.value);
      if (sel.value !== option.node.value) sel.selectedIndex = Array.from(sel.options).indexOf(option.node);
      sel.dispatchEvent(new Event('input', { bubbles: true }));
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }
    option.node.click();
    return true;
  }

  /** Sceglie la taglia. Senza `want` prende la prima disponibile.
   *  Esiti: assente (nessun selettore), ok, primo, mancante, esaurito. */
  function chooseSize(want) {
    const chooser = sizeChooser();
    if (!chooser) return { status: 'assente' };

    const libere = chooser.options.filter((o) => !o.disabled);
    if (!libere.length) return { status: 'esaurito', chooser };

    const wanted = String(want || '').trim() ? canonSize(want) : null;
    if (wanted) {
      const hit = libere.find((o) => o.canon === wanted);
      if (!hit) {
        return { status: 'mancante', disponibili: libere.map((o) => o.label), chooser };
      }
      applyOption(chooser, hit);
      return { status: 'ok', label: hit.label, chooser };
    }

    applyOption(chooser, libere[0]);
    return { status: 'primo', label: libere[0].label, chooser };
  }

  // ------------------------------------------- pulsante aggiungi al carrello

  const ADD = /(aggiungi al carrello|aggiungi al sacchetto|aggiungi al cestino|aggiungi alla borsa|metti nel carrello|aggiungi al bag|add to cart|add to bag|add to basket|addtocart|in den warenkorb|ajouter au panier|anadir a la cesta|agregar al carrito|adicionar ao carrinho)/;
  const NOT_ADD = /(wishlist|preferit|lista desideri|salva per|compra ora|acquista ora|buy now|buy it now|checkout|vai alla cassa|paga|pay |paypal|klarna|notific|avvisami|notify me|iscriv|newsletter|confronta|compare|trova in negozio|find in store|sold out|esaurit|out of stock)/;
  const PRODUCT_URL = /(\/prodott|\/product|\/p\/|\/dp\/|\/item|\/sku|\/shop\/|\/collections\/.+\/products)/i;

  /** Tutti i candidati, anche disabilitati: certi negozi abilitano il
   *  pulsante solo dopo che hai scelto la taglia. */
  function addButtons(custom) {
    if (custom) {
      return Array.from(document.querySelectorAll(custom)).filter(visible);
    }
    const sel = 'button, input[type="submit"], input[type="button"], a[role="button"], [role="button"], a.button, .add-to-cart, [data-testid*="add-to-cart"], [name="add"]';
    const out = [];
    for (const el of document.querySelectorAll(sel)) {
      if (!visible(el)) continue;
      const text = norm(el.innerText || el.value || el.getAttribute('aria-label') || el.title);
      if (NOT_ADD.test(text)) continue;
      // Gli attributi si guardano solo per aggiungere, mai per escludere:
      // su Supreme il pulsante buono si chiama name="remove".
      const attrs = norm([el.id, el.name, typeof el.className === 'string' ? el.className : '',
        el.getAttribute('data-testid')].filter(Boolean).join(' '));
      const byText = ADD.test(text);
      const byAttr = /add ?to ?(cart|bag|basket)|addtocart/.test(attrs);
      const byForm = !!el.closest('form[action*="/cart/add"]');
      if (byText || byAttr || byForm) out.push(el);
    }
    return out;
  }

  const enabled = (el) => !el.disabled && el.getAttribute('aria-disabled') !== 'true';

  // ------------------------------------------------------------- carrello

  // Attenzione ai plurali: su Shopify il checkout vero sta in
  // /checkouts/cn/<token>, non in /checkout.
  const CART_PATH = /(^|\/)(cart|carts|carrello|basket|bag|panier|warenkorb|cesta|checkout|checkouts|cassa|onepage|onestepcheckout)(\/|$|\?|#)/i;

  function isCartOrCheckout() {
    return CART_PATH.test(location.pathname) || /checkout/i.test(location.hostname);
  }

  function cartUrl(custom) {
    if (custom) {
      try { return new URL(custom, location.origin).href; } catch (e) { /* cade sotto */ }
    }
    for (const a of document.querySelectorAll('a[href]')) {
      const href = a.getAttribute('href') || '';
      if (/\/(cart|carrello|basket)(\/|$|\?)/i.test(href) && !/add|remove|update/i.test(href)) {
        try { return new URL(href, location.href).href; } catch (e) { /* continua */ }
      }
    }
    return location.origin + '/cart';   // vale per Shopify e per la maggior parte
  }

  function checkoutUrl(custom) {
    if (custom) {
      try { return new URL(custom, location.origin).href; } catch (e) { /* cade sotto */ }
    }
    for (const a of document.querySelectorAll('a[href]')) {
      const href = a.getAttribute('href') || '';
      if (/\/(checkout|checkouts|cassa)(\/|$|\?)/i.test(href) && !/login|logout|account|policy/i.test(href)) {
        try { return new URL(href, location.href).href; } catch (e) { /* continua */ }
      }
    }
    // Su Shopify /checkout rimanda al checkout vero; WooCommerce e Magento
    // usano lo stesso indirizzo. Con il carrello vuoto si finisce sul carrello.
    return location.origin + '/checkout';
  }

  // -------------------------------------------------------------- riquadro

  function toast(text, tone) {
    const box = document.createElement('div');
    box.textContent = 'Checkout Autofill — ' + text;
    box.style.cssText = [
      'position:fixed', 'z-index:2147483647', 'right:16px', 'bottom:16px',
      'max-width:340px', 'padding:10px 14px', 'border-radius:8px',
      'font:13px/1.4 system-ui,sans-serif', 'color:#fff',
      'background:' + (tone === 'err' ? '#dc2626' : tone === 'warn' ? '#d97706' : '#16a34a'),
      'box-shadow:0 4px 14px rgba(0,0,0,.25)', 'pointer-events:none'
    ].join(';');
    document.body.appendChild(box);
    setTimeout(() => box.remove(), 4500);
  }

  // ------------------------------------------------------------ diagnostica

  /** Racconta cosa vede in pagina, senza toccare niente. */
  function probe(custom) {
    const btns = addButtons(custom && custom.addToCart);
    const chooser = sizeChooser();
    return {
      url: location.href,
      carrelloOChckout: isCartOrCheckout(),
      indirizzoProdotto: PRODUCT_URL.test(location.pathname),
      pulsanti: btns.map((b) => ({
        testo: (b.innerText || b.value || b.getAttribute('aria-label') || '').trim().slice(0, 40),
        attivo: enabled(b)
      })),
      taglie: chooser ? {
        tipo: chooser.kind,
        voci: chooser.options.map((o) => o.label + (o.disabled ? ' (esaurita)' : ''))
      } : null,
      carrello: cartUrl(custom && custom.cartUrl),
      checkout: checkoutUrl(custom && custom.checkoutUrl),
      campiCompilabili: document.querySelectorAll('input:not([type=hidden]), select, textarea').length
    };
  }

  globalThis.CartCore = {
    norm, canonSize, visible, enabled, sizeChooser, chooseSize, addButtons,
    isCartOrCheckout, cartUrl, checkoutUrl, toast, probe, PRODUCT_URL
  };
})();
