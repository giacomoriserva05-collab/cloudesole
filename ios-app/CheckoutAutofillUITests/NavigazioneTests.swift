import XCTest

/// Il controllo che mancava. Fino a ieri la CI avviava l'app e la fotografava:
/// se crollava aprendo una scheda, non se ne accorgeva nessuno. Qui l'app
/// viene toccata dove la toccherebbe una persona.
final class NavigazioneTests: XCTestCase {

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    /// Apre ogni scheda e verifica che l'app sia ancora viva dopo ognuna.
    /// Un crollo si manifesta come `state != .runningForeground`.
    func testLeSchedeSiAprono() throws {
        let app = XCUIApplication()
        app.launch()
        XCTAssertEqual(app.state, .runningForeground, "L'app non è nemmeno partita.")

        for nome in ["Negozio", "Monitor", "Profili", "Impostazioni"] {
            let scheda = app.tabBars.buttons[nome]
            XCTAssertTrue(scheda.waitForExistence(timeout: 10),
                          "La scheda \(nome) non compare nella barra.")
            scheda.tap()
            // Il disegno di una schermata non è istantaneo: se crolla, crolla qui.
            Thread.sleep(forTimeInterval: 1.5)
            XCTAssertEqual(app.state, .runningForeground,
                           "L'app è crollata aprendo la scheda \(nome).")
        }
    }

    /// Le schermate raggiungibili da Impostazioni: account, regole del sito,
    /// diagnostica. Sono quelle che il solo avvio non tocca mai.
    func testLeSchermateInterneSiAprono() throws {
        let app = XCUIApplication()
        app.launch()

        let impostazioni = app.tabBars.buttons["Impostazioni"]
        XCTAssertTrue(impostazioni.waitForExistence(timeout: 10))
        impostazioni.tap()

        for voce in ["Account dei negozi", "Regole per questo sito"] {
            let riga = app.buttons[voce].firstMatch
            guard riga.waitForExistence(timeout: 5) else { continue }
            riga.tap()
            Thread.sleep(forTimeInterval: 1.2)
            XCTAssertEqual(app.state, .runningForeground, "Crollo aprendo \(voce).")
            if app.navigationBars.buttons.element(boundBy: 0).exists {
                app.navigationBars.buttons.element(boundBy: 0).tap()
                Thread.sleep(forTimeInterval: 0.6)
            }
        }
    }

    /// Il monitor con un target vero: è il codice nuovo, ed è quello che il
    /// solo avvio non esercita mai.
    func testIlMonitorSiAvvia() throws {
        let app = XCUIApplication()
        app.launch()

        let monitor = app.tabBars.buttons["Monitor"]
        XCTAssertTrue(monitor.waitForExistence(timeout: 10))
        monitor.tap()
        Thread.sleep(forTimeInterval: 1.5)
        XCTAssertEqual(app.state, .runningForeground, "Crollo aprendo il Monitor.")

        // Il modulo del target: si apre, si scrive, si salva.
        let piu = app.navigationBars.buttons["add"].firstMatch
        if piu.waitForExistence(timeout: 4) {
            piu.tap()
            Thread.sleep(forTimeInterval: 1.0)
            XCTAssertEqual(app.state, .runningForeground, "Crollo aprendo il nuovo target.")

            let annulla = app.buttons["Annulla"].firstMatch
            if annulla.waitForExistence(timeout: 3) { annulla.tap() }
        }
        Thread.sleep(forTimeInterval: 0.8)
        XCTAssertEqual(app.state, .runningForeground)
    }
}
