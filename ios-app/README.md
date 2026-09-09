# Checkout Autofill per iOS

La stessa cosa dell'estensione Chrome, in una app: profili salvati, taglia,
interruttore, aggiunta al carrello, apertura del checkout e compilazione dei
campi. Lo stesso motore, letteralmente — i file JavaScript sono generati da
`chrome-extension/`, non riscritti.

---

## Il vincolo di iOS, detto subito

**Nessuna app su iOS può iniettare script nelle pagine aperte in Safari.** Non
è una scelta di progetto, è come è fatto il sistema: solo un'estensione di
Safari può farlo, e tu una estensione non la volevi.

Quindi l'app ha un browser suo. Il negozio si naviga nella scheda **Negozio**,
dentro l'app, e lì il pilota fa esattamente quello che fa su Chrome. Aprendo lo
stesso negozio in Safari, l'app non c'entra più niente.

È l'unica differenza rispetto all'estensione. Tutto il resto combacia.

## Come si costruisce

Serve un Mac con Xcode: il progetto non è compilabile su Windows.

```bash
brew install xcodegen
cd ios-app
xcodegen generate
open CheckoutAutofill.xcodeproj
```

Poi in Xcode scegli la tua squadra di firma (Signing & Capabilities) e premi
Play su un iPhone collegato o sul simulatore. Con un account gratuito l'app
resta installata sette giorni, poi va rifirmata.

Senza XcodeGen: crea un progetto *iOS App* vuoto (SwiftUI, interfaccia
SwiftUI), poi trascina dentro la cartella `CheckoutAutofill/` scegliendo
*Create groups*, e verifica che i tre `.js` in `Resources/` finiscano in
**Build Phases → Copy Bundle Resources**. Se mancano, l'app parte ma il pilota
non fa niente.

## Il motore è condiviso, non copiato

```bash
python ios-app/tools/sync-js.py
```

Legge `chrome-extension/cartcore.js` e `chrome-extension/filler.js`, li adatta
alla WKWebView (via i moduli ES, via le API di Chrome) e li scrive in
`CheckoutAutofill/Resources/`. Da rieseguire ogni volta che si tocca
l'estensione, altrimenti le due versioni divergono in silenzio. Lo script si
ferma con un errore se l'adattamento non è pulito.

`bridge.js` invece è scritto a mano: è il gemello iOS di `autopilot.js`, con la
stessa sequenza e gli stessi freni, ma prende lo stato dall'app e compila
chiamando il motore direttamente, senza service worker.

## Com'è fatta

```
CheckoutAutofill/
  Models/
    Models.swift      profili, carta, impostazioni, regole per sito
    Store.swift       stato dell'app, salvataggio, stato per il motore
    Keychain.swift    la carta nel portachiavi di iOS
  Web/
    WebController.swift  la WKWebView, gli script iniettati, i messaggi
    WebView.swift        la WKWebView dentro SwiftUI
  Views/
    App.swift          punto d'ingresso e le tre schede
    BrowserView.swift  browser, interruttore, riquadro degli avvisi
    ProfilesView.swift profili e indirizzi
    PaymentView.swift  carta
    SettingsView.swift opzioni, regole per sito, diagnostica
  Resources/
    cartcore.js  filler.js   generati da sync-js.py
    bridge.js                scritto a mano
```

Gli script girano in un **mondo isolato** della WKWebView
(`WKContentWorld.defaultClient`): vedono il DOM ma non le variabili della
pagina, e — quel che conta — la pagina non vede i tuoi dati. È lo stesso
confine che l'estensione ha su Chrome.

## Cosa cambia rispetto all'estensione

| | Chrome | iOS |
| --- | --- | --- |
| Dove agisce | qualunque scheda del browser | solo dentro l'app |
| Interruttore | registra un content script | accende il pilota nella web view |
| Carta ricordata | su disco, in chiaro | portachiavi di iOS, solo a telefono sbloccato |
| Avvisi | riquadro dentro la pagina | banner nativo in fondo allo schermo |
| Compila adesso | scorciatoia da tastiera | pulsante nella barra |

Il resto è identico: stesso riconoscimento dei campi, stessi alias delle taglie
(`M` trova *Medium*, `XL` trova *XLarge*), stesso ripiego sulla prima taglia
libera quando il campo è vuoto, stessi freni — niente clic su "acquista ora",
su PayPal, sul pulsante d'ordine.

## Cosa è stato provato, e cosa no

