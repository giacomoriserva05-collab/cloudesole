// filler.js — funzione iniettata nella pagina.
// Viene serializzata da chrome.scripting.executeScript: deve essere autosufficiente,
// niente riferimenti a variabili esterne. Tutto quello che le serve sta dentro.

export function autofillPage(cfg) {
  const data = (cfg && cfg.data) || {};
  const options = (cfg && cfg.options) || {};
  const overrides = (cfg && cfg.overrides) || [];
  const mode = (cfg && cfg.mode) || 'fill'; // 'fill' | 'preview'

  // ---------------------------------------------------------------- utilità

  const DIACRITICS = new RegExp('[' + String.fromCharCode(768) + '-' + String.fromCharCode(879) + ']', 'g');
  const norm = (s) =>
    String(s || '')
      .normalize('NFD')
      .replace(DIACRITICS, '')
      .toLowerCase()
      .replace(/[_\-.\[\]]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

  const PROVINCE = {
    AG: 'Agrigento', AL: 'Alessandria', AN: 'Ancona', AO: 'Aosta', AR: 'Arezzo',
    AP: 'Ascoli Piceno', AT: 'Asti', AV: 'Avellino', BA: 'Bari',
    BT: 'Barletta-Andria-Trani', BL: 'Belluno', BN: 'Benevento', BG: 'Bergamo',
    BI: 'Biella', BO: 'Bologna', BZ: 'Bolzano', BS: 'Brescia', BR: 'Brindisi',
    CA: 'Cagliari', CL: 'Caltanissetta', CB: 'Campobasso', CE: 'Caserta',
    CT: 'Catania', CZ: 'Catanzaro', CH: 'Chieti', CO: 'Como', CS: 'Cosenza',
    CR: 'Cremona', KR: 'Crotone', CN: 'Cuneo', EN: 'Enna', FM: 'Fermo',
    FE: 'Ferrara', FI: 'Firenze', FG: 'Foggia', FC: 'Forlì-Cesena',
    FR: 'Frosinone', GE: 'Genova', GO: 'Gorizia', GR: 'Grosseto', IM: 'Imperia',
    IS: 'Isernia', AQ: "L'Aquila", SP: 'La Spezia', LT: 'Latina', LE: 'Lecce',
    LC: 'Lecco', LI: 'Livorno', LO: 'Lodi', LU: 'Lucca', MC: 'Macerata',
    MN: 'Mantova', MS: 'Massa-Carrara', MT: 'Matera', ME: 'Messina',
    MI: 'Milano', MO: 'Modena', MB: 'Monza e della Brianza', NA: 'Napoli',
    NO: 'Novara', NU: 'Nuoro', OR: 'Oristano', PD: 'Padova', PA: 'Palermo',
    PR: 'Parma', PV: 'Pavia', PG: 'Perugia', PU: 'Pesaro e Urbino',
    PE: 'Pescara', PC: 'Piacenza', PI: 'Pisa', PT: 'Pistoia', PN: 'Pordenone',
    PZ: 'Potenza', PO: 'Prato', RG: 'Ragusa', RA: 'Ravenna',
    RC: 'Reggio Calabria', RE: 'Reggio Emilia', RI: 'Rieti', RN: 'Rimini',
    RM: 'Roma', RO: 'Rovigo', SA: 'Salerno', SS: 'Sassari', SV: 'Savona',
    SI: 'Siena', SR: 'Siracusa', SO: 'Sondrio', SU: 'Sud Sardegna',
    TA: 'Taranto', TE: 'Teramo', TR: 'Terni', TO: 'Torino', TP: 'Trapani',
    TN: 'Trento', TV: 'Treviso', TS: 'Trieste', UD: 'Udine', VA: 'Varese',
    VE: 'Venezia', VB: 'Verbano-Cusio-Ossola', VC: 'Vercelli', VR: 'Verona',
    VV: 'Vibo Valentia', VI: 'Vicenza', VT: 'Viterbo'
  };

  const COUNTRY = {
    IT: ['Italia', 'Italy', 'Italie', 'Italien'],
    FR: ['Francia', 'France'],
    DE: ['Germania', 'Germany', 'Deutschland'],
    ES: ['Spagna', 'Spain'],
    GB: ['Regno Unito', 'United Kingdom', 'UK', 'Great Britain'],
    US: ['Stati Uniti', 'United States', 'USA'],
    CH: ['Svizzera', 'Switzerland'],
    AT: ['Austria'],
    BE: ['Belgio', 'Belgium'],
    NL: ['Paesi Bassi', 'Netherlands'],
    PT: ['Portogallo', 'Portugal'],
    IE: ['Irlanda', 'Ireland'],
    SE: ['Svezia', 'Sweden'],
    DK: ['Danimarca', 'Denmark'],
    PL: ['Polonia', 'Poland'],
    GR: ['Grecia', 'Greece']
  };

  // Campi da non toccare mai, qualunque cosa somiglino.
  const EXCLUDE = /(^|\s)(search|cerca|ricerca|coupon|sconto|discount|promo ?code|codice promo|gift ?card|newsletter|quantity|quantita|captcha|otp|one ?time|token|csrf|password|passwd|pwd|login|username|user ?name|iscriv|subscribe|note|messaggio|message|comment)(\s|$)/;

  // Regole di riconoscimento. `ac` = token dell'attributo autocomplete,
  // `re` = regex su nome/id/attributi, `label` = regex su testo visibile,
  // `not` = esclusioni specifiche della regola.
  const RULES = [
    { key: 'firstName', ac: ['given-name'],
      re: /\b(first ?name|fname|given ?name|nome|prenom|vorname|name first)\b/,
      label: /\b(nome|first name|given name)\b/,
      not: /(cognome|last|surname|family|full|complet|user|utente|azienda|company|card|carta|titolare|intestatario|street|via|citt|city)/ },

    { key: 'lastName', ac: ['family-name'],
      re: /\b(last ?name|lname|surname|family ?name|cognome|nachname|apellido)\b/,
      label: /\b(cognome|last name|surname|family name)\b/ },

    { key: 'fullName', ac: ['name'],
      re: /\b(full ?name|nome completo|nominativo|name)\b/,
      label: /\b(nome e cognome|nome completo|full name|nominativo)\b/,
      not: /(first|last|given|family|card|carta|titolare|user|utente|company|azienda|street|via)/ },

    { key: 'company', ac: ['organization'],
      re: /\b(company|organization|organisation|azienda|ragione sociale|societa|business)\b/,
      label: /\b(azienda|ragione sociale|company|organizzazione)\b/ },

    { key: 'emailConfirm', ac: [],
      re: /((e ?mail).*(confirm|conferma|repeat|ripeti|verific|again|2))|((confirm|conferma|ripeti|verific).*(e ?mail))/,
      label: /((e ?mail).*(conferma|confirm|ripeti|repeat))|((conferma|confirm|ripeti).*(e ?mail))/ },

    { key: 'email', ac: ['email'],
      re: /\b(e ?mail|posta elettronica)\b/,
      label: /\b(e ?mail|indirizzo email)\b/,
      not: /(confirm|conferma|ripeti|repeat|verific)/ },

    { key: 'phone', ac: ['tel', 'tel-national', 'tel-local'],
      re: /\b(phone|telephone|telefono|tel|mobile|cellulare|celular|handy)\b/,
      label: /\b(telefono|cellulare|phone|mobile)\b/,
      not: /(prefix|prefisso|country ?code|area ?code|dial)/ },

    { key: 'fiscalCode', ac: [],
      re: /\b(codice fiscale|fiscal code|tax ?code|cf|tax ?id|partita iva|vat)\b/,
      label: /\b(codice fiscale|partita iva|vat|tax code)\b/ },

    { key: 'birthDate', ac: ['bday'],
      re: /\b(birth ?date|date ?of ?birth|dob|data di nascita|nascita|birthday)\b/,
      label: /\b(data di nascita|birth)\b/ },

    { key: 'address2', ac: ['address-line2'],
      re: /\b(address ?line ?2|address ?2|addr ?2|street ?2|interno|scala|piano|apt|apartment|suite|building|edificio|presso|complemento|additional)\b/,
      label: /\b(interno|scala|piano|presso|apartment|suite|seconda riga|indirizzo 2)\b/ },

    { key: 'houseNumber', ac: [],
      re: /\b(house ?number|street ?number|civico|numero civico|hausnummer|num ?civ)\b/,
      label: /\b(civico|numero civico|house number)\b/ },

    { key: 'address1', ac: ['address-line1', 'street-address'],
      re: /\b(address ?line ?1|address ?1|addr ?1|address|street|indirizzo|via|strasse|calle|adresse|street ?address)\b/,
      label: /\b(indirizzo|via|address|street)\b/,
      not: /(e ?mail|ip address|address ?book|address ?type|search)/ },

    { key: 'postalCode', ac: ['postal-code'],
      re: /\b(zip|postal ?code|postcode|post ?code|cap|codice postale|plz|zipcode)\b/,
      label: /\b(cap|codice postale|zip|postal code)\b/ },

    { key: 'city', ac: ['address-level2'],
      re: /\b(city|town|citta|comune|localita|ciudad|ville|ort|stadt)\b/,
      label: /\b(citta|comune|localita|city|town)\b/ },

    { key: 'province', ac: ['address-level1'],
      re: /\b(province|provincia|state|region|regione|county|prov|bundesland)\b/,
      label: /\b(provincia|regione|state|province|prov)\b/,
      not: /(stati uniti|united states)/ },

    { key: 'country', ac: ['country', 'country-name'],
      re: /\b(country|nazione|paese|pais|pays|land)\b/,
      label: /\b(paese|nazione|country)\b/ },

    { key: 'cardName', ac: ['cc-name'],
      re: /\b(card ?holder|cardholder|name ?on ?card|ccname|cc ?name|titolare|intestatario|holder ?name|nome sulla carta)\b/,
      label: /\b(titolare|intestatario|nome sulla carta|name on card|cardholder)\b/ },

    { key: 'cardNumber', ac: ['cc-number'],
      re: /\b(card ?number|cardnum|cc ?num|ccnumber|credit ?card|numero carta|carta di credito|pan|kartennummer)\b/,
      label: /\b(numero (della )?carta|card number)\b/ },

    // Il campo unico "MM/AA" ha la precedenza: se nel testo compare la coppia,
    // mese e anno separati vengono esclusi.
    { key: 'cardExpMonth', ac: ['cc-exp-month'],
      re: /((exp|scad).*(month|mese|mm))|((month|mese).*(exp|scad))|\bcc ?month\b|\bexpmonth\b/,
      label: /\b(mese|month|mm)\b/,
      not: /(mm ?[/-] ?(yy|aa)|mmyy|mmaa)/ },

    { key: 'cardExpYear', ac: ['cc-exp-year'],
      re: /((exp|scad).*(year|anno|yy))|((year|anno).*(exp|scad))|\bcc ?year\b|\bexpyear\b/,
      label: /\b(anno|year|yy)\b/,
      not: /(mm ?[/-] ?(yy|aa)|mmyy|mmaa)/ },

    { key: 'cardExp', ac: ['cc-exp'],
      re: /\b(expir|expiry|expiration|scadenza|valid ?thru|cc ?exp|exp ?date|expdate)\b/,
      label: /\b(scadenza|expiry|expiration)\b|mm ?[/-] ?(yy|aa)/ },

    { key: 'cardCvc', ac: ['cc-csc'],
      re: /\b(cvc|cvv|csc|cid|security ?code|codice (di )?sicurezza|verification ?value)\b/,
      label: /\b(cvc|cvv|codice di sicurezza|security code)\b/ }
  ];

  const CARD_KEYS = new Set(['cardNumber', 'cardName', 'cardExp', 'cardExpMonth', 'cardExpYear', 'cardCvc']);

  // ------------------------------------------------------ raccolta elementi

  function collect(root, out, depth) {
    if (depth > 12) return;
    let nodes;
    try {
      nodes = root.querySelectorAll('input, select, textarea, [contenteditable="true"]');
    } catch (e) { return; }
    for (const n of nodes) out.push(n);
    let all;
    try { all = root.querySelectorAll('*'); } catch (e) { return; }
    for (const el of all) if (el.shadowRoot) collect(el.shadowRoot, out, depth + 1);
  }

  function isVisible(el) {
    if (el.disabled || el.readOnly) return false;
    const t = (el.type || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image', 'file', 'range', 'color', 'checkbox', 'radio'].includes(t)) return false;
    if (t === 'password') return false; // le password non si toccano, mai
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) return false;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) < 0.05) return false;
    return true;
  }

  function labelText(el) {
    const parts = [];
    try {
      if (el.labels) for (const l of el.labels) parts.push(l.textContent);
    } catch (e) { /* ignora */ }
    const lb = el.getAttribute && el.getAttribute('aria-labelledby');
    if (lb) for (const id of lb.split(/\s+/)) {
      const n = document.getElementById(id);
      if (n) parts.push(n.textContent);
    }
    const wrap = el.closest && el.closest('label');
    if (wrap) parts.push(wrap.textContent);
    if (!parts.length) {
      let p = el.parentElement, hops = 0;
      while (p && hops < 3 && p !== document.body) {
        // L'etichetta si accetta solo da un contenitore che avvolge questo
        // campo e basta: altrimenti un campo senza etichetta propria si
        // prende quella del primo campo etichettato che trova sopra di sé.
        const vicini = p.querySelectorAll('input:not([type="hidden"]), select, textarea');
        if (vicini.length === 1) {
          const lab = p.querySelector('label, .label, [class*="label"]');
          if (lab) { parts.push(lab.textContent); break; }
        }
        p = p.parentElement; hops++;
      }
    }
    return parts.join(' ').slice(0, 300);
  }

  function attrText(el) {
    const a = [
      el.name, el.id, el.getAttribute('formcontrolname'),
      el.getAttribute('data-testid'), el.getAttribute('data-test'),
      el.getAttribute('data-qa'), el.getAttribute('data-cy'),
      el.getAttribute('data-field'), el.getAttribute('data-name'),
      el.getAttribute('ng-reflect-name')
    ];
    return a.filter(Boolean).join(' ');
  }

  function softText(el) {
    const bits = [el.placeholder, el.getAttribute('aria-label'), el.title];
    // Nelle <select> senza etichetta il nome del campo sta spesso nel
    // primo option, quello segnaposto: "Provincia", "Country/Region"...
    if (el.tagName === 'SELECT' && el.options && el.options.length) {
      const first = el.options[0];
      if (first && !first.value) bits.push(first.textContent);
    }
    return bits.filter(Boolean).join(' ');
  }

  function containerText(el) {
    const p = el.closest('div, fieldset, section, li, td') || el.parentElement;
    const cls = typeof el.className === 'string' ? el.className : '';
    if (!p) return cls;
    const pcls = typeof p.className === 'string' ? p.className : '';
    return cls + ' ' + pcls + ' ' + (p.id || '');
  }

  function sectionOf(el) {
    const ac = norm(el.getAttribute('autocomplete') || '');
    if (/\bbilling\b/.test(ac)) return 'billing';
    if (/\bshipping\b/.test(ac)) return 'shipping';
    let p = el, hops = 0;
    while (p && hops < 14) {
      const bits = [p.id, typeof p.className === 'string' ? p.className : '',
        p.getAttribute && p.getAttribute('data-testid'),
        p.getAttribute && p.getAttribute('name')];
      const s = norm(bits.filter(Boolean).join(' '));
      if (/(billing|fattur|invoice|rechnung)/.test(s)) return 'billing';
      if (/(shipping|spedizion|delivery|consegna|recipient|destinat)/.test(s)) return 'shipping';
      p = p.parentElement; hops++;
    }
    return 'shipping';
  }

  // -------------------------------------------------------------- matching

  // Qui non si usa norm(): trasformerebbe "given-name" in due token separati.
  function acTokens(el) {
    return String(el.getAttribute('autocomplete') || '')
      .toLowerCase().trim().split(/\s+/).filter(Boolean);
  }

  function ruleScore(el, rule, bag) {
    let best = 0, hits = 0;
    if (rule.ac.length) {
      const tokens = acTokens(el);
      if (rule.ac.some((t) => tokens.includes(t))) { best = Math.max(best, 100); hits++; }
    }
    const checks = [
      [bag.attrs, rule.re, 62],
      [bag.soft, rule.label || rule.re, 48],
      [bag.label, rule.label || rule.re, 46],
      [bag.container, rule.re, 20]
    ];
    for (const pair of checks) {
      const text = pair[0], re = pair[1], w = pair[2];
      if (!text || !re) continue;
      if (rule.not && rule.not.test(text)) continue;
      if (re.test(text)) { best = Math.max(best, w); hits++; }
    }
    if (!best) return 0;
    return best + Math.min(hits - 1, 3) * 4;
  }

  function detect(el) {
    const bag = {
      attrs: norm(attrText(el)),
      soft: norm(softText(el)),
      label: norm(labelText(el)),
      container: norm(containerText(el))
    };
    const blob = bag.attrs + ' ' + bag.soft + ' ' + bag.label;
    if (EXCLUDE.test(' ' + blob + ' ')) return null;

    let winner = null, winScore = 0;
    for (const rule of RULES) {
      const acHit = rule.ac.length && rule.ac.some((t) => acTokens(el).includes(t));
      if (rule.not && rule.not.test(blob) && !acHit) continue;
      const s = ruleScore(el, rule, bag);
      if (s > winScore) { winScore = s; winner = rule.key; }
    }

    // Correzioni in base al tipo nativo dell'input.
    const t = (el.type || '').toLowerCase();
    if (t === 'email' && winScore < 100 && winner !== 'emailConfirm') { winner = 'email'; winScore = Math.max(winScore, 70); }
    if (t === 'tel' && winScore < 60 && !CARD_KEYS.has(winner)) { winner = 'phone'; winScore = 70; }

    return winScore >= 40 && winner ? { key: winner, score: winScore } : null;
  }

  // --------------------------------------------------------- valori profilo

  function profileFor(section) {
    const ship = data.shipping || {};
    const bill = data.billing && data.billing.enabled ? data.billing : null;
    if (section !== 'billing' || !bill) return ship;
    const merged = Object.assign({}, ship);
    // L'indirizzo si eredita in blocco: se la fatturazione ha una sua via,
    // civico e interno non arrivano più da quello di spedizione.
    if (bill.address1) {
      merged.houseNumber = '';
      merged.address2 = '';
    }
    for (const k of Object.keys(bill)) {
      if (k !== 'enabled' && bill[k]) merged[k] = bill[k];
    }
    return merged;
  }

  const yy = (y) => String(y || '').slice(-2);

  function valueFor(key, section, el) {
    const p = profileFor(section);
    const c = data.card || {};
    switch (key) {
      case 'firstName': return p.firstName;
      case 'lastName': return p.lastName;
      case 'fullName': return [p.firstName, p.lastName].filter(Boolean).join(' ');
      case 'email':
      case 'emailConfirm': return p.email;
      case 'phone': return p.phone;
      case 'company': return p.company;
      case 'address1': return options.splitHouseNumber && p.houseNumber
        ? p.address1
        : [p.address1, p.houseNumber].filter(Boolean).join(' ');
      case 'address2': return p.address2;
      case 'houseNumber': return p.houseNumber;
      case 'city': return p.city;
      case 'postalCode': return p.postalCode;
      case 'province': return p.province;
      case 'country': return p.country;
      case 'fiscalCode': return p.fiscalCode;
      case 'birthDate': return p.birthDate;
      case 'cardName': return c.name || [p.firstName, p.lastName].filter(Boolean).join(' ');
      case 'cardNumber': return String(c.number || '').replace(/\s+/g, '');
      case 'cardCvc': return c.cvc;
      case 'cardExpMonth': return c.expMonth ? String(c.expMonth).padStart(2, '0') : '';
      case 'cardExpYear': {
        const hint = norm(softText(el) + ' ' + labelText(el));
        const wantsFour = /yyyy|aaaa|20 ?yy/.test(hint) || el.maxLength === 4;
        return wantsFour ? String(c.expYear || '') : yy(c.expYear);
      }
      case 'cardExp': {
        if (!c.expMonth || !c.expYear) return '';
        const ph = norm(el.placeholder || '');
        const sep = ph.includes('-') ? '-' : '/';
        const year = /yyyy|aaaa/.test(ph) ? String(c.expYear) : yy(c.expYear);
        return String(c.expMonth).padStart(2, '0') + sep + year;
      }
      default: return '';
    }
  }

  // Alternative accettabili, usate soprattutto per le <select>.
  function candidates(key, value) {
    const v = String(value || '');
    if (!v) return [];
    if (key === 'country') {
      const code = v.toUpperCase();
      return [code].concat(COUNTRY[code] || []).concat([v]);
    }
    if (key === 'province') {
      const code = v.toUpperCase();
      const name = PROVINCE[code];
      const rev = Object.keys(PROVINCE).find((k) => norm(PROVINCE[k]) === norm(v));
      return [code, name, rev, v].filter(Boolean);
    }
    if (key === 'cardExpMonth') {
      const n = parseInt(v, 10);
      return [String(n).padStart(2, '0'), String(n), v];
    }
    if (key === 'cardExpYear') {
      const n = parseInt(v, 10);
      const four = n < 100 ? 2000 + n : n;
      return [String(four), String(four).slice(-2), v];
    }
    return [v];
  }

  // ------------------------------------------------------------- scrittura

  function nativeSet(el, value) {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
      : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    if (desc && desc.set) desc.set.call(el, value);
    else el.value = value;
  }

  function firePre(el) {
    try { el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })); } catch (e) { /* ignora */ }
    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    try { el.focus({ preventScroll: true }); } catch (e) { el.focus(); }
    el.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
  }

  function firePost(el) {
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Unidentified' }));
    el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Unidentified' }));
    el.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
    try { el.blur(); } catch (e) { /* ignora */ }
  }

  function fillSelect(el, opts) {
    const list = Array.from(el.options || []);
    const wanted = opts.map(norm).filter(Boolean);
    let found = null;
    for (const w of wanted) {
      found = list.find((o) => norm(o.value) === w) || list.find((o) => norm(o.textContent) === w);
      if (found) break;
    }
    if (!found) {
      for (const w of wanted) {
        found = list.find((o) => w.length > 1 && norm(o.textContent).startsWith(w)) ||
                list.find((o) => w.length > 3 && norm(o.textContent).includes(w));
        if (found) break;
      }
    }
    if (!found) return false;
    firePre(el);
    nativeSet(el, found.value);
    if (el.value !== found.value) el.selectedIndex = list.indexOf(found);
    firePost(el);
    return true;
  }

  function fillText(el, value) {
    let v = String(value);
    if (el.maxLength && el.maxLength > 0 && v.length > el.maxLength) {
      const compact = v.replace(/[\s/-]/g, '');
      v = compact.length <= el.maxLength ? compact : v.slice(0, el.maxLength);
    }
    firePre(el);
    if (el.isContentEditable) {
      el.textContent = v;
    } else {
      nativeSet(el, '');
      el.dispatchEvent(new Event('input', { bubbles: true }));
      nativeSet(el, v);
    }
    firePost(el);
    return true;
  }

  function highlight(el, color) {
    const prevOutline = el.style.outline;
    const prevOffset = el.style.outlineOffset;
    el.style.outline = '2px solid ' + color;
    el.style.outlineOffset = '1px';
    setTimeout(() => {
      el.style.outline = prevOutline;
      el.style.outlineOffset = prevOffset;
    }, 2200);
  }

  function mask(key, value) {
    const v = String(value || '');
    if (key === 'cardNumber') return v.length > 4 ? '•••• ' + v.slice(-4) : '••••';
    if (key === 'cardCvc') return '•••';
    return v;
  }

  // ------------------------------------------------------------ esecuzione

  const elements = [];
  collect(document, elements, 0);

  // Override manuali per sito: selettore CSS -> chiave.
  const forced = new Map();
  for (const ov of overrides) {
    if (!ov || !ov.selector || !ov.key) continue;
    try {
      for (const el of document.querySelectorAll(ov.selector)) forced.set(el, ov.key);
    } catch (e) { /* selettore non valido: si ignora */ }
  }

  const used = new Set();   // "sezione:chiave" già compilati in questo frame
  const out = [];
  let scanned = 0;
  let skipped = 0;          // riconosciuti ma già pieni: la pagina è a posto

  for (const el of elements) {
    if (!isVisible(el)) continue;
    scanned++;

    let key = forced.get(el) || null;
    if (!key) {
      const d = detect(el);
      if (!d) continue;
      key = d.key;
    }
    if (CARD_KEYS.has(key) && !options.fillCard) continue;

    // I dati della carta non dipendono dalla sezione: una sola voce per chiave.
    const section = CARD_KEYS.has(key) ? 'card' : sectionOf(el);
    const stamp = section + ':' + key;
    if (used.has(stamp)) continue;

    const value = valueFor(key, section, el);
    if (value === undefined || value === null || value === '') continue;

    const current = (el.isContentEditable ? el.textContent : el.value) || '';
    if (current.trim() && !options.overwrite) { used.add(stamp); skipped++; continue; }

    const label = (labelText(el) || el.name || el.id || '').replace(/\s+/g, ' ').trim().slice(0, 60);

    if (mode === 'preview') {
      out.push({ key, section, value: mask(key, value), label, ok: true });
      highlight(el, '#2563eb');
      used.add(stamp);
      continue;
    }

    let ok = false;
    try {
      ok = el.tagName === 'SELECT' ? fillSelect(el, candidates(key, value)) : fillText(el, value);
    } catch (e) { ok = false; }

    if (ok) {
      used.add(stamp);
      out.push({ key, section, value: mask(key, value), label, ok: true });
      if (options.highlight !== false) highlight(el, '#16a34a');
    } else {
      out.push({ key, section, value: mask(key, value), label, ok: false });
      if (options.highlight !== false) highlight(el, '#dc2626');
    }
  }

  return {
    ok: true,
    mode,
    url: location.href,
    host: location.hostname,
    isTop: window.top === window.self,
    scanned,
    skipped,
    filled: out
  };
}
