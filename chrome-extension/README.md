# Checkout Autofill

Estensione Chrome con un interruttore. Da spenta non fa niente. Da accesa:
apri la scheda prodotto e lei sceglie la taglia, aggiunge al carrello e apre il
checkout, dove compila spedizione, fatturazione e pagamento. Riconosce i campi
da sola, in italiano e in inglese, senza configurare nulla sito per sito.

È il pezzo che manca al monitor: il monitor ti dice che il prodotto è live,
l'estensione ti porta dal link al checkout senza che tu tocchi nulla.
**Si ferma prima dell'ordine**: non preme mai "paga" né "conferma acquisto",
l'ultimo clic resta tuo.

> Aggiungere al carrello in automatico non è la stessa cosa che compilare i
> propri dati: parecchi retailer lo vietano nelle condizioni d'uso e qualcuno
> sospende l'account. Vale la pena saperlo prima di accendere l'interruttore.

---

## Installazione

1. Apri `chrome://extensions/`
2. Attiva **Modalità sviluppatore** (interruttore in alto a destra)
3. **Carica estensione non pacchettizzata** e scegli questa cartella
   (`chrome-extension`)
4. Fissa l'icona alla barra con la puntina

Non serve pubblicarla sul Web Store: resta installata finché non la rimuovi.

