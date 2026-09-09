# Restock Monitor

Monitor di disponibilità per store online. Interroga endpoint **pubblici** a intervalli
regolari e ti avvisa nel momento in cui un articolo torna disponibile — su console,
con un toast di Windows, su Telegram o su Discord.

Il checkout resta tuo: il monitor non aggiunge al carrello, non compila form, non invia
ordini. Ti dà il vantaggio che conta davvero in un drop FCFS — sapere per primo che il
prodotto è live, con il link diretto alla variante giusta.

---

## Installazione

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

Lo script verifica Python (lo installa con winget se manca), crea l'ambiente virtuale
in `.venv`, installa le dipendenze e genera `config.yaml` dal template.

## Icona sul desktop

```powershell
powershell -ExecutionPolicy Bypass -File crea-icona.ps1
```

Crea il collegamento **Restock Monitor** sul desktop: doppio clic e il programma parte,
senza console nera dietro. Per toglierlo, stesso comando con `-Rimuovi`.

L'icona (`restock.ico`) viene generata da [makeicon.py](makeicon.py) in cinque misure, da
256 a 16 pixel, senza librerie grafiche esterne: il disegno viene fatto ad alta risoluzione
e ridotto per media dei blocchi, che è ciò che gli dà i bordi puliti anche piccolissima.
Lo stesso codice, in [imaging.py](restock/imaging.py), disegna i segni di spunta
dell'interfaccia.

## Farlo girare sempre

Un programma su un computer spento non funziona: non c'è configurazione che lo permetta.
Le vie praticabili sono due, e coprono casi diversi.

### Il PC è acceso, ma non voglio aprire la finestra

```powershell
powershell -ExecutionPolicy Bypass -File avvio-automatico.ps1
```

Registra un'operazione pianificata di Windows che avvia il monitor **un minuto dopo ogni
accesso**, senza finestra. Se si interrompe viene riavviato fino a 5 volte a distanza di due
minuti. Non serve essere amministratore.

```powershell
powershell -ExecutionPolicy Bypass -File avvio-automatico.ps1 -Stato
powershell -ExecutionPolicy Bypass -File avvio-automatico.ps1 -Rimuovi
```

Il registro finisce in `monitor.log`, con rotazione a 1 MB per non crescere all'infinito.

Con l'avvio automatico attivo **non premere Avvia nella finestra**: il monitor gira già. Se
lo fai, viene rifiutato con un messaggio invece di partire due volte — c'è un lucchetto di
sistema che garantisce una sola istanza per configurazione, e regge anche se un processo
muore male, perché il blocco lo rilascia il sistema operativo.

### Il PC è spento

Serve una macchina che resti accesa: un Raspberry Pi, un NAS, un piccolo server. Il monitor
è Python puro con tre dipendenze e gira senza interfaccia, quindi ci sta ovunque; le
notifiche arrivano su Telegram, che raggiunge il telefono da qualsiasi parte.

In [deploy/restock-monitor.service](deploy/restock-monitor.service) c'è l'unità systemd
pronta, con le istruzioni passo passo. Un Raspberry Pi consuma circa 3 W: acceso tutto
l'anno costa sui 5 euro.

Sulla macchina remota conviene lasciare attivo **solo Telegram**: le notifiche desktop non
avrebbero nessuno schermo davanti.

## Uso — interfaccia grafica

```powershell
.\gui.ps1
```

Equivalente al doppio clic sull'icona. Niente YAML da scrivere a mano, niente riga di
comando.

La finestra è divisa come le impostazioni di macOS: barra laterale a sinistra con le tre
sezioni e l'indicatore di stato in fondo, contenuti a destra dentro riquadri bianchi.

- **Target** — la tabella con lo stato aggiornato dal vivo: attivo, tipo, intervallo,
  quanti articoli letti, quanti disponibili, ora dell'ultimo controllo. Sopra l'elenco i
  comandi per aggiungere, sotto quelli che agiscono su ciò che è selezionato.
