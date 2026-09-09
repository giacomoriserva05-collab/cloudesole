import SwiftUI

/// Profili: quanti ne vuoi, ognuno col suo indirizzo, la sua taglia e la sua
/// carta. Si salva da sé, non c'è nessun pulsante "Salva".
struct ProfilesView: View {
    @EnvironmentObject var store: Store
    @State private var chiediConferma = false

    private var profilo: Binding<Profile> {
        Binding(get: { store.active }, set: { store.active = $0 })
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Profilo attivo", selection: $store.activeID) {
                        ForEach(store.profiles) { p in Text(p.name).tag(p.id) }
                    }
                    TextField("Nome del profilo", text: profilo.name)
                } footer: {
                    Text("Il profilo attivo è quello che il pilota userà sul negozio.")
                }

                Section("Spedizione") {
                    CampiIndirizzo(indirizzo: profilo.shipping)
                }

                Section {
                    TextField("Taglia (42, 42.5, M…)", text: profilo.shipping.size)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                } header: {
                    Text("Taglia")
                } footer: {
                    Text("Lasciala vuota per far prendere la prima taglia disponibile. "
                         + "Se la scrivi e non c'è, il pilota si ferma invece di scegliere al posto tuo.")
                }

                Section {
                    Toggle("Indirizzo di fatturazione diverso", isOn: profilo.billingEnabled)
                    if store.active.billingEnabled {
                        CampiIndirizzo(indirizzo: profilo.billing)
                    }
                } footer: {
                    Text("Basta scrivere i campi che cambiano: il resto arriva dalla spedizione.")
                }

                Section("Pagamento") {
                    NavigationLink { PaymentView() } label: {
                        HStack {
                            Text("Dati della carta")
                            Spacer()
                            Text(store.card(for: store.activeID).isEmpty ? "Non impostata" : "Impostata")
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Section {
                    Button { store.aggiungiProfilo(copiandoAttivo: false) } label: {
                        Label("Nuovo profilo", systemImage: "plus")
                    }
                    Button { store.aggiungiProfilo(copiandoAttivo: true) } label: {
                        Label("Duplica questo profilo", systemImage: "doc.on.doc")
                    }
                    Button(role: .destructive) { chiediConferma = true } label: {
                        Label("Elimina questo profilo", systemImage: "trash")
                    }
                    .disabled(store.profiles.count < 2)
                }
            }
            .navigationTitle("Profili")
            .confirmationDialog("Eliminare \"\(store.active.name)\"?",
                                isPresented: $chiediConferma, titleVisibility: .visible) {
                Button("Elimina", role: .destructive) { store.eliminaProfiloAttivo() }
                Button("Annulla", role: .cancel) { }
            } message: {
                Text("Sparisce anche la carta salvata per questo profilo.")
            }
        }
    }
}

/// I campi di un indirizzo. Gli stessi, in fatturazione e in spedizione.
struct CampiIndirizzo: View {
    @Binding var indirizzo: Address

    // Diviso in due blocchi: un ViewBuilder accetta al massimo dieci viste.
    var body: some View {
        Group {
            contatti
            indirizzoPostale
        }
    }

    private var contatti: some View {
        Group {
            TextField("Nome", text: $indirizzo.firstName)
                .textContentType(.givenName)
            TextField("Cognome", text: $indirizzo.lastName)
                .textContentType(.familyName)
            TextField("Email", text: $indirizzo.email)
                .textContentType(.emailAddress)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            TextField("Telefono", text: $indirizzo.phone)
                .textContentType(.telephoneNumber)
                .keyboardType(.phonePad)
            TextField("Azienda (facoltativo)", text: $indirizzo.company)
            TextField("Codice fiscale (facoltativo)", text: $indirizzo.fiscalCode)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
            TextField("Data di nascita (gg/mm/aaaa)", text: $indirizzo.birthDate)
                .keyboardType(.numbersAndPunctuation)
        }
    }

    private var indirizzoPostale: some View {
        Group {
            TextField("Indirizzo (via)", text: $indirizzo.address1)
                .textContentType(.streetAddressLine1)
            TextField("Civico", text: $indirizzo.houseNumber)
            TextField("Interno / scala", text: $indirizzo.address2)
                .textContentType(.streetAddressLine2)
            TextField("CAP", text: $indirizzo.postalCode)
                .textContentType(.postalCode)
                .keyboardType(.numbersAndPunctuation)
            TextField("Città", text: $indirizzo.city)
                .textContentType(.addressCity)
            TextField("Provincia (sigla)", text: $indirizzo.province)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
            Picker("Paese", selection: $indirizzo.country) {
                ForEach(Paesi.all) { Text($0.nome).tag($0.id) }
            }
        }
    }
}
