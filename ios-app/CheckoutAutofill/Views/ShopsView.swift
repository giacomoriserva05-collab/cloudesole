import SwiftUI

/// La schermata iniziale della scheda Negozio: i negozi salvati, uno per
/// riquadro. Tocchi e si apre il sito, senza passare dalla barra d'indirizzo.
struct ShopsView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var web: WebController
    @State private var mostraAggiunta = false

    private let colonne = [GridItem(.adaptive(minimum: 104), spacing: 14)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: colonne, spacing: 14) {
                ForEach(store.shops) { negozio in
                    Button {
                        web.vai(a: negozio.indirizzo)
                    } label: {
                        Riquadro(negozio: negozio)
                    }
                    .buttonStyle(.plain)
                    // Tenendo premuto si elimina: niente modalità "modifica".
                    .contextMenu {
                        Button(role: .destructive) {
                            store.rimuoviNegozio(negozio)
                        } label: {
                            Label("Elimina", systemImage: "trash")
                        }
                    }
                }

                Button {
                    mostraAggiunta = true
                } label: {
                    RiquadroAggiungi()
                }
                .buttonStyle(.plain)
            }
            .padding(16)

            if store.shops.isEmpty {
                Text("Nessun negozio. Tocca il riquadro col più per aggiungerne uno.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
            }
        }
        .sheet(isPresented: $mostraAggiunta) {
            AggiungiNegozioView()
                .environmentObject(store)
        }
    }
}

/// Un negozio: pastiglia colorata con le iniziali e il nome sotto.
private struct Riquadro: View {
    let negozio: Shop

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(Color(hue: negozio.tinta, saturation: 0.55, brightness: 0.78))
                Text(negozio.sigla)
                    .font(.title2.weight(.bold))
                    .foregroundStyle(.white)
                    .minimumScaleFactor(0.6)
                    .lineLimit(1)
                    .padding(6)
            }
            .frame(height: 78)

            Text(negozio.nome)
                .font(.caption)
                .foregroundStyle(.primary)
                .lineLimit(1)
                .truncationMode(.tail)
        }
    }
}

private struct RiquadroAggiungi: View {
    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .strokeBorder(Color.secondary.opacity(0.4), style: StrokeStyle(lineWidth: 2, dash: [6]))
                Image(systemName: "plus")
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            .frame(height: 78)

            Text("Aggiungi")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
    }
}

/// Il modulo per aggiungere un negozio a mano.
struct AggiungiNegozioView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var chiudi
    @State private var nome = ""
    @State private var indirizzo = ""

    private var valido: Bool {
        !nome.trimmingCharacters(in: .whitespaces).isEmpty &&
        !indirizzo.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Nome", text: $nome)
                    TextField("Indirizzo", text: $indirizzo)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                } footer: {
                    Text("L'indirizzo può essere scritto anche senza https://, "
                         + "ci pensa l'app. Conviene la pagina principale del negozio, "
                         + "o direttamente quella di una categoria che segui.")
                }

                Section {
                    Button("Ripristina i negozi predefiniti") {
                        store.ripristinaNegozi()
                        chiudi()
                    }
                } footer: {
                    Text("Rimette l'elenco com'era al primo avvio. Quelli aggiunti da te vanno persi.")
                }
            }
            .navigationTitle("Nuovo negozio")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Annulla") { chiudi() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Salva") {
                        store.aggiungiNegozio(nome: nome, indirizzo: indirizzo)
                        chiudi()
                    }
                    .disabled(!valido)
                }
            }
        }
    }
}