- **Avvisi** — ogni restock e ogni prodotto nuovo, con doppio clic per aprire la pagina.
  Il numero accanto alla voce nella barra laterale dice quanti ne sono arrivati.
- **Registro** — **una scheda per ogni target**, più una "Generale" per ciò che non
  appartiene a nessuno (avvio, salvataggi, pause di un intero host). Selezionando un target
  nell'elenco si apre il suo registro, senza le righe degli altri mescolate dentro.

Il tema è in [theme.py](restock/theme.py): palette dei colori di sistema di macOS, Segoe UI
Variable (il carattere di Windows 11, molto più vicino a SF Pro del vecchio Segoe UI), barre
di scorrimento che compaiono solo quando servono, e i segni di spunta disegnati come
immagini — perché il tema `clam` di Tk li disegnerebbe come una **X**, ed è il dettaglio che
più di tutti tradisce l'origine dell'interfaccia.

I pulsanti coprono l'intero flusso:

- **Monitora un sito** — analizza un indirizzo e crea il target adatto. Vedi sotto.
- **Siti predefiniti** — configurazioni già pronte e verificate per Travis Scott, Nike
  SNKRS, Nike.com e GameLife. Vedi sotto.
- **Aggiungi / Modifica / Duplica / Rimuovi** — un modulo guidato che cambia in base al
  tipo di target scelto, con la spiegazione di ogni campo. Il filtro sulle taglie si
  scrive come `42, 42.5, 43`.
- **Prova adesso** — interroga il target selezionato una volta sola e mostra cosa ha
  letto. Serve a capire se URL e marcatori sono giusti *prima* di lasciarlo girare.
- **Prova notifiche** — manda un avviso finto su tutti i canali attivi.
- **Impostazioni** — User-Agent, `robots.txt`, intervallo predefinito, e le credenziali di
  Telegram e Discord.
- **Attiva / Disattiva**, **Solo questo**, **Attiva tutti** — accendono e spengono i
  singoli target. Vedi sotto.
- **Avvia / Ferma** — durante il monitoraggio i pulsanti di modifica si disattivano, così
  non si cambia la configurazione sotto i piedi al monitor in esecuzione.

Ogni salvataggio viene prima validato su un file temporaneo: una configurazione non valida
non arriva mai a sovrascrivere quella buona, e l'errore ti viene spiegato a schermo.

## Monitorare un sito intero

Il pulsante **Monitora un sito** è la via principale. Scegli cosa vuoi seguire —

- **Tutto un sito**, per essere avvisato di qualunque restock su qualsiasi prodotto
- **Un solo prodotto**, quando ti interessa quello e basta

— incolli l'indirizzo e premi **Analizza**. Il monitor va a vedere di persona: legge
`robots.txt`, prova l'elenco prodotti in blocco, deduce come sono fatti i link dalla pagina
stessa, apre una scheda campione e cerca il campo di disponibilità. Poi ti dice **cosa
riesce a fare su quel sito**, e propone una configurazione già pronta.

Le tre risposte possibili sono esplicite:

| Esito | Significa |
|---|---|
| **completa** | Restock e prodotti nuovi, su tutto il catalogo |
| **parziale** | Solo i prodotti nuovi: la disponibilità non è leggibile |
| **nessuna** | Il sito risponde solo a un browser vero, non c'è niente da leggere |

Non c'è nessuna euristica che indovini sempre. Su un sito con molta navigazione la famiglia
di link più numerosa può essere il menu, non il catalogo: per questo l'analisi **mostra
tutte le famiglie trovate** con il numero di link di ciascuna e se lo stock è leggibile, e
ti lascia scegliere dal menu a tendina. È un'informazione, non un indovinello.

Il singolo prodotto resta pieno supporto: su uno store Shopify l'analisi propone il tipo che
legge la disponibilità **taglia per taglia**, che è più preciso del monitoraggio di sito.

### Cataloghi su più pagine

Un negozio più grande di una risposta va sfogliato, altrimenti "tutto il sito" vorrebbe dire
"la prima pagina":

```yaml
options:
  pages: 10          # sfoglia fino a 10 pagine
  page_param: page   # nome del parametro, se il sito ne usa un altro
```

