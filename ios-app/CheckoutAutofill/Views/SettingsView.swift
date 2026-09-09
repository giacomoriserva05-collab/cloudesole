import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var web: WebController

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle("Pilota acceso", isOn: $store.armed)
                } footer: {
                    Text("Da acceso: sulla scheda prodotto sceglie la taglia, aggiunge al "
                         + "carrello e apre il checkout, dove compila i campi. Non preme mai "
                         + "il pulsante d'ordine.")
                }

                Section("Dopo l'aggiunta al carrello") {
                    Picker("Apri", selection: $store.settings.afterAdd) {
                        Text("La pagina di checkout").tag("checkout")
                        Text("La pagina del carrello").tag("cart")
                    }
                    Stepper("Attesa: \(store.settings.cartWait) ms",
                            value: $store.settings.cartWait, in: 300...15000, step: 250)
                }

                Section("Compilazione") {
                    Toggle("Compila il checkout appena ci arrivi",
                           isOn: $store.settings.autoFillCheckout)
                    Toggle("Sovrascrivi i campi già compilati",
                           isOn: $store.settings.overwrite)
                    Toggle("Il sito ha un campo civico separato",
                           isOn: $store.settings.splitHouseNumber)
                    Toggle("Evidenzia i campi toccati",
                           isOn: $store.settings.highlight)
                }

                Section {
                    NavigationLink { SiteRulesView() } label: {
                        HStack {
                            Text("Regole per questo sito")
                            Spacer()
                            Text(web.host.isEmpty ? "—" : web.host)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                    NavigationLink { DiagnosticsView() } label: {
                        Label("Prova il pilota su questa pagina", systemImage: "stethoscope")
                    }
                }

                Section {
                    Text("Il pilota agisce solo dentro il browser di questa app. Su iOS "
                         + "nessuna applicazione può intervenire sulle pagine aperte in "
                         + "Safari: per farlo servirebbe un'estensione di Safari, che è "
                         + "un'altra cosa.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Impostazioni")
        }
    }
}

/// Le regole su misura per il negozio aperto adesso.
struct SiteRulesView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var web: WebController
    @State private var cfg = SiteConfig()
    @State private var selettore = ""
    @State private var chiave = FieldKey.all[0].id
    @State private var caricata = false

    var body: some View {
        Form {
            Section {
                TextField("Pulsante aggiungi al carrello (CSS)", text: $cfg.addToCart)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                TextField("Indirizzo del carrello", text: $cfg.cartUrl)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                TextField("Indirizzo del checkout", text: $cfg.checkoutUrl)
                    .textInputAutocapitalization(.never).autocorrectionDisabled()
            } header: {
                Text(web.host.isEmpty ? "Nessun sito aperto" : web.host)
            } footer: {
                Text("Servono solo se il pilota non ci arriva da solo. Vuoti, se la cava "
                     + "con il riconoscimento automatico.")
            }

            Section("Campi non riconosciuti") {
                ForEach(cfg.rules) { r in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(FieldKey.label(r.key)).font(.callout.weight(.semibold))
                        Text(r.selector).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .onDelete { cfg.rules.remove(atOffsets: $0) }

                HStack {
                    TextField("Selettore CSS", text: $selettore)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                    Picker("", selection: $chiave) {
                        ForEach(FieldKey.all) { Text($0.nome).tag($0.id) }
                    }
                    .labelsHidden()
                    Button {
                        guard !selettore.isEmpty else { return }
                        cfg.rules.append(FieldRule(selector: selettore, key: chiave))
                        selettore = ""
                    } label: { Image(systemName: "plus.circle.fill") }
                    .disabled(selettore.isEmpty)
                }
            }
        }
        .navigationTitle("Regole del sito")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            if !caricata { cfg = store.site(for: web.host); caricata = true }
        }
        .onChange(of: cfg) { nuova in
            store.setSite(nuova, for: web.host)
        }
    }
}

/// Cosa vede il pilota in pagina, senza toccare niente.
struct DiagnosticsView: View {
    @EnvironmentObject var web: WebController
    @State private var esito: ProbeResult?
    @State private var interrogato = false

    var body: some View {
        List {
            if let p = esito {
                Section("Pulsante") {
                    if p.pulsanti.isEmpty {
                        Label("Nessuno trovato", systemImage: "xmark.circle")
                            .foregroundStyle(.red)
                    } else {
                        ForEach(p.pulsanti) { b in
                            Label("\(b.testo)\(b.attivo ? "" : " (spento)")",
                                  systemImage: b.attivo ? "checkmark.circle" : "pause.circle")
                        }
                    }
                }
                Section("Taglie") {
                    if let t = p.taglie {
                        Text(t.voci.joined(separator: ", "))
                    } else {
                        Text("Nessun selettore in pagina").foregroundStyle(.secondary)
                    }
                }
                Section("Campi riconosciuti") {
                    if p.campi.isEmpty {
                        Text("Nessuno").foregroundStyle(.secondary)
                    } else {
                        ForEach(p.campi) { c in
                            HStack {
                                Text(FieldKey.label(c.key))
                                Spacer()
                                Text(c.value).foregroundStyle(.secondary).lineLimit(1)
                            }
                        }
                    }
                }
                Section("Indirizzi") {
                    LabeledContent("Carrello", value: p.carrello)
                    LabeledContent("Checkout", value: p.checkout)
                    LabeledContent("Pagina", value: p.carrelloOChckout ? "carrello o checkout"
                                   : p.indirizzoProdotto ? "scheda prodotto" : "altro")
                }
            } else if interrogato {
                Text("Il motore non risponde su questa pagina.").foregroundStyle(.red)
            } else {
                Text("Interrogo la pagina…").foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Prova del pilota")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            Button("Rileggi") { interroga() }
        }
        .onAppear { interroga() }
    }

    private func interroga() {
        web.prova { r in
            esito = r
            interrogato = true
        }
    }
}
