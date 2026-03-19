"""
Data page for the map application. For simplicity's sake, here is a single file.
"""

DATA_PAGE_HTML = r"""
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Daten & Methodik</title>
  <style>
    :root {
      --bg: #f8fafc;
      --card: #ffffff;
      --text: #111827;
      --muted: #4b5563;
      --border: #e5e7eb;
      --accent: #111827;
      --accent-soft: #f3f4f6;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
      color: var(--text);
    }

    .wrap {
      max-width: 980px;
      margin: 0 auto;
      padding: 40px 20px 56px;
    }

    .hero {
      margin-bottom: 24px;
    }

    .eyebrow {
      display: inline-block;
      margin-bottom: 12px;
      padding: 6px 12px;
      border-radius: 999px;
      background: var(--accent-soft);
      border: 1px solid var(--border);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.02em;
      color: var(--muted);
    }

    h1 {
      margin: 0 0 14px;
      font-size: clamp(30px, 5vw, 42px);
      line-height: 1.1;
    }

    .lead {
      max-width: 780px;
      font-size: 18px;
      line-height: 1.7;
      color: var(--muted);
      margin: 0;
    }

    .grid {
      display: grid;
      gap: 20px;
      grid-template-columns: 1fr;
    }

    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 28px;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
    }

    h2 {
      margin: 0 0 16px;
      font-size: 24px;
      line-height: 1.2;
    }

    p {
      margin: 0 0 16px;
      line-height: 1.75;
      color: var(--muted);
      font-size: 16px;
    }

    p:last-child {
      margin-bottom: 0;
    }

    .facts {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin: 18px 0 22px;
    }

    .fact {
      background: #f9fafb;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px 16px;
    }

    .fact-label {
      display: block;
      font-size: 13px;
      font-weight: 700;
      color: #6b7280;
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }

    .fact-value {
      font-size: 15px;
      font-weight: 600;
      color: var(--text);
      line-height: 1.5;
    }

    a {
      color: var(--accent);
      font-weight: 700;
      text-decoration-thickness: 2px;
      text-underline-offset: 2px;
    }

    .back {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 24px;
      padding: 12px 16px;
      border-radius: 12px;
      background: var(--accent);
      color: white;
      text-decoration: none;
      font-weight: 700;
    }

    .back:hover {
      opacity: 0.94;
    }

    @media (max-width: 640px) {
      .wrap {
        padding: 28px 16px 40px;
      }

      .card {
        padding: 22px;
        border-radius: 18px;
      }

      .lead {
        font-size: 17px;
      }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="grid">
      <section class="card">
        <h2>Projekt</h2>
        <p>
        Dieses Projekt analysiert die Erreichbarkeit im deutschen Regional- und Fernverkehr auf Basis öffentlich 
        verfügbarer Fahrplandaten. Dargestellt werden Reisezeiten, die Anzahl notwendiger Umstiege sowie das Verhältnis 
        von Reisezeiten im öffentlichen Verkehr zum motorisierten Individualverkehr auf Ebene räumlicher Zonen. Ziel ist 
        es, Unterschiede in der verkehrlichen Erreichbarkeit regional vergleichbar und interaktiv sichtbar zu machen.
        </p>
        <p>
        Das Projekt basiert auf einem GTFS-basierten Datenworkflow, der Fahrplandaten verarbeitet und für Routing und 
        Auswertung aufbereitet. Die schnellsten Verbindungen zwischen Haltestellen werden mit einem RAPTOR-basierten 
        Modul berechnet und anschließend auf räumliche Zonen übertragen. Ergänzend werden für dieselben Zonenrelationen 
        auch Pkw-Reisezeiten berechnet. Dadurch wird sichtbar, wo der öffentliche Verkehr besonders leistungsfähig ist, 
        wo viele Umstiege erforderlich sind und wo sich deutliche Unterschiede zur Erreichbarkeit mit dem Auto zeigen.
        </p>
      </section>

      <section class="card">
        <h2>Daten und Methodik</h2>

        <div class="facts">
          <div class="fact">
            <span class="fact-label">GTFS-Daten</span>
            <span class="fact-value">Datensatz von gtfs.de (Stand 24.02.2026)</span>
          </div>
          <div class="fact">
            <span class="fact-label">Fahrplanzeitraum</span>
            <span class="fact-value">KW 9 (23. Februar bis 1. März 2026)</span>
          </div>
          <div class="fact">
            <span class="fact-label">Zonierung</span>
            <span class="fact-value">VG1000, ungefähr Landkreisebene</span>
          </div>
          <div class="fact">
            <span class="fact-label">Pkw-Daten</span>
            <span class="fact-value">Aus openrouteservice API (Stand 24.02.2026)</span>
          </div>
        </div>

        <p>
          Grundlage des Projekts sind zwei GTFS-Datensätze von 
          <a href="https://gtfs.de/" target="_blank" rel="noopener noreferrer">gtfs.de</a>
          mit Fahrplandaten für die Kalenderwoche 9 aus dem Jahr 2026. Als räumliche Bezugsebene wird die
          <a href="https://gdz.bkg.bund.de/index.php/default/verwaltungsgebiete-1-1-000-000-stand-31-12-vg1000-31-12.html" target="_blank" rel="noopener noreferrer">VG1000-Zonierung</a>
          verwendet, die ungefähr den deutschen Landkreisen entspricht.
        </p>
        <p>
          Für jede Zone wurde die Haltestelle mit den meisten Abfahrten als repräsentativer Halt ausgewählt. Von diesen
          Haltestellen aus wurden mit einem RAPTOR-basierten Routingverfahren die schnellsten Verbindungen zu allen anderen
          Haltestellen für jede volle Stunde berechnet. Berücksichtigt wurden dabei sowohl die Reisezeit als auch
          die Zahl der erforderlichen Umstiege bei schnellster Verbindung. Berücksichtig werden ausschließlich ICE, IC, RB, RE und S-Bahnen.
          Ersatzverkehre, U-Bahn, Straßenbahn oder Regionalbusse werden bei der Berechnung nicht berücksichtigt.
          Zudem ist zu beachten, dass die Daten ausschließlich auf dem GTFS Datensatz beruhen und dieser Fehler enthalten kann.
          Die so entstehenden Ergebnisse werden anschließend auf Zonenebene zusammengefasst und in der Karte dargestellt.
        </p>
        <p>
          Zusätzlich wurden mit <a href="https://openrouteservice.org/" target="_blank" rel="noopener noreferrer">openrouteservice</a>
          Pkw-Reisezeiten zwischen den repräsentativen Haltestellen berechnet. Um realistischere Bedingungen abzubilden,
          wurden diese Zeiten abhängig von der Tageszeit mit Faktoren von 1,0, 1,1 oder 1,2 angepasst, um beispielsweise
          Stau und Parksuchzeiten näherungsweise einzubeziehen.
        </p>
        <p>
          Code und Datengrundlage sind über <a href="https://github.com/tarikels/deutsche-bahn-traveltimes" target="_blank" rel="noopener noreferrer">GitHub</a> verfügbar. 
          Das Projekt und Berechnungen können außerdem mit anderen GTFS-Datensätzen, Zonierungen und Auswahlmethoden für repräsentative Haltestellen weiterverwendet werden. 
          Einige Erweiterungen sind bereits im Code implementiert, zudem wir im Code die genaue Berechnungsmethodik der Reisezeiten ersichtlich.
        </p>
        <p>
        DISCLAIMER: Dieses Projekt ist in keiner Verbindung zur Deutschen Bahn. Alle Angaben erfolgen ohne Gewähr und können Fehler enthalten.
        </p>

        <a class="back" href="/">← Zurück zur Karte</a>
      </section>
    </div>
  </div>
</body>
</html>
"""