Il monitor si ferma da solo alla prima pagina vuota, quindi il valore è un tetto, non un
costo fisso.

## Attivare un target alla volta

Non serve far girare tutto insieme. Ogni target ha un interruttore, e la colonna **Attivo**
nella tabella dice a colpo d'occhio chi è acceso.

- **Attiva / Disattiva** — accende o spegne quello selezionato. Un target spento resta in
  elenco con la sua configurazione, semplicemente non viene interrogato.
- **Solo questo** — spegne tutti gli altri e lascia acceso il selezionato. È la via rapida
  quando ti interessa un drop specifico e non vuoi rumore intorno.
- **Attiva tutti** — rimette tutto in funzione.

Lo stato è salvato in `config.yaml` (`enabled: true/false`), quindi sopravvive alla
chiusura. La barra in basso mostra sempre quanti target sono attivi sul totale, e **Avvia**
si rifiuta di partire se sono tutti spenti invece di girare a vuoto.

Da riga di comando vale lo stesso: `--once` mostra i target spenti come `[SPENTO]` e non li
interroga.

## Siti predefiniti

Il pulsante **Siti predefiniti** apre un elenco di configurazioni pronte. Ognuna è stata
ricavata interrogando davvero il sito — `robots.txt`, accessibilità, marcatori — non
scritta a intuito. La scheda di ogni preset dichiara anche **cosa non fa**, perché su
questi siti i limiti contano più delle funzionalità.

| Preset | Cosa segnala |
|---|---|
| **Travis Scott — nuovi prodotti** | Prodotto nuovo, con stato, + restock su tutto lo store |
| **Travis Scott — disponibilità prodotto** | Un prodotto specifico torna disponibile |
| **Nike SNKRS IT — appena disponibili** | Lancio acquistabile, con stato accertato per taglia |
| **Nike SNKRS IT — nuovi lanci** | Nike mette in calendario un lancio nuovo |
| **Nike.com IT — novità** | Compare un prodotto nuovo sul sito Nike normale |
| **Nike.com IT — saldi** | Un prodotto entra in sconto |
| **Nike.com IT — categoria a scelta** | Come sopra, su una pagina di catalogo che scegli tu |
| **GameLife — nuovi prodotti** | GameLife pubblica un prodotto che corrisponde al filtro |

Cosa ho trovato sui quattro siti, perché spiega le scelte fatte:

**Travis Scott** è Shopify, ma Cloudflare risponde `403` agli endpoint `products.json` e
`.js` — quelli che normalmente userebbe un monitor. Le pagine HTML invece rispondono `200`,
e Shopify vi incorpora la disponibilità. Il preset legge la collezione per scoprire i
prodotti e apre le schede per accertarne lo stock, quindi copre l'intero store: nuovi
prodotti *e* restock di quelli già presenti. Marcatore verificato su sei prodotti reali:
sulla pagina esaurita `"available":true` compare 0 volte e `false` 24; sulle pagine
disponibili è l'esatto contrario. La rilevazione è a livello di pagina, non di singola
taglia.

**Nike SNKRS**: `robots.txt` consente `/it/launch`, e le pagine rispondono `200`. Sulle
pagine-elenco un marcatore di disponibilità non significherebbe niente — contengono un
misto di `true` e `false` per decine di prodotti insieme — quindi l'elenco serve a rilevare
i **lanci nuovi che compaiono**, e la disponibilità viene accertata aprendo la scheda del
singolo lancio, dove il campo per taglia c'è ed è attendibile: su un lancio provato, 16
taglie disponibili e 8 esaurite.

Sul preset SNKRS c'è un limite che conviene conoscere prima di contarci: in Europa la
maggior parte dei lanci sono **estrazioni**, non vendite a chi arriva prima. Si partecipa
dall'app entro una finestra e si aspetta l'esito. Su quei drop il monitor ti dice quando la
finestra si apre — utile — ma non esiste nessun "arrivare primi" da vincere. Per cambiare
paese basta sostituire `/it/` nell'URL.

