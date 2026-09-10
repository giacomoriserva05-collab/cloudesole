#import "ReteDiSicurezza.h"
#import <objc/runtime.h>

static NSString *const kTesto = @"tocchiTrattenutiTesto";
static NSString *const kData = @"tocchiTrattenutiData";
static NSString *const kConta = @"tocchiTrattenutiConta";

/// Prende nota e lascia proseguire l'app.
static void ca_annota(NSException *eccezione) {
    NSArray<NSString *> *pila = eccezione.callStackSymbols;
    NSUInteger quante = MIN((NSUInteger)12, pila.count);
    NSString *testo = [NSString stringWithFormat:@"%@\n%@\n\n%@",
                       eccezione.name ?: @"eccezione senza nome",
                       eccezione.reason ?: @"senza motivo dichiarato",
                       [[pila subarrayWithRange:NSMakeRange(0, quante)]
                        componentsJoinedByString:@"\n"]];

    NSUserDefaults *d = NSUserDefaults.standardUserDefaults;
    [d setObject:testo forKey:kTesto];
    [d setObject:[NSDate date] forKey:kData];
    [d setInteger:[d integerForKey:kConta] + 1 forKey:kConta];

    NSLog(@"[rete] tocco perso per un'eccezione in UIKit: %@", eccezione.reason);
}

@implementation UIWindow (ReteDiSicurezza)

- (void)ca_sendEvent:(UIEvent *)evento {
    @try {
        // Dopo lo scambio questo nome porta all'implementazione originale:
        // non è ricorsione.
        [self ca_sendEvent:evento];
    } @catch (NSException *eccezione) {
        ca_annota(eccezione);
    }
}

@end

@implementation ReteDiSicurezza

+ (void)installa {
    static dispatch_once_t unaVolta;
    dispatch_once(&unaVolta, ^{
        Method originale = class_getInstanceMethod([UIWindow class], @selector(sendEvent:));
        Method sostituto = class_getInstanceMethod([UIWindow class], @selector(ca_sendEvent:));
        if (originale && sostituto) {
            method_exchangeImplementations(originale, sostituto);
        }
    });
}

+ (NSString *)ultimoTesto {
    return [NSUserDefaults.standardUserDefaults stringForKey:kTesto];
}

+ (NSDate *)ultimaData {
    id valore = [NSUserDefaults.standardUserDefaults objectForKey:kData];
    return [valore isKindOfClass:NSDate.class] ? valore : nil;
}

+ (NSInteger)quanti {
    return [NSUserDefaults.standardUserDefaults integerForKey:kConta];
}

+ (void)dimentica {
    NSUserDefaults *d = NSUserDefaults.standardUserDefaults;
    [d removeObjectForKey:kTesto];
    [d removeObjectForKey:kData];
    [d removeObjectForKey:kConta];
}

@end