Il **motore JavaScript è stato verificato** in un browser vero, con
`test/bridge-demo.html`, che carica gli stessi tre file che finiscono nel
bundle: scelta della taglia in stile Supreme (`M` → Medium), clic sul pulsante
giusto, messaggi verso l'app, compilazione manuale (7 campi su 7), diagnostica,
compilazione automatica sul checkout e ricompilazione tornando sullo stesso
indirizzo.

Il **codice Swift non è stato compilato**: è stato scritto su Windows, dove
Xcode non esiste. È però passato per una rilettura mirata agli errori che il
compilatore darebbe, che ne ha trovati quattro:

- key path su elementi di tupla (`ForEach(elenco, id: \.0)`), che in Swift non
  esistono: gli elenchi di paesi e di chiavi ora sono strutture `Voce`;
- lettura di una proprietà di `self` dentro `Store.init()` prima che tutte le
  proprietà fossero inizializzate;
- quattordici viste dentro un solo `ViewBuilder`, che ne accetta dieci;
- una ternaria fra `.white` e `.primary` passata a un parametro generico, dove
  il compilatore non ha modo di scegliere il tipo.

Restano possibili errori di battitura o di firma delle API: il primo
`xcodegen generate` + build su un Mac è il controllo vero.

Per provare il motore senza un Mac:

```bash
python -m http.server 8779     # dalla radice del repository
```

poi apri `http://localhost:8779/ios-app/test/bridge-demo.html`. I messaggi che
l'app riceverebbe finiscono in `window.__CA_TEST`.

## Prima di usarla sul serio

Vale la stessa avvertenza dell'estensione: aggiungere al carrello in automatico
non è come compilare i propri dati, e parecchi retailer lo vietano nelle
condizioni d'uso. L'app si ferma prima dell'ordine — non preme mai "paga" né
"conferma acquisto" — ma la decisione di accendere l'interruttore resta tua.

## Controlli da Windows

```powershell
powershell -ExecutionPolicy Bypass -File ios-app\tools\check-swift.ps1
```

Analisi sintattica di tutti i sorgenti Swift con `swiftc -parse` (toolchain da
`winget install --id Swift.Toolchain`). Non risolve gli import, quindi gira
anche dove SwiftUI e WebKit non esistono: prende refusi, parentesi sbagliate e
file troncati. Non prende errori di tipo né firme di API sbagliate — per quelli
serve il runner macOS di `.github/workflows/ios-build.yml`.

## Portarla sull'iPhone con TestFlight

Serve l'**Apple Developer Program** (99 $/anno): è quello che sblocca la firma
di distribuzione. TestFlight in sé è gratis. Fatto quello, non serve un Mac in
nessun punto della catena.

**Le quattro chiavi.** Su App Store Connect → *Utenti e accessi* →
*Integrazioni* → *Chiavi App Store Connect*, genera una chiave con ruolo
**Admin**. Non *App Manager*: quel ruolo non può creare certificati e profili
di firma, e l'esportazione muore con *"Cloud signing permission error — No
profiles were found"*. Il ruolo di una chiave non si cambia dopo: va revocata
e rifatta.

Ti dà Issuer ID, Key ID e un file `.p8` scaricabile una volta sola. Il Team ID
sta in *Appartenenza* sul portale sviluppatori.

Vanno caricate come segreti del repository. **Falli tu**: la `.p8` è una chiave
privata di firma e non deve passare per nessun altro.

```bash
gh secret set ASC_KEY_ID --repo <utente>/cloudesole
gh secret set ASC_ISSUER_ID --repo <utente>/cloudesole
gh secret set ASC_TEAM_ID --repo <utente>/cloudesole
gh secret set ASC_KEY_P8 --repo <utente>/cloudesole < AuthKey_XXXXXXXX.p8
```

**Il caricamento** si avvia a mano, perché i minuti macOS non sono infiniti:

```bash
gh workflow run "Carica su TestFlight"
```

Il workflow controlla prima che i segreti ci siano, genera il progetto, compila
in Release e carica. Certificato e profilo di provisioning se li crea Xcode al
volo con `-allowProvisioningUpdates`: non c'è niente da installare a mano.

Il numero di build è il numero della corsa di GitHub, così cresce sempre —
TestFlight rifiuta due caricamenti con lo stesso numero.

**Per te non serve nessuna revisione di Apple.** Come tester *interno* (sei nel
tuo stesso team) la build è disponibile appena finisce l'elaborazione, dieci
minuti circa. La revisione servirebbe solo per i tester esterni.

> Questo workflow non è mai stato eseguito: senza credenziali non è
> verificabile. La prima corsa è anche la prima prova, e qualche aggiustamento
> è probabile.