**Nike.com** (il sito normale, non SNKRS) è il caso più semplice di tutti: `robots.txt`
consente `/it/w/` e `/it/t/`, e le pagine di catalogo contengono i prodotti direttamente
nell'HTML. Provato su quattro pagine: 33 prodotti in Novità e Saldi, 106 in "uomo scarpe" e
"donna scarpe". Sono le uscite ordinarie, quelle che non passano da SNKRS e non sono
soggette a estrazione — qui chi arriva prima compra davvero.

C'è però un limite netto: sulle **schede prodotto** di nike.com la disponibilità non è
leggibile, perché taglie e stock arrivano via JavaScript e questo strumento non esegue JS.
Ho verificato: `robots.txt` consentirebbe l'accesso e la pagina risponde `200`, ma i campi
di stato semplicemente non ci sono nell'HTML iniziale. Un preset "segui questo prodotto" su
nike.com darebbe risposte inventate, quindi non l'ho incluso. Per il sito Nike il
monitoraggio è a livello di catalogo.

**GameLife** risponde `403` alle richieste automatiche perfino sulla home. L'unica
superficie pubblica accessibile è la sitemap, che il sito serve regolarmente perché è fatta
apposta per essere letta dai programmi. Il preset legge quella: rileva i **prodotti nuovi a
catalogo**, non i restock, perché dalla sitemap la disponibilità non è leggibile. La
sitemap contiene circa 30.000 URL, quindi il filtro è di fatto obbligatorio: il valore
predefinito è `pokemon` (1.297 prodotti) e va cambiato con quello che ti interessa.

Gli intervalli dei preset sono più larghi del solito (60–900 secondi) di proposito: due di
questi siti hanno già mostrato di non gradire il traffico automatico, e insistere è il modo
più rapido per farsi bloccare l'IP proprio durante un drop.

> Verifica effettuata il 07/09/2026. Se un sito cambia impaginazione o politica di accesso
> il preset va ricontrollato: **Prova adesso** te ne fa accorgere subito.

## Uso — riga di comando

```powershell
.\run.ps1 --once
```

Un solo giro su tutti i target, poi esce: serve a verificare che URL e selettori siano
giusti prima di lasciarlo in esecuzione.

```powershell
.\run.ps1 --test-notify
```

Manda una notifica finta su ogni canale abilitato, per controllare token e webhook.

```powershell
.\run.ps1
```

Avvia il monitoraggio continuo. `Ctrl-C` per fermarlo; lo stato viene salvato, quindi
al riavvio non ricevi una raffica di notifiche per ciò che era già disponibile.

Altre opzioni: `-c altra-config.yaml`, `-v` (log di debug), `--reset-state`.

---

## Configurazione

Tutto vive in `config.yaml`, che l'interfaccia grafica legge e riscrive. Se preferisci
modificarlo a mano puoi farlo — parti da `config.example.yaml`, che contiene un esempio
commentato per ciascuno dei cinque tipi di target — ma tieni presente che i commenti che
aggiungi vengono persi al primo salvataggio dalla GUI.

### Tipi di target

| `type` | Quando usarlo | Cosa serve |
|---|---|---|
| `shopify_product` | Un prodotto specifico su uno store Shopify | L'URL normale del prodotto |
| `shopify_collection` | Un'intera collezione, per intercettare anche i drop non annunciati | L'URL della collezione |
| `json` | Il sito espone un'API pubblica | I percorsi puntati dei campi |
| `html` | Nessuna API: si leggono marcatori nel testo della pagina | Le frasi che distinguono disponibile da esaurito |
| `links` | La disponibilità non è leggibile, ma il catalogo sì | Un'espressione regolare che isola le voci dell'elenco |

**Shopify** è il caso più semplice e più affidabile: incolli l'URL del prodotto e il
monitor usa da solo l'endpoint pubblico `.js`, che restituisce la disponibilità di ogni
singola variante (taglia). Per capire se uno store è Shopify, prova ad aprire
`https://ilsito.com/products/qualcosa.js` nel browser: se vedi del JSON, lo è.

