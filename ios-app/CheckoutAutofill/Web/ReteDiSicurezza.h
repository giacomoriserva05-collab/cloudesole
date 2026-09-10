#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

/// Rete di sicurezza sulla consegna dei tocchi.
///
/// Tre resoconti di crash di fila dicono la stessa cosa: UIKit abortisce
/// dentro `-[UIWindow sendEvent:]`, nel codice che trattiene i tocchi per
/// decidere a chi consegnarli. Nella pila non c'è una sola riga di questa
/// app, quindi non c'è una riga da correggere: si può solo togliere di mezzo
/// ciò che ce lo porta.
///
/// Finché non è chiaro cosa sia, questa rete impedisce che un'eccezione lì
/// dentro faccia cadere l'app: l'evento si perde — un tocco mancato — e il
/// motivo resta scritto, leggibile da Impostazioni.
///
/// Non è una cura. È il modo di non far pagare all'utente il tempo che serve
/// per trovarla.
@interface ReteDiSicurezza : NSObject

/// Va chiamata una volta sola, all'avvio.
+ (void)installa;

/// L'ultima eccezione trattenuta, se c'è stata.
+ (nullable NSString *)ultimoTesto;
+ (nullable NSDate *)ultimaData;
+ (NSInteger)quanti;
+ (void)dimentica;

@end

NS_ASSUME_NONNULL_END
