import SwiftUI

/// La scheda Negozio. Si apre sull'elenco dei negozi salvati, non su una
/// pagina web: tocchi un riquadro e il sito si apre lì dentro, dove il pilota
/// può agire. Fuori dall'app, in Safari, nessuna app può intervenire.
struct BrowserView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var web: WebController
    @State private var indirizzo = ""
    @FocusState private var scriveIndirizzo: Bool
    @State private var mostraNuovoAccount = false

    var body: some View {
        VStack(spacing: 0) {
            testata
            Divider()

            // Elenco e pagina restano **tutti e due montati**, e si alternano
            // per trasparenza. Toglierli e rimetterli nell'albero delle viste
            // faceva crollare UIKit: il cambio avveniva dentro la gestione del
            // tocco che l'aveva provocato, e i riconoscitori di gesti della
            // WKWebView si ritrovavano a metà strada
            // (-[UIGestureRecognizer _delayTouchesForEvent:], oggetto nullo).
            ZStack(alignment: .bottom) {
                WebView(webView: web.webView)
                    .opacity(web.mostraElenco ? 0 : 1)
                    .allowsHitTesting(!web.mostraElenco)

                ShopsView()
                    .background(Color(.systemBackground))
                    .opacity(web.mostraElenco ? 1 : 0)
                    .allowsHitTesting(web.mostraElenco)

                // Anche l'avviso resta montato. Comparire e sparire mentre
                // il pilota lavora significherebbe cambiare l'albero mentre
                // hai il dito sulla pagina: e' la stessa trappola di prima.
                riquadro
            }

            Divider()
            barraStrumenti
        }
        .onChange(of: web.currentURL) { nuovo in
            if !scriveIndirizzo { indirizzo = nuovo?.absoluteString ?? "" }
        }
        .sheet(isPresented: $mostraNuovoAccount) {
            NuovoAccountView(hostSuggerito: web.host)
                .environmentObject(store)
        }
    }

    // MARK: - Testate

    /// Una testata sola per i due stati: cambia il titolo, ma il campo di
    /// testo resta sempre lo stesso e non lascia mai l'albero delle viste.
    private var testata: some View {
        VStack(alignment: .leading, spacing: 8) {
            if web.mostraElenco {
                Text("Negozi").font(.title2.weight(.bold))
            }
            campoIndirizzo
        }
        .padding(.horizontal, 14)
        .padding(.top, web.mostraElenco ? 10 : 8)
        .padding(.bottom, 8)
        .background(.bar)
    }

    /// Lo stesso campo nei due stati: da qui si può sempre andare altrove,
    /// anche se il negozio non è nell'elenco.
    private var campoIndirizzo: some View {
        HStack(spacing: 8) {
            Image(systemName: web.isLoading ? "arrow.triangle.2.circlepath" : "magnifyingglass")
                .foregroundStyle(.secondary)
                .font(.footnote)
            TextField("Indirizzo o ricerca", text: $indirizzo)
                .textFieldStyle(.plain)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.URL)
                .submitLabel(.go)
                .focused($scriveIndirizzo)
                .onSubmit {
                    web.vai(a: indirizzo)
                    scriveIndirizzo = false
                }
            // Anche questo si spegne invece di sparire: comparirebbe mentre
            // scrivi, cioe' mentre stai toccando la tastiera.
            Button { indirizzo = "" } label: { Image(systemName: "xmark.circle.fill") }
                .foregroundStyle(.secondary)
                .disabled(indirizzo.isEmpty || !scriveIndirizzo)
                .opacity(!indirizzo.isEmpty && scriveIndirizzo ? 1 : 0)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(Color.secondary.opacity(0.12), in: Capsule())
    }

    // MARK: - Barra in fondo

    private var barraStrumenti: some View {
        HStack(spacing: 16) {
            Button { web.mostraElenco = true } label: { Image(systemName: "square.grid.2x2") }
                .disabled(web.mostraElenco)
            Button { web.indietro() } label: { Image(systemName: "chevron.left") }
                .disabled(!web.canGoBack || web.mostraElenco)
            Button { web.avanti() } label: { Image(systemName: "chevron.right") }
                .disabled(!web.canGoForward || web.mostraElenco)
            Button { web.ricarica() } label: { Image(systemName: "arrow.clockwise") }
                .disabled(web.mostraElenco)

            // Serve solo dove c'e' un modulo di accesso, ma non compare e
            // sparisce: si spegne. Aggiungere un pulsante alla barra mentre
            // stai toccando lo schermo cambia l'albero delle viste sotto le
            // dita di UIKit, ed e' cosi' che l'app crollava.
            Button {
                if let voce = store.account(per: web.host) {
                    web.accedi(con: voce, store: store)
                } else {
                    mostraNuovoAccount = true
                }
            } label: {
                Image(systemName: store.account(per: web.host) != nil ? "key.fill" : "key")
            }
            .disabled(!web.moduloAccesso || web.mostraElenco)
            .opacity(web.moduloAccesso && !web.mostraElenco ? 1 : 0)

            Spacer()

            Button { web.compilaAdesso() } label: {
                Label("Compila", systemImage: "square.and.pencil").labelStyle(.iconOnly)
            }
            .disabled(web.mostraElenco)

            Button {
                store.armed.toggle()
                web.mostra(store.armed
                           ? "Pilota acceso: apri la scheda prodotto."
                           : "Pilota spento: non tocca più nessuna pagina.",
                           tono: "ok")
            } label: {
                Label(store.armed ? "Attivo" : "Attiva",
                      systemImage: store.armed ? "bolt.fill" : "bolt.slash")
                    .font(.callout.weight(.semibold))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 7)
                    .background(store.armed ? Color.green : Color.secondary.opacity(0.18),
                                in: Capsule())
                    .foregroundStyle(store.armed ? Color.white : Color.primary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.bar)
    }

    // MARK: - Avvisi

    private var riquadro: some View {
        Text(web.banner?.text ?? "")
            .font(.footnote)
            .foregroundStyle(.white)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(colore(web.banner?.tone ?? "ok"), in: RoundedRectangle(cornerRadius: 10))
            .padding(12)
            .opacity(web.banner == nil ? 0 : 1)
            // Non deve mai rubare un tocco alla pagina sotto.
            .allowsHitTesting(false)
            .animation(.easeOut(duration: 0.2), value: web.banner?.id)
    }

    private func colore(_ tono: String) -> Color {
        switch tono {
        case "err": return .red
        case "warn": return .orange
        default: return .green
        }
    }
}
