import SwiftUI

/// Il negozio si naviga qui dentro. È l'unico posto in cui il pilota può
/// agire: fuori dall'app, in Safari, nessuna app può intervenire sulle pagine.
struct BrowserView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var web: WebController
    @State private var indirizzo = ""
    @FocusState private var scriveIndirizzo: Bool

    var body: some View {
        VStack(spacing: 0) {
            barraIndirizzo
            Divider()
            ZStack(alignment: .bottom) {
                WebView(webView: web.webView)
                if let b = web.banner { riquadro(b) }
            }
            Divider()
            barraStrumenti
        }
        .onAppear {
            if web.currentURL == nil { web.vai(a: "https://www.google.com") }
        }
        .onChange(of: web.currentURL) { nuovo in
            if !scriveIndirizzo { indirizzo = nuovo?.absoluteString ?? "" }
        }
    }

    private var barraIndirizzo: some View {
        HStack(spacing: 8) {
            Image(systemName: web.isLoading ? "arrow.triangle.2.circlepath" : "lock.fill")
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
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private var barraStrumenti: some View {
        HStack(spacing: 18) {
            Button { web.indietro() } label: { Image(systemName: "chevron.left") }
                .disabled(!web.canGoBack)
            Button { web.avanti() } label: { Image(systemName: "chevron.right") }
                .disabled(!web.canGoForward)
            Button { web.ricarica() } label: { Image(systemName: "arrow.clockwise") }

            Spacer()

            Button { web.compilaAdesso() } label: {
                Label("Compila", systemImage: "square.and.pencil")
                    .labelStyle(.iconOnly)
            }

            Button {
                store.armed.toggle()
                web.mostra(store.armed
                           ? "Pilota acceso: apri la scheda prodotto."
                           : "Pilota spento: non tocca più nessuna pagina.",
                           tono: "ok")
            } label: {
                Label(store.armed ? "Attivo" : "Attiva", systemImage: store.armed ? "bolt.fill" : "bolt.slash")
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
