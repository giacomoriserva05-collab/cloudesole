import SwiftUI

/// La scheda Negozio. Si apre sull'elenco dei negozi salvati, non su una
/// pagina web: tocchi un riquadro e il sito si apre lì dentro, dove il pilota
/// può agire. Fuori dall'app, in Safari, nessuna app può intervenire.
struct BrowserView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var web: WebController
    @State private var indirizzo = ""
    @FocusState private var scriveIndirizzo: Bool

    var body: some View {
        VStack(spacing: 0) {
            if web.mostraElenco { intestazioneElenco } else { barraIndirizzo }
            Divider()

            if web.mostraElenco {
                ShopsView()
            } else {
                ZStack(alignment: .bottom) {
                    WebView(webView: web.webView)
                    if let b = web.banner { riquadro(b) }
                }
            }

            Divider()
            barraStrumenti
        }
        .onChange(of: web.currentURL) { nuovo in
            if !scriveIndirizzo { indirizzo = nuovo?.absoluteString ?? "" }
        }
    }

    // MARK: - Testate

    private var intestazioneElenco: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Negozi")
                .font(.title2.weight(.bold))
            campoIndirizzo
        }
        .padding(.horizontal, 14)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background(.bar)
    }

    private var barraIndirizzo: some View {
        campoIndirizzo
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
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
            if !indirizzo.isEmpty && scriveIndirizzo {
                Button { indirizzo = "" } label: { Image(systemName: "xmark.circle.fill") }
                    .foregroundStyle(.secondary)
            }
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

    private func riquadro(_ b: WebController.Banner) -> some View {
        Text(b.text)
            .font(.footnote)
            .foregroundStyle(.white)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(colore(b.tone), in: RoundedRectangle(cornerRadius: 10))
            .padding(12)
            .transition(.move(edge: .bottom).combined(with: .opacity))
            .animation(.easeOut(duration: 0.2), value: b.id)
    }

    private func colore(_ tono: String) -> Color {
        switch tono {
        case "err": return .red
        case "warn": return .orange
        default: return .green
        }
    }
}
