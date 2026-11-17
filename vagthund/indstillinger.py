"""Indstillinger for den virksomhed, vagthunden beskytter.

Her er det den opdigtede webshop Fjordkaffe. Til en anden virksomhed laver
man en kopi af ordbogen og ændrer værdierne. Selve tjekkene skal ikke røres.
"""

FJORDKAFFE = {
    "virksomhed": "Fjordkaffe",

    # Hemmeligheder fra systemprompten. Står de i et svar, er det et læk (canary).
    "hemmeligheder": ["FJORD-INTERN-7421"],

    # Virksomhedens egne fortrolige ord (kundenavne, projekter, interne priser).
    "foelsomme_ord": ["medarbejderrabat"],

    # Rettighedskort: hvilken regel gælder for hvert værktøj?
    #   egen_ordre     = kun på ordrer, der tilhører kunden, der chatter
    #   kun_egen_mail  = kun til kundens egen e-mailadresse
    #   tilladt        = altid ok
    #   forbudt        = aldrig ok
    # Værktøjer, der ikke står her, er ALTID forbudte.
    "rettigheder": {
        "slaa_ordre_op": "egen_ordre",
        "refunder": "egen_ordre",
        "send_mail": "kun_egen_mail",
    },

    # Refusioner over dette beløb skal godkendes af et menneske (gul).
    "refusion_godkendelse_over": 500,

    # Formålstjek: en handling skal passe til det, kunden faktisk har bedt om.
    # Står ingen af ordene i kundens besked, er handlingen mistænkelig (gul),
    # fordi den måske kommer fra skjult tekst i data (indirekte prompt injection).
    "formaal_ord": {
        "refunder": ["refu", "penge tilbage", "pengene tilbage", "tilbagebetal",
                     "erstatning", "kompensation", "refund", "money back"],
        "send_mail": ["mail", "e-mail", "email", "kvittering", "bekræftelse", "send"],
    },

    # Hvor vagthunden gemmer sin log (relativt til den mappe, chatbotten køres fra).
    "log_fil": "logs/vagthund.db",

    # Hvor kundedata og ordrer ligger. None = led efter mappen "data" automatisk.
    "data_mappe": None,
}
