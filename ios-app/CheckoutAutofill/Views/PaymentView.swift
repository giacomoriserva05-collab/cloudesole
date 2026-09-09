import SwiftUI

/// Dati della carta del profilo attivo. Spenti di default: finché non accendi
/// "compila anche i campi carta" il motore non li riceve nemmeno.
struct PaymentView: View {
    @EnvironmentObject var store: Store
    @State private var carta = Card()
    @State private var caricata = false

    var body: some View {
        Form {
            Section {
                Toggle("Compila anche i campi della carta", isOn: $store.settings.fillCard)
            }

            Section("Carta") {
                TextField("Numero", text: $carta.number)
                    .keyboardType(.numberPad)
                    .textContentType(.creditCardNumber)
                TextField("Titolare", text: $carta.name)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                HStack {
                    TextField("Mese", text: $carta.expMonth).keyboardType(.numberPad)
                    Divider()
                    TextField("Anno", text: $carta.expYear).keyboardType(.numberPad)
                    Divider()
                    TextField("CVC", text: $carta.cvc).keyboardType(.numberPad)
                }
            }

            Section {
                Toggle("Ricorda la carta su questo iPhone", isOn: $store.settings.rememberCard)
            } footer: {
                Text("Con la spunta i dati vanno nel portachiavi di iOS, leggibili solo a "
                     + "telefono sbloccato e solo su questo dispositivo: non finiscono nei "
                     + "backup né su un altro telefono. Senza, restano in memoria e "
                     + "spariscono chiudendo l'app.")
            }

            Section {
                Button(role: .destructive) {
                    store.cancellaCarta(for: store.activeID)
                    carta = Card()
                } label: {
                    Label("Cancella i dati della carta", systemImage: "trash")
                }
            } footer: {
                Text("L'app non invia mai i dati da nessuna parte: li scrive nei campi del "
                     + "negozio che stai visitando, e si ferma prima del pulsante d'ordine.")
            }
        }
        .navigationTitle("Pagamento")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            if !caricata {
                carta = store.card(for: store.activeID)
                caricata = true
            }
        }
        .onChange(of: carta) { nuova in
            store.setCard(nuova, for: store.activeID)
        }
    }
}