> **Dopo ogni modifica ai file serve il pulsante Ricarica** (l'icona circolare
> sulla scheda dell'estensione in `chrome://extensions/`): lo script che gira
> sulle pagine viene registrato una volta e resta registrato, quindi senza
> ricaricare Chrome continua a iniettare la versione vecchia. Le schede del
> negozio invece **non** vanno ricaricate: accendendo l'interruttore il pilota
> entra da solo anche in quelle già aperte.

## Uso

Apri il popup dall'icona, compila la scheda **Profilo** una volta sola — si
salva da sé, non c'è nessun pulsante "Salva" — scrivi la **taglia** in fondo al
profilo, poi premi **Attiva l'estensione**.

La prima attivazione chiede l'accesso ai siti: senza, l'estensione non può
agire su una pagina che non hai aperto tu dal popup, e resta spenta. Da accesa
il pallino in alto a sinistra diventa verde e sull'icona compare **ON**.

**Si accende una volta e basta.** L'interruttore aspetta che lo script risulti
davvero registrato prima di dirti che è attivo, entra nelle schede già aperte
senza chiederti di ricaricarle, e se per qualsiasi motivo la registrazione si
perde, si rimette da sola alla prima apertura del popup.

Da lì in poi, su una scheda prodotto:

1. sceglie la taglia scritta nel profilo, saltando quelle esaurite — se il
   campo taglia è vuoto, o il prodotto non ha taglie, prende la prima
   disponibile e va avanti lo stesso;
2. preme "Aggiungi al carrello" — mai "Acquista ora", mai "Preferiti";
3. aspetta un attimo e apre **la pagina di checkout** (dalle Opzioni si può
   scegliere il carrello).

Un riquadro in basso a destra dice sempre cosa ha fatto, o perché non ha fatto
niente. Sul checkout compila i campi da sé, e siccome quasi tutti i checkout
montano il modulo a pezzi, **riprova per dieci secondi** finché i campi non
compaiono; si ferma prima se trova i campi già pieni. Ricompila a ogni passo
del checkout, e anche se torni indietro o ricarichi la stessa pagina: non
esiste un "l'ho già fatto una volta" che lo blocchi, perché ricompilare non fa
danni — i campi già scritti non vengono toccati. Per fermare tutto: premi di
nuovo l'interruttore.

Molti negozi cambiano pagina senza ricaricare (Shopify, i checkout a passi):
il pilota tiene d'occhio l'indirizzo e riparte da solo quando cambia, senza
aspettare un ricaricamento che non arriverà.

Restano due modi manuali, per quando l'estensione è spenta: il collegamento
**Compila adesso questa pagina** sotto l'interruttore e la scorciatoia
<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Y</kbd>, che si cambia da
`chrome://extensions/shortcuts`. I campi toccati si accendono per due secondi:
verde se compilati, rosso se il riconoscimento è riuscito ma la scrittura no.

### Quando il pilota automatico si ferma da solo

Sono i freni che gli impediscono di fare danni al posto tuo:

- **più pulsanti "aggiungi al carrello" in pagina** e l'indirizzo non sembra
  quello di una scheda prodotto: è un elenco, non tocca niente;
- **la taglia che hai chiesto non c'è o è esaurita**: te lo dice, elenca quelle
  disponibili e si ferma, senza ripiegare su una taglia che non hai scelto;
- **tutte le taglie esaurite**, o pulsante che resta disattivato: si ferma e lo
  dice;
- **una volta sola per pagina e per scheda**, ma solo per l'aggiunta al
  carrello: se torni indietro sullo stesso prodotto non lo riaggiunge (per
  riprovare, apri il link in una scheda nuova). La compilazione del checkout
  non ha questo limite;
- **pagine di carrello e checkout**: lì non aggiunge, semmai compila;
- **nessun clic su pagamento, conferma, PayPal o "acquista ora"**, in nessun
  caso.

### Profili salvati

La barra sopra le schede tiene i profili: quanti ne vuoi, ognuno col suo nome,
il suo indirizzo e la sua carta. Il menu a tendina sceglie quello attivo — è
quello che verrà usato dal pulsante e dalla scorciatoia.

- **Nuovo** crea un profilo vuoto e ti porta sul campo del nome.
- **Duplica** copia indirizzo, fatturazione e carta del profilo attivo: comodo
  per due indirizzi che cambiano solo per la via.
- **Elimina** chiede conferma sullo stesso pulsante (un primo clic scrive
  "Confermi?", il secondo esegue) e si disattiva quando resta un solo profilo.

Il nome si cambia dal campo **Nome del profilo** in cima alla scheda Profilo:
la tendina si aggiorna mentre scrivi. Non c'è nessun pulsante "Salva" — ogni
modifica viene scritta da sola dopo un attimo, e cambiando profilo quello che
lasci viene salvato prima del passaggio.

Se avevi già usato una versione precedente con un profilo solo, al primo avvio
i tuoi dati vengono spostati dentro un profilo chiamato "Principale": non si
perde niente e non devi fare nulla.

### Le quattro schede

| Scheda | A cosa serve |
| --- | --- |
| **Profilo** | Nome del profilo, contatti, indirizzo, taglia. Con la spunta si aggiunge un indirizzo di fatturazione diverso: qui basta scrivere i campi che cambiano, il resto arriva dalla spedizione. |
| **Pagamento** | Dati della carta del profilo attivo. Disattivato di default. |
| **Sito** | Regole manuali per il sito aperto, selettore del pulsante "aggiungi al carrello", indirizzi di carrello e checkout, la prova del pilota, l'analisi dei campi e lo stato del captcha — tutte senza toccare niente. |
| **Opzioni** | Sovrascrittura, campo civico separato, evidenziazione, compilazione automatica del checkout, dove andare dopo l'aggiunta, attesa prima di cambiare pagina, stato reale del pilota, accesso agli iframe. |

## Come riconosce i campi

Per ogni campo visibile della pagina l'estensione mette insieme cinque segnali
e assegna un punteggio a ciascuna delle 22 chiavi conosciute (nome, cognome,
email, via, civico, CAP, provincia, numero carta, scadenza...):

| Segnale | Punti | Esempio |
| --- | --- | --- |
| attributo `autocomplete` | 100 | `autocomplete="shipping postal-code"` |
| `name`, `id`, `data-testid`, `formcontrolname` | 62 | `name="billing_postcode"` |
| `placeholder`, `aria-label`, `title` | 48 | `placeholder="Postal code"` |
| testo della `<label>` | 46 | `<label>CAP</label>` |
| classi del contenitore | 20 | `class="field--zip"` |

Vince la chiave col punteggio più alto sopra la soglia di 40. Poi:

- **spedizione o fatturazione** si decidono risalendo gli antenati del campo,
  cercando `billing`/`fattur`/`invoice` oppure `shipping`/`spedizion`/`consegna`;
- ogni chiave si compila **una volta sola per sezione**, così un secondo blocco
  identico più in basso nella pagina non viene sovrascritto;
- le `<select>` si risolvono provando più alternative: `IT`, `Italia`, `Italy`
  per il paese, sigla e nome esteso per tutte le 107 province italiane, mese
  come `9` o `09`, anno come `29` o `2029`;
- la scadenza si adatta al formato: campo unico `MM/AA`, oppure mese e anno
  separati, leggendo il segnaposto per capire se vuole due o quattro cifre;
- il civico si attacca alla via, a meno che tu non spunti "campo civico
  separato" nelle opzioni.

I valori si scrivono passando dal setter nativo di `HTMLInputElement` e
sparando la sequenza completa di eventi (`pointerdown`, `focus`, `input`,
`change`, `keyup`, `blur`): è quello che serve perché React, Vue e Angular si
accorgano della modifica invece di riscrivere il campo vuoto al primo clic.

### Cosa non tocca mai

Ricerca, codici sconto, quantità, newsletter, note, captcha, OTP e **qualsiasi
campo password**, anche se il resto combacia. Non preme nessun pulsante.

## La via veloce su Shopify

Prima di leggere la pagina, il pilota prova la scorciatoia. Shopify espone gli
stessi endpoint che il negozio usa da sé:

    GET  /products/<handle>.js   varianti, taglie, disponibilità
    POST /cart/add.js            aggiunta al carrello

Due richieste e il carrello è pieno: niente attesa del rendering, niente
pulsante da aspettare, niente selettore di taglie da interpretare. Sono
esattamente le richieste che partono quando premi "aggiungi al carrello" —
non si aggira nulla, si salta solo il giro dell'interfaccia.

La scelta della variante usa **gli stessi alias delle taglie** del resto:
`M` trova *Medium*, `XL` trova *XLarge*, `42,5` trova `42.5`. Le varianti con
`available: false` vengono saltate, anche quando sono la taglia che hai chiesto.

**Se qualcosa non torna, si torna alla via lenta.** Non è Shopify, l'endpoint
risponde HTML (capita: Supreme chiude `products.json`), il carrello rifiuta con
un 422 perché la taglia è finita nel frattempo: in tutti questi casi riparte il
riconoscimento dal DOM, che continua a funzionare come prima. La scorciatoia è
un'ottimizzazione, non una dipendenza.

Si spegne dalle Opzioni, *"Su Shopify usa le richieste dirette"*.

## Come trova il pulsante e la taglia

Tutto il riconoscimento sta in `cartcore.js`, usato sia dal pilota sia dalla
diagnostica del popup, così quello che vedi nella prova è esattamente quello
che farà.

**Il pulsante** lo cerca fra `button`, `input[type=submit]` e gli elementi con
`role="button"`: deve dire "aggiungi al carrello" (o al sacchetto, al cestino,
*add to cart*, *add to bag*, *in den Warenkorb*, *ajouter au panier*), oppure
avere `add-to-cart` nelle classi o nel `data-testid`, oppure stare dentro un
`form` che punta a `/cart/add`. Il testo può escludere un pulsante — preferiti,
"acquista ora", checkout, PayPal, "avvisami", "esaurito" — ma **gli attributi
non escludono mai**: su Supreme il pulsante giusto si chiama `name="remove"`, e
una regola che guardasse il nome lo butterebbe via.

Accetta anche i pulsanti **disabilitati**, perché parecchi negozi li sbloccano
solo dopo la scelta della taglia: prima sceglie la taglia, poi aspetta fino a
due secondi che il pulsante si accenda, e solo allora clicca.

**La taglia** la cerca prima fra le `<select>`, poi fra i pulsanti e le
etichette corte (la classica griglia dei negozi di scarpe). Una `<select>` vale
come selettore di taglie se lo dice il nome — `size`, `taglia`, `misura` — *o*
se sono le voci stesse a sembrare taglie: serve per i negozi che non etichettano
niente.

Il confronto passa da una forma canonica, così `M` trova **Medium**, `XL` trova
**XLarge**, `42,5` trova `42.5` e `EU 42` trova `42`:

| Scrivi | Trova anche |
| --- | --- |
| `S` `M` `L` | Small, Medium, Large |
| `XL` `XXL` | XLarge, X-Large, 2XL |
| `42.5` | `42,5`, `EU 42.5` |
| `OS` | One Size, Taglia unica |

Salta tutto ciò che è disabilitato o marcato esaurito, *sold out*, *non
disponibile*, barrato o sbiadito.

**Se lasci vuoto il campo taglia**, prende la prima disponibile invece di
fermarsi; se il prodotto non ha taglie, aggiunge e basta. Se invece la taglia
l'hai scritta e non c'è, si ferma e ti dice quali ci sono — non ripiega su una
taglia che non hai chiesto.

**Dove va dopo** lo decidi nelle Opzioni: di default il **checkout**, in
alternativa il carrello. L'indirizzo lo prende da quello scritto nella scheda
Sito; se non c'è, segue il primo collegamento utile della pagina; in ultima
istanza prova `/checkout` (o `/cart`) sul dominio corrente, che è quello giusto
su Shopify — Supreme compreso, dove in pagina non c'è nessun link al carrello.

Il riconoscimento delle pagine di cassa guarda ai segmenti dell'indirizzo, al
plurale compreso: su Shopify il checkout vero è `/checkouts/cn/<token>`, non
`/checkout`, ed è il motivo per cui prima la compilazione non partiva mai.

### Se non parte

Nell'ordine, sono le tre cose che vanno storte più spesso:

1. **L'estensione non è stata ricaricata** dopo una modifica ai file: la
   registrazione dello script sopravvive ai riavvii di Chrome, quindi una
   versione vecchia resta appesa. Premi Ricarica in `chrome://extensions/`.
2. **Guarda la riga di stato** in fondo alle Opzioni: dice cosa risulta
   installato davvero, non cosa crede il popup. In condizioni normali si
   ripara da sola; *Ricontrolla e riattiva il pilota* è lì solo come ultima
   spiaggia.
3. **Il negozio è fuori dall'ordinario.** Apri *Prova il pilota su questa
   pagina* nella scheda Sito: se non trova il pulsante o le taglie, lì sotto si
   danno il selettore CSS e gli indirizzi giusti.

### Provare prima di fidarsi

Nella scheda **Sito**, *Prova il pilota su questa pagina* dice cosa vede senza
toccare niente: quale pulsante ha trovato e se è attivo, quali taglie ci sono,
su quale indirizzo aprirebbe il carrello. È il primo posto dove guardare quando
un negozio non risponde come dovrebbe. Se serve, lì sotto si mette un selettore
CSS su misura e l'indirizzo esatto del carrello.

### Il captcha di questa pagina

In fondo alla scheda **Sito** c'è il riquadro **Captcha**: dice che captcha
c'è e a che punto è. Serve perché il token **scade** — due minuti su reCAPTCHA
e hCaptcha, cinque su Turnstile: se il drop ti fa aspettare, quando arrivi a
mandare l'ordine la verifica che avevi fatto è già morta, e il negozio te la
ributta in faccia a carrello pieno. Qui lo vedi prima.

Riconosce **tutti i captcha che si incontrano davvero**, e su tre li sa anche
rifare:

| Captcha | Versioni | Rifacibile da qui |
| --- | --- | --- |
| **reCAPTCHA** | v2 a casella, v2 invisibile, v3 a punteggio, Enterprise | sì |
| **hCaptcha** | casella, invisibile | sì |
| **Cloudflare Turnstile** | gestito, solo se serve, su richiesta | sì |
| Arkose Labs / FunCaptcha | — | no, API chiusa |
| GeeTest, AWS WAF, Friendly Captcha, MTCaptcha | — | no, API chiusa |
| Captcha a immagine fatto in casa | — | no, non c'è nessuna API |

Quelli dell'ultima parte vengono comunque **riconosciuti e segnalati**: sapere
che c'è un Arkose in pagina spiega perché il checkout non va avanti, anche se
da qui non si può fare niente.

Per ogni captcha trovato il riquadro mostra versione, site key, quanti widget
ci sono e se sono già disegnati, lo stato del token (valido, scaduto, non
ancora risolto), i secondi che restano — in rosso sotto i venti — e il conto
di quanti token sono stati emessi, scaduti e rifatti. Se in pagina ce n'è più
di uno, ognuno ha il suo blocco e compare una tendina per scegliere quale
rifare.

*Rifai la verifica* fa la cosa giusta per ciascuno:

- **reCAPTCHA v2 a casella** e **hCaptcha a casella** — `reset()`, e la spunta
  la rimetti tu. È l'unico punto in cui serve una persona, e l'estensione non
  prova ad aggirarlo.
- **le versioni invisibili** — `reset()` più `execute()`: non c'è niente da
  spuntare, quindi il token nuovo arriva da sé.
- **reCAPTCHA v3** — `execute()` e il token nuovo finisce nello stesso campo
  dove lo mette il sito. La v3 non mostra mai una sfida: il punteggio lo dà
  Google.
- **Turnstile** — `reset()`, e in modalità gestita riparte da solo.

*Tieni d'occhio la scadenza* ricontrolla ogni secondo finché il popup resta
aperto, così il conto alla rovescia si muove davvero.

Il riconoscimento sta in `captcha.js`, che gira **nel mondo MAIN** della
pagina: `grecaptcha`, `hcaptcha` e `turnstile` vivono lì, e dal mondo isolato
degli script di estensione non si vedrebbero. Ogni fornitore dichiara come
riconoscersi, dove tiene il token, quanto vale e come si rifà — aggiungerne
uno è una voce in più nell'elenco `FORNITORI`.

Trova il widget in tutti e due i modi in cui i siti lo montano: quello
implicito, con `data-sitekey` sul contenitore, e quello esplicito via
`render()` su un div qualunque, dove la chiave va pescata dall'indirizzo
dell'iframe. Con hCaptcha esplicito la chiave non è scritta da nessuna parte:
lì la riga *Site key* resta vuota, e va bene così.

> Il token lo emette il fornitore e lo valuta il fornitore. L'estensione non
> risolve captcha e non ci prova: quello che automatizza è accorgersi che il
> token è scaduto e rifare il giro.

## Quando un campo non viene riconosciuto

Scheda **Sito** → *Analizza la pagina senza compilarla*: bordi blu sui campi
riconosciuti e l'elenco di cosa ci scriverebbe. Se ne manca uno, prendi il suo
selettore CSS (tasto destro → Ispeziona → Copia → Copia selettore), incollalo,
scegli il dato dal menu e premi `+`. La regola vale per quell'host e per i suoi
sottodomini, e viene applicata prima del riconoscimento automatico.

## I tuoi dati

Restano nel profilo Chrome di questo computer, in `chrome.storage`. Non c'è
nessun server: l'estensione non ha permessi di rete e non manda niente da
nessuna parte.

I dati della carta seguono una regola diversa dal resto: **di default stanno
solo in memoria di sessione e spariscono quando chiudi Chrome**. La spunta
"Ricorda la carta su questo computer" li sposta su disco, in chiaro — come
qualsiasi dato di estensione, quindi leggibili da chi ha accesso al tuo profilo
Chrome. La scelta vale per tutte le carte insieme e le sposta subito da una
parte all'altra. Il pulsante *Cancella i dati della carta* rimuove da entrambi
i posti quella del profilo attivo; eliminare un profilo cancella anche la sua.

Da spenta il permesso è `activeTab`: legge la pagina solo nell'istante in cui
premi il collegamento o la scorciatoia, e solo quella scheda. Da accesa serve
l'accesso ai siti, perché deve agire su pagine che apri normalmente: è per
questo che l'attivazione lo chiede. Il pezzo che gira sulle pagine
(`autopilot.js`) viene **registrato quando accendi e cancellato quando
spegni** — a interruttore spento non c'è codice dell'estensione in esecuzione
da nessuna parte. Lo stesso permesso serve anche a compilare i campi dentro
agli iframe.

## Limiti noti

- **Campi carta dentro iframe di terze parti** (Stripe, Adyen, PayPal, il
  checkout ospitato di Shopify): senza il permesso sugli iframe non li vede, e
  alcuni provider bloccano comunque la scrittura dall'esterno. Il resto del
  form si compila lo stesso.
- **Menu a tendina finti** costruiti con `<div>` invece che con `<select>`
  (react-select e simili) non sono gestiti: vanno scelti a mano.
- **Checkout a più passi**: compila quello che c'è a schermo. Passa allo step
  successivo e premi di nuovo.
- Campi già pieni non vengono toccati, salvo attivare la sovrascrittura.
- **Selettori di taglia disegnati a mano** (griglie fatte di `div` senza testo,
  o dentro uno shadow DOM chiuso) non vengono visti: la taglia la scegli tu e
  poi aggiungi tu.
- **Pagine che montano tutto in ritardo**: aspetta il pulsante per sei secondi,
  poi lascia perdere. Se il negozio è più lento, ricarica.
- L'attesa fra il clic e l'apertura del carrello è a tempo fisso (1,5 secondi
  di default, si cambia nelle Opzioni): su una connessione lenta conviene
  alzarla, altrimenti il carrello si apre prima che l'aggiunta sia arrivata.

## Struttura

```
manifest.json      permessi e punti d'ingresso (Manifest V3)
filler.js          il motore dei campi: riconoscimento e scrittura
cartcore.js        riconoscimento di pulsante, taglie e carrello (condiviso)
captcha.js         riconoscimento dei captcha e rinnovo del token (mondo MAIN)
autopilot.js       la sequenza: taglia, aggiunta al carrello, apertura carrello
runner.js          profili salvati, carte e avvio dell'iniezione (condiviso)
background.js      service worker: interruttore, scorciatoia, badge
popup.html/css/js  interfaccia
test/              banco di prova, vedi sotto
```

## Prove

`test/checkout-demo.html` è un checkout finto con le insidie tipiche: sezione
spedizione e fatturazione, select di provincia e paese, scadenza `MM/AA` e
campi trappola (ricerca, coupon, quantità, password, note) che devono restare
vuoti.

`test/product-demo.html` è una scheda prodotto finta con la griglia delle
taglie (una esaurita), il pulsante buono e due trappole accanto ("Aggiungi ai
preferiti", "Acquista ora"). Registra in `window.__log` che cosa è stato
cliccato, così si vede subito se ha sbagliato bersaglio. Senza parametri prova
il ripiego sulla prima taglia libera; con `?size=46` la taglia mancante, con
`?nosizes` il prodotto senza taglie, con `?many` il caso "più prodotti in
pagina" — quest'ultimo va aperto come `listing-demo.html`, perché un indirizzo
che contiene "product" viene creduto sulla parola.

`test/supreme-like.html` ricostruisce la scheda prodotto di `eu.supreme.com`
com'è davvero: Shopify con styled-components, nessun `<form>`, nessun link al
carrello, classi illeggibili, taglie scritte `Small / Medium / XLarge` con
valori che sono id di variante, e il pulsante "add to cart" che si chiama
`name="remove"`. `?size=M`, `?locked` (pulsante che si sblocca solo dopo la
taglia) e `?soldout` coprono i tre casi che contano.

`test/spa-checkout.html` è un negozio a pagina singola: l'indirizzo cambia con
`pushState` e le prime due richieste di compilazione non trovano campi. Serve a
verificare che il pilota si accorga del cambio di pagina e che insista.

`test/popup-preview.html` apre il popup fuori dall'estensione, con le API di
Chrome simulate, per lavorare sull'interfaccia; `window.__grant = false`
simula il permesso negato.

`test/captcha-demo.html` è un checkout con un captcha vero accanto. Serve a due
cose: verificare che la compilazione **non tocchi il captcha** (né il token, né
il campo "codice di verifica" vecchio stile), e seguire il **ciclo di vita del
token** — emesso, valido per due minuti, scaduto, rifatto.

Il selettore in alto copre le due versioni che si incontrano davvero:

| Versione | Cosa fa | Rinnovo alla scadenza |
| --- | --- | --- |
| **v2 a casella** | il widget "Non sono un robot" | `grecaptcha.reset()` riporta la casella vuota: **la spunta la rimette una persona** |
| **v2 invisibile** | nessuna interazione, token su richiesta | `grecaptcha.execute()`, senza interazione |
| **v3** | punteggio, nessun widget | `grecaptcha.execute()`, senza interazione |

Il **motore** sceglie fra reCAPTCHA vero (`https://www.google.com`) e una
simulazione locale che riproduce lo stesso ciclo senza rete — utile per far
girare i test offline, e obbligatoria per la v3, per cui Google non pubblica
una chiave di prova. Per la v2 a casella la chiave di test ufficiale è già
dentro. La tua chiave si incolla nel campo *Site key*.

I due pulsanti dei test:

- **Esegui il test** — dieci controlli: il token non viene sovrascritto, nessun
  campo del captcha finisce fra quelli compilati, le trappole (coupon,
  quantità, password, codice di verifica) restano vuote, i sei campi di
  spedizione vengono compilati, il widget sopravvive alla compilazione.
- **Test del ciclo di scadenza** — fa scadere il token, verifica che la
  scadenza venga rilevata e che *Rifai la verifica* riporti le cose a posto:
  token nuovo senza interazione in v3 e v2 invisibile, widget da spuntare in v2
  a casella.

*Fai scadere adesso* anticipa i due minuti; *rinnova da solo alla scadenza*
riparte da sé appena il token muore — con la v2 a casella si ferma comunque
sulla spunta, che è l'unico punto in cui serve una persona.

Parametri dell'indirizzo: `?v=2` (default), `?v=2i`, `?v=3`; `?mock=1` forza il
motore simulato e `?mock=0` quello reale; `?key=...` la tua site key. Da
console e da un driver esterno c'è `window.__captcha`: `stato()`, `scadi()`,
`rinnova()`, `test()`, `testScadenza()`.

> Il banco non risolve il captcha e non prova a farlo: la verifica resta un
> gesto di chi sta davanti allo schermo. Quello che automatizza è il contorno —
> accorgersi che il token è scaduto e rifare il giro.

`test/captcha-tutti.html` monta **le tre librerie insieme** nella stessa
pagina, con le chiavi di test ufficiali di ciascuna: reCAPTCHA v2 in modo
esplicito (`grecaptcha.render`), hCaptcha e Turnstile in modo implicito
(`data-sitekey` sul contenitore). Copre perciò tutti e due i modi in cui i
siti li montano. Il pulsante *Leggi con captcha.js* carica lo stesso file che
l'estensione inietta e mostra cosa ha riconosciuto: fornitore, versione, site
key e stato del token. È il posto dove provare il riquadro **Captcha** della
scheda Sito senza andare a cercarsi un negozio che ne monti uno.

Le chiavi di test dei tre fornitori passano sempre e non proteggono niente:
`6LeIxAcT...` per reCAPTCHA v2, `10000000-ffff-ffff-ffff-000000000001` per
hCaptcha, `1x00000000000000000000AA` per Turnstile.

```bash
python -m http.server 8777
```

Poi apri `http://localhost:8777/test/checkout-demo.html` e, dalla console:

```js
autofillPage({ mode: 'fill', options: { fillCard: true }, overrides: [],
  data: { shipping: { firstName: 'Giacomo', lastName: 'Rossi', /* ... */ },
          billing: { enabled: false }, card: { /* ... */ } } })
```

Il file va servito via HTTP, non aperto da disco: `file://` blocca l'import del
modulo.
