import SwiftUI

/// Gli account dei negozi che senza login non fanno finire l'ordine — END. è
/// il caso tipico. Qui c'è il nome utente; la password sta nel portachiavi di
/// iOS, protetta dal riconoscimento, e non si rilegge mai da questa schermata.
struct AccountsView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var web: WebController
    @State private var mostraNuovo = false

    var body: some View {
        List {
            if store.accounts.isEmpty {
                Section {
                    Text("Nessun account salvato.")
                        .foregroundStyle(.secondary)
                } footer: {
                    Text("Aggiungine uno con il più in alto. Poi, sulla pagina di accesso "
                         + "del negozio, comparirà la chiave nella barra in basso: un tocco, "
                         + "Face ID, e i campi sono pieni.")
                }
            }

            ForEach(store.accounts) { voce in
                VStack(alignment: .leading, spacing: 3) {
                    Text(voce.host).font(.callout.weight(.semibold))
                    Text(voce.utente).font(.caption).foregroundStyle(.secondary)
                    if !voce.nota.isEmpty {
                        Text(voce.nota).font(.caption2).foregroundStyle(.secondary)
                    }
                }
            }
            .onDelete { indici in
                for i in indici { store.rimuoviAccount(store.accounts[i]) }
            }

            Section {
                Text("La password non è leggibile da qui, e nemmeno da me: viene riscritta "
                     + "nel portachiavi ogni volta che la cambi, e riletta solo nell'istante "
                     + "in cui va scritta nel modulo del negozio. Il pulsante \"Accedi\" non "
                     + "viene mai premuto al posto tuo.")
                .font(.footnote)
                .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Account")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { mostraNuovo = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $mostraNuovo) {
            NuovoAccountView(hostSuggerito: web.host)
                .environmentObject(store)
        }
    }
}

/// Il modulo per salvare un accesso. È l'unico punto in cui si scrive una
/// password, e la scrivi tu.
struct NuovoAccountView: View {
    @EnvironmentObject var store: Store
    @Environment(\.dismiss) private var chiudi

    let hostSuggerito: String
    @State private var host = ""
    @State private var utente = ""
    @State private var segreto = ""
    @State private var nota = ""
    @State private var errore = ""

    private var valido: Bool {
        !host.trimmingCharacters(in: .whitespaces).isEmpty &&
        !utente.trimmingCharacters(in: .whitespaces).isEmpty &&
        !segreto.isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Sito (es. endclothing.com)", text: $host)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    TextField("Email o nome utente", text: $utente)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.emailAddress)
                    SecureField("Password", text: $segreto)
                    TextField("Nota (facoltativa)", text: $nota)
                } footer: {
                    Text("Il sito vale anche per i sottodomini: salvato su endclothing.com "
                         + "funziona anche su www.endclothing.com.")
                }

                if !errore.isEmpty {
                    Section {
                        Text(errore).foregroundStyle(.red).font(.footnote)
                    }
                }

                Section {
                    Text("La password finisce nel portachiavi di iOS con la protezione del "
                         + "riconoscimento: per rileggerla il telefono chiederà Face ID o il "
                         + "codice. Non esce dal dispositivo, non entra nei backup, non "
                         + "raggiunge nessun server.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Nuovo account")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Annulla") { chiudi() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Salva") { salva() }.disabled(!valido)
                }
            }
            .onAppear { if host.isEmpty { host = hostSuggerito } }
        }
    }

    private func salva() {
        if store.salvaAccount(host: host, utente: utente, password: segreto, nota: nota) {
            chiudi()
        } else {
            errore = "Il portachiavi non ha accettato la password. Riprova."
        }
    }
}
