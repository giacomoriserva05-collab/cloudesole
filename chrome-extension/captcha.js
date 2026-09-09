// captcha.js — riconosce il captcha della pagina, ne segue il token e lo
// rifà quando scade. Va iniettato nel mondo MAIN: `grecaptcha` vive lì, e
// dal mondo isolato degli script di estensione non si vede.
//
// Non risolve niente e non ci prova. Con la v2 a casella il rinnovo azzera
// il widget e la spunta la rimette una persona; con la v3 e la v2 invisibile
// non c'è nessuna sfida da superare, il token lo emette Google su richiesta
// ed è Google a dargli un punteggio.

(function () {
  'use strict';

  // Il token di reCAPTCHA vale due minuti. Non c'è modo di chiedere alla
  // libreria quanto manca, quindi il tempo lo conta il sorvegliante.
  var TTL = 120;

  var S = globalThis.__captchaStato || {
    emesso: 0,        // quando è comparso il token attuale
    ultimo: '',       // ultimo token visto, per accorgersi dei cambi
    scaduto: false,
    emissioni: 0,
    scadenze: 0,
    rinnovi: 0,
    orologio: null
  };
  globalThis.__captchaStato = S;

  function scripts() {
    var out = [];
    var nodi = document.querySelectorAll('script[src]');
    for (var i = 0; i < nodi.length; i++) out.push(nodi[i].src);
    return out;
  }

  /** Quale libreria c'è in pagina. Le alternative a reCAPTCHA le segnaliamo
   *  e basta: hanno un'API diversa e qui non sono gestite. */
  function libreria() {
    var s = scripts();
    for (var i = 0; i < s.length; i++) {
      if (/recaptcha\/(api|enterprise)\.js/.test(s[i])) {
        return { nome: /enterprise/.test(s[i]) ? 'reCAPTCHA Enterprise' : 'reCAPTCHA',
                 gestita: true, src: s[i] };
      }
      if (/hcaptcha\.com\/1\/api\.js/.test(s[i])) return { nome: 'hCaptcha', gestita: false, src: s[i] };
      if (/challenges\.cloudflare\.com\/turnstile/.test(s[i])) return { nome: 'Cloudflare Turnstile', gestita: false, src: s[i] };
    }
    if (document.querySelector('.h-captcha, [data-hcaptcha-widget-id]')) return { nome: 'hCaptcha', gestita: false, src: '' };
    if (document.querySelector('.cf-turnstile')) return { nome: 'Cloudflare Turnstile', gestita: false, src: '' };
    if (document.querySelector('.g-recaptcha, [data-sitekey], textarea[name="g-recaptcha-response"]')) {
      return { nome: 'reCAPTCHA', gestita: true, src: '' };
    }
    return null;
  }

  /** La site key della v3 sta nel parametro `render` dello script; per la v2
   *  sta sull'elemento del widget. */
  function chiaveV3(src) {
    if (!src) return '';
    try {
      var r = new URL(src).searchParams.get('render');
      return (r && r !== 'explicit') ? r : '';
    } catch (e) { return ''; }
  }

  function contenitoriV2() {
    var out = [];
    var nodi = document.querySelectorAll('.g-recaptcha, [data-sitekey]');
    for (var i = 0; i < nodi.length; i++) {
      var n = nodi[i];
      if (n.classList.contains('h-captcha') || n.classList.contains('cf-turnstile')) continue;
      out.push({
        sitekey: n.getAttribute('data-sitekey') || '',
        size: n.getAttribute('data-size') || 'normal',
        // Il widget montato appende un iframe: senza, è ancora da disegnare.
        montato: !!n.querySelector('iframe')
      });
    }
    if (out.length) return out;

    // Ripiego: parecchi siti montano il widget con grecaptcha.render() su un
    // div qualunque, senza classe né data-sitekey. Lì l'unica traccia è
    // l'iframe, che però porta con sé chiave e dimensione nella query.
    var frame = document.querySelectorAll('iframe[src*="/recaptcha/"]');
    for (var j = 0; j < frame.length; j++) {
      var src = frame[j].src || '';
      if (!/\/anchor\b/.test(src)) continue;   // l'altro iframe è quello della sfida
      var p;
      try { p = new URL(src).searchParams; } catch (e) { continue; }
      out.push({
        sitekey: p.get('k') || '',
        size: p.get('size') || 'normal',
        montato: true
      });
    }
    return out;
  }

  /** Il token dove lo scrive reCAPTCHA. Il textarea è quello della v2; la v3
   *  di solito lo mette in un campo nascosto del form, con lo stesso name. */
  function campoToken() {
    return document.querySelector('textarea[name="g-recaptcha-response"]')
        || document.querySelector('input[name="g-recaptcha-response"]')
        || document.querySelector('input[name="g-recaptcha-response-100000"]');
  }

  /** La verità sul token la sa grecaptcha: getResponse torna stringa vuota
   *  sia se non è mai stato risolto sia se è scaduto. Il campo in pagina è
   *  il ripiego per quando l'API non è raggiungibile. */
  function token() {
    try {
      if (globalThis.grecaptcha && typeof grecaptcha.getResponse === 'function') {
        var t = grecaptcha.getResponse();
        if (typeof t === 'string') return t;
      }
    } catch (e) { /* nessun widget registrato: si guarda il campo */ }
    var c = campoToken();
    return c ? c.value : '';
  }

  function versione(lib, chiave3, v2) {
    if (!lib || !lib.gestita) return null;
    if (chiave3) return 'v3';
    if (v2.length) return v2[0].size === 'invisible' ? 'v2i' : 'v2';
    // Script con render=explicit e nessun contenitore: il widget lo monta il
    // sito a mano, più avanti.
    return 'v2';
  }

  // ------------------------------------------------------- sorvegliante
  // Segna quando il token compare e quando sparisce. È l'unico modo per
  // dire "scaduto" invece di "non risolto": la libreria non avvisa nessuno.

  function battito() {
    var t = token();
    if (t && t !== S.ultimo) {
      S.ultimo = t;
      S.emesso = Date.now();
      S.scaduto = false;
      S.emissioni++;
    } else if (!t && S.ultimo) {
      S.ultimo = '';
      S.scaduto = true;
      S.scadenze++;
    } else if (t && S.emesso && (Date.now() - S.emesso) / 1000 > TTL) {
      // Alcune integrazioni lasciano il token vecchio nel campo anche dopo
      // la scadenza: dopo due minuti non vale più comunque.
      S.scaduto = true;
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
  function probe() {
    var lib = libreria();
    if (!lib) {
      smetti();
      return { presente: false, libreria: null, versione: null };
    }
    var v2 = contenitoriV2();
    var k3 = chiaveV3(lib.src);
    var ver = versione(lib, k3, v2);
    sorveglia();
    battito();

    var t = token();
    var restano = (t && !S.scaduto && S.emesso)
      ? Math.max(0, TTL - Math.round((Date.now() - S.emesso) / 1000))
      : 0;

    return {
      presente: true,
      libreria: lib.nome,
      gestita: lib.gestita,
      versione: ver,
      sitekey: k3 || (v2[0] && v2[0].sitekey) || '',
      widget: v2.length,
      montato: v2.some(function (w) { return w.montato; }),
      apiPronta: !!(globalThis.grecaptcha && grecaptcha.getResponse),
      token: t ? t.slice(0, 14) + '…' : '',
      tokenLungo: t.length,
      valido: !!t && !S.scaduto,
      scaduto: S.scaduto,
      restano: restano,
      emissioni: S.emissioni,
      scadenze: S.scadenze,
      rinnovi: S.rinnovi,
      // Il campo del token è quello che l'estensione non deve mai toccare.
      campo: campoToken() ? (campoToken().tagName.toLowerCase()) : ''
    };
  }

  // ------------------------------------------------------------- rinnovo
  function rinnova() {
    var lib = libreria();
    if (!lib || !lib.gestita) {
      return { ok: false, motivo: lib ? lib.nome + ' non è gestito qui' : 'nessun captcha in pagina' };
    }
    if (!globalThis.grecaptcha) {
      return { ok: false, motivo: 'la libreria non è ancora carica' };
    }
    var v2 = contenitoriV2();
    var k3 = chiaveV3(lib.src);
    var ver = versione(lib, k3, v2);
    S.rinnovi++;

    try {
      if (ver === 'v3') {
        // Nessuna sfida da superare: si richiede un token nuovo e lo si
        // rimette dov'era, che è esattamente quello che fa il sito quando
        // mandi il form. Il punteggio lo decide Google, non noi.
        grecaptcha.ready(function () {
          grecaptcha.execute(k3, { action: 'submit' }).then(function (t) {
            var c = campoToken();
            if (c) c.value = t;
            battito();
          });
        });
        return { ok: true, modo: 'v3', azione: 'token nuovo richiesto a Google' };
      }

      grecaptcha.reset();
      S.ultimo = '';
      S.emesso = 0;
      S.scaduto = false;

      if (ver === 'v2i') {
        grecaptcha.execute();
        return { ok: true, modo: 'v2i', azione: 'verifica invisibile rilanciata' };
      }
      return { ok: true, modo: 'v2',
               azione: 'widget azzerato — la spunta va rimessa a mano' };
    } catch (e) {
      return { ok: false, motivo: String((e && e.message) || e) };
    }
  }

  globalThis.CaptchaCore = { probe: probe, rinnova: rinnova, sorveglia: sorveglia, smetti: smetti, ttl: TTL };
})();
