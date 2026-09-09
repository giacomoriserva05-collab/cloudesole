// captcha.js — riconosce i captcha della pagina, ne segue i token e li rifà
// quando scadono. Va iniettato nel mondo MAIN: `grecaptcha`, `hcaptcha` e
// `turnstile` vivono lì, e dal mondo isolato degli script di estensione non
// si vedono.
//
// Non risolve niente e non ci prova. Dove c'è una sfida da superare — la
// casella di reCAPTCHA v2, quella di hCaptcha — il rinnovo azzera il widget e
// la rimette davanti a una persona. Dove non c'è nessuna sfida (reCAPTCHA v3,
// le modalità invisibili, Turnstile gestito) il token lo emette il fornitore
// su richiesta ed è lui a dargli un punteggio.

(function () {
  'use strict';

  // ---------------------------------------------------------- fornitori
  // Ogni fornitore dice come riconoscersi, dove tiene il token, quanto vale
  // e come si rifà. Le tre API gestite si somigliano molto — hCaptcha nasce
  // apposta come rimpiazzo di reCAPTCHA — ma non abbastanza da unificarle.

  function urlDi(src) {
    try { return new URL(src, location.href); } catch (e) { return null; }
  }

  /** Cerca fra i segmenti dell'indirizzo di un iframe qualcosa che somigli a
   *  una site key. Serve a Turnstile, che non la mette in query. */
  function chiaveNelPercorso(src, re) {
    var u = urlDi(src);
    if (!u) return '';
    var parti = u.pathname.split('/');
    for (var i = 0; i < parti.length; i++) if (re.test(parti[i])) return parti[i];
    return '';
  }

  var FORNITORI = [
    {
      id: 'recaptcha',
      nome: 'reCAPTCHA',
      gestito: true,
      ttl: 120,
      script: /\/recaptcha\/(api|enterprise)\.js/,
      selettore: '.g-recaptcha, [data-sitekey]:not(.h-captcha):not(.cf-turnstile)',
      campi: ['textarea[name="g-recaptcha-response"]', 'input[name="g-recaptcha-response"]'],
      iframe: 'iframe[src*="/recaptcha/"]',
      // L'iframe della sfida non porta lo stato del widget: solo quello
      // "anchor", cioè la casella, ha chiave e dimensione in query.
      daIframe: function (src) {
        if (!/\/anchor\b/.test(src)) return null;
        var u = urlDi(src);
        if (!u) return null;
        return { sitekey: u.searchParams.get('k') || '', size: u.searchParams.get('size') || 'normal' };
      },
      api: function () {
        var g = globalThis.grecaptcha;
        if (!g) return null;
        // Enterprise espone le stesse funzioni sotto un altro ramo.
        return (g.enterprise && g.enterprise.getResponse) ? g.enterprise : g;
      },
      nomeEsteso: function () {
        return (globalThis.grecaptcha && globalThis.grecaptcha.enterprise)
          ? 'reCAPTCHA Enterprise' : 'reCAPTCHA';
      },
      versione: function (ctx) {
        // La v3 si riconosce dal parametro `render` dello script: è la site
        // key, mentre la v2 esplicita scrive `explicit`.
        var u = ctx.src && urlDi(ctx.src);
        var r = u && u.searchParams.get('render');
        if (r && r !== 'explicit') return { id: 'v3', etichetta: 'v3 — punteggio', sitekey: r, sfida: false };
        var w = ctx.widget[0];
        if (w && w.size === 'invisible') return { id: 'v2i', etichetta: 'v2 — invisibile', sfida: false };
        return { id: 'v2', etichetta: 'v2 — casella da spuntare', sfida: true };
      },
      rinnova: function (ctx, api) {
        if (ctx.versione.id === 'v3') {
          api.ready(function () {
            api.execute(ctx.versione.sitekey, { action: 'submit' }).then(function (t) {
              var c = ctx.campo;
              if (c) c.value = t;
            });
          });
          return { azione: 'token nuovo richiesto a Google', sfida: false };
        }
        api.reset();
        if (ctx.versione.id === 'v2i') {
          api.execute();
          return { azione: 'verifica invisibile rilanciata', sfida: false };
        }
        return { azione: 'widget azzerato — la spunta va rimessa a mano', sfida: true };
      }
    },

    {
      id: 'hcaptcha',
      nome: 'hCaptcha',
      gestito: true,
      ttl: 120,
      script: /hcaptcha\.com\/1\/api\.js/,
      selettore: '.h-captcha, [data-hcaptcha-widget-id]',
      // hCaptcha scrive anche in `g-recaptcha-response`, per entrare nei siti
      // nati per reCAPTCHA senza cambiargli il form. Il suo campo però è il
      // primo: si guarda quello, altrimenti si legge il token dell'altro.
      campi: ['textarea[name="h-captcha-response"]', 'textarea[name="g-recaptcha-response"]'],
      iframe: 'iframe[src*="hcaptcha.com"]',
      daIframe: function (src) {
        var u = urlDi(src);
        if (!u) return null;
        var k = u.searchParams.get('sitekey');
        if (!k) return null;
        return { sitekey: k, size: u.searchParams.get('size') || 'normal' };
      },
      api: function () { return globalThis.hcaptcha || null; },
      versione: function (ctx) {
        var w = ctx.widget[0];
        return (w && w.size === 'invisible')
          ? { id: 'invisibile', etichetta: 'invisibile', sfida: false }
          : { id: 'casella', etichetta: 'casella da spuntare', sfida: true };
      },
      rinnova: function (ctx, api) {
        api.reset();
        if (ctx.versione.id === 'invisibile') {
          api.execute();
          return { azione: 'verifica invisibile rilanciata', sfida: false };
        }
        return { azione: 'widget azzerato — la spunta va rimessa a mano', sfida: true };
      }
    },

    {
      id: 'turnstile',
      nome: 'Cloudflare Turnstile',
      // Cinque minuti, non due: Turnstile è l'unico che si discosta.
      ttl: 300,
      gestito: true,
      script: /challenges\.cloudflare\.com\/turnstile/,
      selettore: '.cf-turnstile',
      campi: ['input[name="cf-turnstile-response"]', 'textarea[name="cf-turnstile-response"]'],
      iframe: 'iframe[src*="challenges.cloudflare.com"]',
      daIframe: function (src) {
        // Qui la chiave è un segmento del percorso, non un parametro.
        var k = chiaveNelPercorso(src, /^[0-9]x[A-Za-z0-9_-]{15,}$/);
        var u = urlDi(src);
        var m = u && u.pathname.match(/\/(normal|compact|flexible|invisible)\b/);
        return { sitekey: k, size: m ? m[1] : 'normal' };
      },
      api: function () { return globalThis.turnstile || null; },
      versione: function (ctx) {
        var w = ctx.widget[0];
        var a = w && w.appearance;
        if (a === 'execute') return { id: 'execute', etichetta: 'su richiesta (execute)', sfida: false };
        if (a === 'interaction-only') return { id: 'interazione', etichetta: 'solo se serve', sfida: false };
        return { id: 'gestito', etichetta: 'gestito', sfida: false };
      },
      // Turnstile è l'unico che sa dire da solo se è scaduto.
      scaduto: function (api) {
        try { return api.isExpired() === true; } catch (e) { return null; }
      },
      rinnova: function (ctx, api) {
        api.reset();
        if (ctx.versione.id === 'execute') {
          api.execute();
          return { azione: 'verifica rilanciata su richiesta', sfida: false };
        }
        // In modalità gestita Turnstile riparte da sé dopo il reset.
        return { azione: 'widget azzerato — Turnstile riparte da solo', sfida: false };
      }
    },

    // ------------------------------------------ riconosciuti e basta
    // Hanno API chiuse o proprietarie: si segnalano, così sai perché la
    // pagina non va avanti, ma non c'è niente da rifare da qui.
    { id: 'arkose', nome: 'Arkose Labs / FunCaptcha', gestito: false,
      script: /(arkoselabs\.com|funcaptcha\.co)/,
      selettore: '#funcaptcha, [data-pkey], iframe[src*="arkoselabs.com"]' },
    { id: 'geetest', nome: 'GeeTest', gestito: false,
      script: /geetest\.com/, selettore: '.geetest_holder, .geetest_btn' },
    { id: 'awswaf', nome: 'AWS WAF Captcha', gestito: false,
      script: /captcha\.awswaf\.com/, selettore: '#awswaf-captcha, [id^="awswaf"]' },
    { id: 'friendly', nome: 'Friendly Captcha', gestito: false,
      script: /friendlycaptcha/, selettore: '.frc-captcha' },
    { id: 'mtcaptcha', nome: 'MTCaptcha', gestito: false,
      script: /mtcaptcha\.com/, selettore: '.mtcaptcha, #mtcaptcha' }
  ];

  // ------------------------------------------------------------- stato
  // Un contatore per fornitore: quando il token compare, quando sparisce,
  // quante volte è stato rifatto. Sopravvive alle iniezioni successive.

  var S = globalThis.__captchaStato || { per: {}, orologio: null };
  globalThis.__captchaStato = S;

  function statoDi(id) {
    if (!S.per[id]) {
      S.per[id] = { emesso: 0, ultimo: '', scaduto: false, emissioni: 0, scadenze: 0, rinnovi: 0 };
    }
    return S.per[id];
  }

  // ------------------------------------------------------- riconoscimento
  function scriptSrc(re) {
    var nodi = document.querySelectorAll('script[src]');
    for (var i = 0; i < nodi.length; i++) if (re.test(nodi[i].src)) return nodi[i].src;
    return '';
  }

  function contenitori(f) {
    var out = [];
    var nodi = [];
    try { nodi = document.querySelectorAll(f.selettore); } catch (e) { nodi = []; }
    var presi = [];
    for (var i = 0; i < nodi.length; i++) {
      var n = nodi[i];
      // Un widget solo può far scattare più selettori: hCaptcha marca il div
      // e anche l'iframe che ci mette dentro. Il figlio non è un secondo
      // widget, quindi si salta.
      var dentro = false;
      for (var k = 0; k < presi.length; k++) if (presi[k].contains(n)) dentro = true;
      if (dentro) continue;
      presi.push(n);
      out.push({
        sitekey: n.getAttribute('data-sitekey') || n.getAttribute('data-pkey') || '',
        size: n.getAttribute('data-size') || 'normal',
        appearance: n.getAttribute('data-appearance') || '',
        // hCaptcha marca l'iframe stesso: lì non c'è nessun figlio da cercare.
        montato: n.tagName === 'IFRAME' || !!n.querySelector('iframe')
      });
    }
    if (!f.iframe || !f.daIframe) return out;

    // Ripiego per i widget montati via render() su un div qualunque, senza
    // classe né data-sitekey: l'unica traccia è l'iframe. Serve anche quando
    // un contenitore c'è ma la chiave no, che è il caso di hCaptcha esplicito.
    if (out.length && out.some(function (w) { return w.sitekey; })) return out;

    var frame = document.querySelectorAll(f.iframe);
    var trovati = [];
    for (var j = 0; j < frame.length; j++) {
      var d = f.daIframe(frame[j].src || '');
      if (!d || !d.sitekey) continue;
      trovati.push({ sitekey: d.sitekey, size: d.size, appearance: '', montato: true });
    }
    if (!trovati.length) return out;
    // Se il contenitore l'avevamo già, gli si aggiunge solo la chiave.
    if (out.length) {
      out[0].sitekey = trovati[0].sitekey;
      if (out[0].size === 'normal') out[0].size = trovati[0].size;
      return out;
    }
    return trovati;
  }

  function campoDi(f) {
    if (!f.campi) return null;
    for (var i = 0; i < f.campi.length; i++) {
      var c = document.querySelector(f.campi[i]);
      if (c) return c;
    }
    return null;
  }

  /** La verità sul token la sa la libreria: getResponse torna stringa vuota
   *  sia se non è mai stato risolto sia se è scaduto. Il campo in pagina è il
   *  ripiego per quando l'API non è ancora carica. */
  function tokenDi(f, api, campo) {
    if (api && typeof api.getResponse === 'function') {
      try {
        var t = api.getResponse();
        if (typeof t === 'string') return t;
      } catch (e) { /* nessun widget registrato: si guarda il campo */ }
    }
    return campo ? (campo.value || '') : '';
  }

  /** Un captcha disegnato in casa: un'immagine e un campo dove ricopiare i
   *  caratteri. Non c'è nessuna API, quindi si segnala e basta. */
  function captchaFattoInCasa() {
    var img = document.querySelector(
      'img[src*="captcha" i], img[alt*="captcha" i], img[class*="captcha" i], img[id*="captcha" i]');
    if (!img) return null;
    var campo = document.querySelector(
      'input[name*="captcha" i], input[id*="captcha" i], input[placeholder*="captcha" i]');
    return { immagine: true, campo: !!campo };
  }

  // ------------------------------------------------------- sorvegliante
  // Segna quando un token compare e quando sparisce. È l'unico modo per dire
  // "scaduto" invece di "non risolto": nessuna delle librerie avvisa.

  function battito() {
    for (var i = 0; i < FORNITORI.length; i++) {
      var f = FORNITORI[i];
      if (!f.gestito) continue;
      if (!scriptSrc(f.script) && !contenitori(f).length) continue;

      var api = f.api();
      var st = statoDi(f.id);
      var t = tokenDi(f, api, campoDi(f));

      if (t && t !== st.ultimo) {
        st.ultimo = t;
        st.emesso = Date.now();
        st.scaduto = false;
        st.emissioni++;
      } else if (!t && st.ultimo) {
        st.ultimo = '';
        st.scaduto = true;
        st.scadenze++;
      } else if (t && st.emesso && (Date.now() - st.emesso) / 1000 > f.ttl) {
        // Alcune integrazioni lasciano il token vecchio nel campo anche dopo
        // la scadenza: passato il tempo non vale più comunque.
        st.scaduto = true;
      }

      // Turnstile lo sa da sé: la sua parola vale più della nostra.
      if (f.scaduto && api) {
        var suo = f.scaduto(api);
        if (suo === true) st.scaduto = true;
        else if (suo === false && st.ultimo) st.scaduto = false;
      }
    }
  }

  function sorveglia() {
    if (S.orologio) return;
    battito();
    S.orologio = setInterval(battito, 1000);
  }

  function smetti() {
    clearInterval(S.orologio);
    S.orologio = null;
  }

  // ------------------------------------------------------------- lettura
  function leggi(f) {
    var src = scriptSrc(f.script);
    var widget = contenitori(f);
    if (!src && !widget.length) return null;

    var base = {
      id: f.id,
      nome: f.nomeEsteso ? f.nomeEsteso() : f.nome,
      gestito: !!f.gestito,
      widget: widget.length,
      montato: widget.some(function (w) { return w.montato; }),
      sitekey: (widget[0] && widget[0].sitekey) || ''
    };
    if (!f.gestito) {
      base.versione = 'non gestito da qui';
      return base;
    }

    var api = f.api();
    var campo = campoDi(f);
    var ctx = { src: src, widget: widget, campo: campo };
    var ver = f.versione(ctx);
    var st = statoDi(f.id);
    var t = tokenDi(f, api, campo);

    var restano = (t && !st.scaduto && st.emesso)
      ? Math.max(0, f.ttl - Math.round((Date.now() - st.emesso) / 1000)) : 0;

    base.versione = ver.etichetta;
    base.versioneId = ver.id;
    base.sfida = ver.sfida;          // serve una persona per superarlo?
    base.ttl = f.ttl;
    base.sitekey = ver.sitekey || base.sitekey;
    base.apiPronta = !!(api && api.getResponse);
    base.token = t ? t.slice(0, 14) + '…' : '';
    base.tokenLungo = t.length;
    base.valido = !!t && !st.scaduto;
    base.scaduto = st.scaduto;
    base.restano = restano;
    base.emissioni = st.emissioni;
    base.scadenze = st.scadenze;
    base.rinnovi = st.rinnovi;
    base.campo = campo ? campo.tagName.toLowerCase() : '';
    return base;
  }

  function probe() {
    var out = [];
    for (var i = 0; i < FORNITORI.length; i++) {
      var r = leggi(FORNITORI[i]);
      if (r) out.push(r);
    }
    if (!out.length) {
      var casa = captchaFattoInCasa();
      if (casa) {
        out.push({
          id: 'casalingo', nome: 'Captcha a immagine (fatto in casa)', gestito: false,
          versione: casa.campo ? 'immagine e campo di testo' : 'immagine',
          widget: 1, montato: true, sitekey: ''
        });
      }
    }
    if (out.length) sorveglia(); else smetti();
    battito();
    return { presente: out.length > 0, fornitori: out };
  }

  // ------------------------------------------------------------- rinnovo
  function rinnova(id) {
    var f = null;
    for (var i = 0; i < FORNITORI.length; i++) if (FORNITORI[i].id === id) f = FORNITORI[i];
    if (!f) return { ok: false, motivo: 'fornitore sconosciuto: ' + id };
    if (!f.gestito) return { ok: false, motivo: f.nome + ' ha un\'API chiusa: va rifatto a mano' };

    var api = f.api();
    if (!api) return { ok: false, motivo: 'la libreria di ' + f.nome + ' non è ancora carica' };

    var widget = contenitori(f);
    var ctx = { src: scriptSrc(f.script), widget: widget, campo: campoDi(f) };
    ctx.versione = f.versione(ctx);

    var st = statoDi(f.id);
    st.rinnovi++;
    try {
      var esito = f.rinnova(ctx, api);
      // Il reset azzera il token: il sorvegliante non deve contarlo come una
      // scadenza vera, l'abbiamo voluta noi.
      st.ultimo = '';
      st.emesso = 0;
      st.scaduto = false;
      return { ok: true, id: f.id, nome: f.nome, modo: ctx.versione.id,
               azione: esito.azione, sfida: esito.sfida };
    } catch (e) {
      return { ok: false, motivo: String((e && e.message) || e) };
    }
  }

  globalThis.CaptchaCore = {
    probe: probe,
    rinnova: rinnova,
    sorveglia: sorveglia,
    smetti: smetti,
    fornitori: FORNITORI.map(function (f) { return { id: f.id, nome: f.nome, gestito: !!f.gestito }; })
  };
})();