**Filtro sulle taglie** — solo quelle che ti interessano:

```yaml
match:
  variants: ["42", "42.5", "43"]
```

**Target HTML** — apri la pagina mentre il prodotto è esaurito, individua una frase
presente solo in quello stato e mettila in `out_of_stock_when`. È il metodo più fragile
(basta un restyling del sito) ma funziona ovunque.

**Target `links`** — ragiona in modo diverso dagli altri tre: non guarda la disponibilità,
guarda **chi c'è nell'elenco**. Ogni voce trovata vale come presente, e l'avviso scatta
quando ne compare una che prima non c'era. È la risposta ai siti che nascondono lo stock ma
pubblicano il catalogo — pagine di lancio, sitemap. Con cataloghi grandi usa `include` per
restringere il campo, altrimenti finiscono sotto osservazione decine di migliaia di voci.

### Riconoscere disponibile da esaurito su un elenco

Un elenco da solo sa che un prodotto è *comparso*, non se è *comprabile*. Il blocco
`detail` colma la differenza: il monitor apre la scheda di ogni prodotto e ne accerta lo
stock.

```yaml
detail:
  in_stock_when: ['\\?"available\\?"\s*:\s*true']
  regex: true
  max_checks: 5          # schede aperte per giro
  recheck_sold_out: true # ricontrolla gli esauriti, per i restock
```

Con questo blocco attivo cambiano cinque cose:

- l'avviso elenca le **taglie disponibili**. Su Telegram diventano **pulsanti**: si preme
  la taglia e si apre il prodotto con quella misura già selezionata, senza leggere né
  incollare indirizzi. Sul toast di Windows le prime quattro taglie sono altrettanti
  pulsanti (il massimo che Windows accetta); su Discord sono link nel testo, perché i
  webhook non hanno pulsanti. L'elenco viene letto dall'array delle varianti della pagina: contando le
  parentesi, non per vicinanza di testo — fra il nome della taglia e la sua disponibilità i
  siti infilano oggetti annidati, e qualsiasi limite di distanza sbaglia su metà delle
  pagine. Se una pagina espone più elenchi con lo stesso nome (capita: il primo è quello
  delle statistiche, senza disponibilità) vengono provati tutti;

- l'avviso porta il **nome vero del prodotto**, letto dalla sua pagina, invece di quello
  ricavato dall'indirizzo. Su alcuni siti la differenza è tutto: su Supreme un prodotto
  vive su `/products/gh-ii_gyou4-fsju`, e da lì non si ricava niente di leggibile —
  aprendo la scheda diventa *Supreme®/Larry Clark Hooded Varsity Jacket*. Il nome viene
  cercato prima nell'`<h1>`, poi in `og:title`, poi nel `<title>`, ripulito dalle code tipo
  "- Shop - NomeSito", e **conservato nello stato**: le schede si riaprono a rotazione, non
  a ogni giro, e senza memoria il nome tornerebbe a essere lo slug;

- l'avviso di prodotto nuovo dice anche lo stato: `[NUOVO] ... [DISPONIBILE]` oppure
  `[ESAURITO]`;
- un prodotto già noto che era esaurito e torna comprabile genera un `[RESTOCK]`;
- senza il blocco, l'avviso non dichiara nessuno stato — perché non lo conosce, e
  inventarlo sarebbe peggio che tacere.

Aprire tutte le schede a ogni giro sarebbe un carico assurdo su un catalogo di cento
prodotti, quindi se ne aprono **poche per giro**: prima le novità, poi le altre a
rotazione. Su un catalogo da 26 prodotti con `max_checks: 5` la copertura completa arriva
in circa cinque giri — misurato, non stimato. Un prodotto mai ancora accertato non viene
spacciato per disponibile: resta senza etichetta finché non lo si è aperto davvero.

Funziona solo dove la scheda prodotto è raggiungibile **e** contiene lo stato nell'HTML. Se
il sito carica le taglie via JavaScript, o risponde `403` alle richieste automatiche, non
c'è marcatore che tenga.

