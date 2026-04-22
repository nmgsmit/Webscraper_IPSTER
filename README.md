# Webscraper_IPSTER - Simple Scrape

Deze branch bevat de minimalistische Stella-export voor LLM-retrieval.

Doel: een chatbot of call-agent zo weinig mogelijk ruis geven, zodat klanten
betrouwbaarder antwoord krijgen op vragen over locatie, telefoonnummer,
e-mailadres en openingstijden.

## Gebruik

Vereist Python 3.9+ en gebruikt alleen de standaardbibliotheek.

```powershell
python export_simple_llm_json.py
```

Standaard schrijft het script naar:

```text
data/stella_vestigingen_simple.json
```

Een ander outputpad kan ook:

```powershell
python export_simple_llm_json.py --output data/mijn_simple_export.json
```

## Welke Data Wordt Gebruikt

Het script haalt live data op uit officiële Stella-bronnen:

- `https://www.stella.nl/fietsenwinkels`
- het locatie-endpoint dat op die pagina staat

Uit het locatie-endpoint gebruikt de simpele export alleen:

- vestigingsnaam
- plaats
- straat, postcode en plaats als één adresregel
- telefoonnummer
- openingstijden van de fietsenwinkel
- openingstijden van de werkplaats

Voor e-mail gebruikt de export bewust het algemene klantenserviceadres:

```text
klantenservice@stellanext.nl
```

De Stella locatiebron bevat namelijk `noreply@stellanext.nl` per vestiging.
Dat adres is niet geschikt om aan klanten te geven.

De algemene sluitingsmelding van Stella wordt ook meegenomen als speciale
openingstijd:

```text
Let op: Wij zijn van 25-12 t/m 01-01 gesloten
```

## Output

De simpele JSON bevat per vestiging alleen:

- `vestiging`
- `plaats`
- `adres`
- `telefoon`
- `email`
- `speciale_openingstijden`
- `openingstijden.fietsenwinkel`
- `openingstijden.werkplaats`

Voorbeeld:

```json
{
  "vestiging": "Stella Amersfoort",
  "plaats": "Amersfoort",
  "adres": "Leusderweg 250, 3817 KH Amersfoort",
  "telefoon": "088-2526370",
  "email": "klantenservice@stellanext.nl",
  "speciale_openingstijden": [
    "Let op: Wij zijn van 25-12 t/m 01-01 gesloten"
  ],
  "openingstijden": {
    "fietsenwinkel": {
      "maandag": "10:00 - 17:00",
      "zondag": "Gesloten"
    },
    "werkplaats": {
      "maandag": "10:00 - 17:00",
      "zondag": "Gesloten"
    }
  }
}
```

## Waarom Minimaal

Deze branch laat de uitgebreide scraper en uitgebreide JSON bewust weg.
Er staan dus geen labels, coördinaten, bronlabels, relatieve daglabels,
provincies, interne correcties of scrape-time open/dicht-status in de
LLM-output.

Dat voorkomt veelvoorkomende retrieval-fouten, zoals:

- een klant een intern of `noreply` e-mailadres geven;
- oude `vandaag` of `morgen` labels voorlezen;
- een verouderde live open/dicht-status gebruiken;
- irrelevante metadata ophalen in plaats van het telefoonnummer of de
  openingstijden.

Voor debugging, broncontrole en uitgebreidere data staat de volledige scraper
op de branch `main`.
