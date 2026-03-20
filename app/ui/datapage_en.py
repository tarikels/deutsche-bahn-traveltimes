"""
Data page for the map application. For simplicity's sake, here is a single file.
"""

DATA_PAGE_HTML_EN = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Data & Methodology</title>
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
        <h2>Project</h2>
        <p>
        This project analyses accessibility in German regional and long-distance rail transport based on publicly
        available timetable data. It displays travel times, the number of required transfers, and the ratio of
        public transport travel times to private motorised transport travel times at the level of spatial zones.
        The aim is to make regional differences in transport accessibility comparable and interactively visible.
        </p>
        <p>
        The project is based on a GTFS-based data workflow that processes timetable data and prepares it for routing
        and analysis. The fastest connections between stops are calculated with a RAPTOR-based module and then
        transferred to spatial zones. In addition, car travel times are also calculated for the same zone relations.
        This makes it visible where public transport performs particularly well, where many transfers are required,
        and where substantial differences compared with car accessibility can be observed.
        </p>
      </section>

      <section class="card">
        <h2>Data and Methodology</h2>

        <div class="facts">
          <div class="fact">
            <span class="fact-label">GTFS Data</span>
            <span class="fact-value">Dataset from gtfs.de (as of 24 February 2026)</span>
          </div>
          <div class="fact">
            <span class="fact-label">Timetable Period</span>
            <span class="fact-value">Calendar week 9 (23 February to 1 March 2026)</span>
          </div>
          <div class="fact">
            <span class="fact-label">Zoning</span>
            <span class="fact-value">VG1000, approximately county level</span>
          </div>
          <div class="fact">
            <span class="fact-label">Car Data</span>
            <span class="fact-value">From the openrouteservice API (as of 24 February 2026)</span>
          </div>
        </div>

        <p>
          The project is based on two GTFS datasets from
          <a href="https://gtfs.de/" target="_blank" rel="noopener noreferrer">gtfs.de</a>
          containing timetable data for calendar week 9 in 2026. The spatial reference layer used is the
          <a href="https://gdz.bkg.bund.de/index.php/default/verwaltungsgebiete-1-1-000-000-stand-31-12-vg1000-31-12.html" target="_blank" rel="noopener noreferrer">VG1000 zoning</a>,
          which roughly corresponds to German counties.
        </p>
        <p>
          For each zone, the stop with the highest number of departures was selected as the representative stop. From these
          stops, the fastest connections to all other stops were calculated for each full hour using a RAPTOR-based routing method.
          Both travel time and the number of required transfers for the fastest connection were taken into account.
          Only ICE, IC, RB, RE, and S-Bahn services are considered.
          Rail replacement services, underground services, trams, and regional buses are not included in the calculations.
          It should also be noted that the data is based exclusively on the GTFS dataset and that this dataset may contain errors.
          The resulting values are then aggregated at zone level and displayed on the map.
        </p>
        <p>
          In addition, car travel times between the representative stops were calculated using
          <a href="https://openrouteservice.org/" target="_blank" rel="noopener noreferrer">openrouteservice</a>.
          To reflect more realistic conditions, these times were adjusted depending on the time of day using factors of 1.0, 1.1, or 1.2
          in order to approximately account for congestion and parking search times.
        </p>
        <section class="card">
        <h2>Meaning of the Metrics</h2>

        <p>
          <strong>Rail travel time:</strong> This shows the fastest connection departing within the selected
          hour from the representative stop of a zone. If there is no suitable departure within that hour,
          the value remains empty. For weekdays, this application uses Tuesday, 24 February 2026,
          as the reference day of the analysed week.
        </p>

        <p>
          <strong>Car travel time:</strong> This shows the car travel time between the representative stops of the
          zones, calculated via the openrouteservice API. To roughly reflect different traffic conditions,
          travel times are weighted depending on the time of day: by a factor of 1.2 for the hours from 7 to 9 a.m. and
          from 3 to 6 p.m., by a factor of 1.0 for the hours from 10 p.m. to 5 a.m., and by a factor of 1.1 for all remaining
          hours.
        </p>

        <p>
          <strong>Rail transfers:</strong> This gives the number of transfers for the fastest connection selected
          for the metric “Rail travel time”. Walking links between stops or within stations are not counted as transfers.
        </p>

        <p>
          <strong>Public transport / car travel time ratio:</strong> This metric describes the ratio of rail travel time
          to car travel time. A value of 1.0 means that both modes are equally fast. Values above 1.0
          indicate that travel by train takes longer than by car, while values below 1.0 indicate a
          faster connection by public transport.
        </p>
      </section>
        <p>
          The code and data basis are available via
          <a href="https://github.com/tarikels/deutsche-bahn-traveltimes" target="_blank" rel="noopener noreferrer">GitHub</a>.
          The project and calculations can also be reused with other GTFS datasets, zonings, and selection methods for representative stops.
          Some extensions are already implemented in the code, and the exact methodology used for the travel time calculations is also visible in the code.
        </p>
        <p>
          <strong>Disclaimer:</strong> This project is not affiliated with Deutsche Bahn in any way.
          All information is provided without guarantee and may contain errors or inaccuracies.
        </p>

        <a class="back" href="/">← Back to map</a>
      </section>
    </div>
  </div>
</body>
</html>
"""