### Notifiche

- **console** — attiva di default
- **desktop** — toast di Windows con pulsante "Apri pagina", più un beep
- **telegram** — vedi la procedura qui sotto
- **discord** — Impostazioni canale → Integrazioni → Webhook → Copia URL

Per un drop, Telegram è il canale migliore: la notifica arriva sul telefono anche se non
sei davanti al PC.

### Collegare Telegram

Servono due valori: il **token del bot** e il tuo **chat ID**. Cinque minuti in tutto.

**1. Crea il bot.** Su Telegram cerca **@BotFather** (quello con la spunta blu) e aprilo.
Manda `/newbot`. Ti chiede due cose: un nome visualizzato (quello che vuoi, es. "Restock")
e uno username che **deve finire per `bot`** (es. `restock_giacomo_bot`; se è già preso te
lo dice e ne chiedi un altro). BotFather risponde con un messaggio che contiene una riga
tipo:

```
8123456789:AAF-abc123DEF456ghi789JKL012mno345PQR
```

Quello è il token. Copialo tutto, compresi i due punti.

**2. Scrivi al tuo bot.** Cerca su Telegram lo username che hai appena scelto, apri la
conversazione e manda un messaggio qualsiasi (va bene `ciao`). **Questo passaggio non è
facoltativo**: finché non gli scrivi per primo, Telegram vieta al bot di scriverti, ed è
l'errore più comune quando "non arriva niente".

**3. Metti il token nel programma.** Nella GUI: **Impostazioni** → riquadro Telegram →
incolla il token → **Salva**.

**4. Lascia fare il resto allo script.**

```powershell
.venv\Scripts\python.exe telegramsetup.py
```

Verifica il token, resta in ascolto finché non scrivi al bot, ricava il chat ID, lo salva,
attiva il canale e ti manda subito una notifica di prova. Con `--attesa 600` allunga la
finestra di ascolto.

Il chat ID non è ricavabile in nessun altro modo: è l'API del bot a comunicarlo, e solo
dopo che gli hai scritto almeno una volta. Non è il tuo username e non è il link `t.me`.

Se preferisci a mano, apri `https://api.telegram.org/bot<TOKEN>/getUpdates` nel browser e
cerca `"chat":{"id":123456789,`. Una lista vuota (`"result":[]`) significa che il passaggio
2 non è andato a buon fine.

**5. Attiva il canale sui target che ti interessano.** Selezionane uno → **Modifica** →
spunta `Telegram` fra i canali di notifica. Va fatto per ogni target: così puoi ricevere sul
telefono solo i drop che contano e lasciare gli altri sul PC.

Se una notifica non arriva, il registro nella scheda *Generale* dice cosa non va in
italiano — token non valido, chat non trovata, bot bloccato, permessi mancanti.

Il token dà pieno controllo del bot: sta in chiaro in `config.yaml`, quindi non condividere
quel file. Se ti sfugge, `/revoke` su BotFather lo invalida e te ne dà uno nuovo.

Ogni target può scegliere i propri canali:

```yaml
notify: [console, desktop, telegram]
```

---

## Come si comporta con i siti

Il monitor è progettato per essere un client onesto, non per nascondersi:

- **Rispetta `robots.txt`.** Se un URL è vietato, quel target viene disattivato con un
  messaggio esplicito. Disattivabile con `respect_robots: false`, ma il default è `true`.
- **Si identifica** con uno `User-Agent` dichiarato. Mettici un contatto reale: se il tuo
  traffico dà fastidio, il sito ha modo di dirtelo invece di limitarsi a bloccarti.
- **Intervallo minimo di 3 secondi** per target, non aggirabile dalla configurazione, più
  una spaziatura di 1 secondo fra richieste consecutive allo stesso host — così venti
  target sullo stesso store non si trasformano in venti richieste simultanee.
- **Jitter** sull'intervallo, per non produrre un pattern perfettamente regolare.
- **Onora `429` e `Retry-After`.** Se il sito chiede di rallentare, il monitor mette in
  pausa l'intero host e riprende dopo. Sugli errori 5xx applica backoff esponenziale
  fino a 5 minuti.

