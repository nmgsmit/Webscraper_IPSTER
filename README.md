# Webscraper_IPSTER

Python scraper voor Stella.nl. Het script haalt alle Nederlandse Stella
vestigingen op, inclusief contactgegevens, adresinformatie en openingstijden
voor zowel de fietsenwinkel als de werkplaats.

De output is een gestructureerd JSON-bestand dat direct bruikbaar is als
kennisbank-input voor een LLM.

## Gebruik

Vereist Python 3.9+ en gebruikt alleen de standaardbibliotheek.

```powershell
python scrape_stella_locations.py
```

Standaard schrijft het script naar:

```text
data/stella_vestigingen.json
```

Een ander outputpad kan ook:

```powershell
python scrape_stella_locations.py --output data/stella_vestigingen_latest.json
```

Maak daarna eventueel een minimalistische LLM-versie:

```powershell
python export_simple_llm_json.py
```

Standaard schrijft dit script naar:

```text
data/stella_vestigingen_simple.json
```

Deze simpele export bevat bewust alleen:

- `vestiging`
- `plaats`
- `adres`
- `telefoon`
- `email`
- `speciale_openingstijden`
- `openingstijden.fietsenwinkel`
- `openingstijden.werkplaats`

Gebruik deze versie wanneer een LLM zo min mogelijk retrieval-ruis mag krijgen.
De uitgebreide JSON blijft handig voor debugging, broncontrole en toekomstige
uitbreidingen.

## Data

Het script ontdekt de actuele Stella locatie-endpoint vanaf:

```text
https://www.stella.nl/fietsenwinkels
```

De scraper controleerde op dit moment 12 vestigingen:

```text
Amersfoort, Assen, Best, Beverwijk, Breda, Heerhugowaard, Houten,
Nunspeet, Nuth, Ridderkerk, Schiedam, Wijchen
```

Per vestiging bevat de JSON onder andere:

- `naam`
- `plaats`
- `pagina_url`
- `adres`
- `contact.telefoon`
- `contact.algemene_klantenservice_email`
- `contact.website`
- `labels`
- `speciale_openingstijden`
- `openingstijden.fietsenwinkel`
- `openingstijden.werkplaats`

In de Stella-bron heet de winkelopening `Testcenter`; in de JSON is die
genormaliseerd naar `fietsenwinkel`. `Werkplaats` blijft `werkplaats`.

## Call-agent veiligheid

Deze JSON is bedoeld voor een LLM of call-agent die vragen van klanten
beantwoordt. Daarom zijn twee bronvelden bewust aangepast of weggelaten:

1. Geen scrape-time open/dicht-status

   De Stella locatie-endpoint bevat velden zoals `isOpen` en `openingTime`.
   Die zeggen alleen wat de status was op het moment van scrapen. Als een
   call-agent die tekst later gebruikt, kan de agent ten onrechte zeggen dat
   een vestiging "vandaag open tot ..." is terwijl die informatie inmiddels
   verouderd is.

   Daarom schrijft de scraper geen `actuele_status_bij_scrape` meer naar de
   agent-facing JSON. De JSON bevat alleen de vaste weekopeningstijden onder
   `openingstijden`. Een live open/dicht-antwoord moet worden berekend met de
   actuele datum en tijd in `Europe/Amsterdam`.

2. Geen `noreply` e-mailadres als klantcontact

   De Stella locatiebron geeft per vestiging `noreply@stellanext.nl` terug.
   Dat is geen geschikt e-mailadres om aan klanten te geven. De scraper neemt
   dat bronadres daarom niet over.

   In plaats daarvan staat in elke vestiging:

   ```text
   contact.algemene_klantenservice_email = klantenservice@stellanext.nl
   ```

   Dit veld is bewust expliciet gelabeld als algemeen klantenserviceadres,
   zodat de call-agent het niet verwart met een vestigingsspecifiek inboxadres.

3. Geen relatieve daglabels uit de bron

   De Stella-bron gebruikt labels zoals `Vandaag` en `Morgen` in de
   openingstijden. Die labels zijn alleen geldig op het moment van scrapen.
   De scraper schrijft `weergavetitel_bron` daarom niet meer naar de JSON.

   In plaats daarvan gebruikt de JSON vaste weekdagen:

   ```text
   maandag, dinsdag, woensdag, donderdag, vrijdag, zaterdag, zondag
   ```

   Zo kan een call-agent niet per ongeluk een oude scrape-dag als "vandaag"
   voorlezen.

4. Speciale openingstijden en feestdagen

   De scraper zoekt in de officiële Stella-bronnen naar speciale of afwijkende
   openingstijden. Daarvoor worden het fietsenwinkeloverzicht en de
   vestigingspagina's gecontroleerd op termen zoals:

   ```text
   Let op: Wij zijn van DD-MM t/m DD-MM gesloten
   DD-MM t/m DD-MM gesloten
   speciale openingstijden
   gewijzigde openingstijden
   afwijkende openingstijden
   feestdagopening
   openingstijden ... feestdagen
   ```

   De Stella overzichtspagina bevat momenteel deze melding:

   ```text
   Let op: Wij zijn van 25-12 t/m 01-01 gesloten
   ```

   De scraper slaat deze melding op in `bron.speciale_openingstijden` en in
   `speciale_openingstijden` per vestiging, omdat het een algemene melding op
   het fietsenwinkeloverzicht is. De periode wordt gestructureerd als:

   ```text
   type = sluiting
   periode.van = 25-12
   periode.tot_en_met = 01-01
   periode.jaar = null
   ```

   De bron noemt dag en maand, maar geen jaar. Daarom blijft `jaar` leeg en
   bevat de JSON een opmerking dat de sluiting moet worden toegepast op de
   eerstvolgende relevante jaarwisseling. Bij andere feestdagen zonder item
   mag de agent geen afwijkende openingstijden verzinnen.

## Data-normalisatie

De scraper voert ook kleine correcties uit zodat de data natuurlijker en
betrouwbaarder is in klantgesprekken:

- Nederlandse postcodes worden genormaliseerd met een spatie, bijvoorbeeld
  `1948NK` wordt `1948 NK`.
- De provincie van vestiging Best wordt handmatig gecorrigeerd naar
  `Noord-Brabant`. De Stella locatiebron geeft hiervoor `Noord-Holland` terug,
  maar Best ligt in Noord-Brabant.

Deze correctie staat ook in `bron.correcties` in het JSON-bestand, zodat
zichtbaar blijft wat door de scraper is aangepast.