Non c'è rotazione di proxy, spoofing del fingerprint, bypass di captcha o di code di
attesa: sono le tecniche che trasformano un monitor in un bot, e non sono qui.

Un intervallo di 15–30 secondi è il punto giusto per quasi tutti i casi. Scendere sotto i
10 secondi raramente cambia l'esito e aumenta parecchio la probabilità di finire
rate-limitato proprio nel momento del drop.

---

## Struttura

```
restock/
  config.py       caricamento e validazione YAML
  httpclient.py   client HTTP con robots.txt, spaziatura per host, backoff
  adapters.py     risposta HTTP -> lista di Item (i cinque tipi di target)
  state.py        persistenza, dedup, rilevamento delle transizioni
  notify.py       console / desktop / Telegram / Discord
  monitor.py      scheduler asincrono, un task per target
  discover.py     analisi di un sito: capire cosa e monitorabile e come
  presets.py      configurazioni pronte per Travis Scott, SNKRS, Nike.com, GameLife
  theme.py        aspetto in stile macOS: palette, caratteri, indicatori disegnati
  imaging.py      scrittura di PNG in memoria, senza librerie grafiche
  istanza.py      lucchetto di sistema: un solo monitor per configurazione
  gui.py          interfaccia grafica (tkinter), un registro per target
  cli.py          riga di comando
selftest.py       test unitari offline
e2etest.py        prova end-to-end contro un finto store Shopify locale
guitest.py        prova automatica dell'interfaccia grafica
makeicon.py       genera restock.ico senza dipendenze grafiche
crea-icona.ps1    crea il collegamento sul desktop
avvio-automatico.ps1  avvio del monitor a ogni accesso a Windows
deploy/           unita systemd per una macchina sempre accesa
telegramsetup.py  collega Telegram: trova il chat ID e manda una prova
```

La GUI non blocca mai: il monitor gira in un thread separato con il proprio event loop
asyncio e comunica con l'interfaccia solo attraverso una coda, letta dal thread di Tk.
Nessun widget viene toccato dal thread del monitor.

Il rilevamento è basato su **transizioni**: si viene avvisati quando un articolo passa da
esaurito a disponibile, non a ogni giro in cui risulta disponibile. Il primo giro su un
target è silenzioso — fotografa la situazione di partenza.

## Test

```powershell
.venv\Scripts\python.exe selftest.py
```

57 test unitari su parsing degli adapter, filtri, transizioni di stato, persistenza e
validazione della configurazione. Nessuna rete.

```powershell
.venv\Scripts\python.exe e2etest.py
```

Prova end-to-end: avvia un finto store Shopify su `127.0.0.1:8931` e ci fa girare contro
il monitor vero, verificando che il primo giro sia silenzioso, che il restock venga
notificato una volta sola con il link diretto alla variante, che `robots.txt` disattivi i
target vietati, che il filtro sulle taglie funzioni e che un `429` metta l'host in pausa
per il tempo indicato da `Retry-After`. Tutto in locale, nessun sito esterno coinvolto.

```powershell
.venv\Scripts\python.exe guitest.py
```

Apre la finestra vera, ci inietta eventi come se arrivassero dal monitor e verifica
tabelle, avvisi, registro, finestre di dialogo e salvataggio della configurazione. Si
chiude da sola: non serve cliccare nulla.

---

## Limiti

- I siti con protezione anti-bot aggressiva (Akamai, DataDome, Queue-it) possono
  rispondere con una challenge anche a un client onesto. Il monitor non la aggira: logga
  l'errore e continua. Su quei siti, l'unica via è il canale ufficiale del brand.
- I target `html` si rompono quando il sito cambia markup. Se un target smette di
  segnalare, usa **Prova adesso** dalla GUI (o `--once -v` da riga di comando) e
  ricontrolla i marcatori.
- Il monitor rileva la disponibilità, non la garantisce: fra la notifica e il tuo
  checkout il pezzo può sparire.
