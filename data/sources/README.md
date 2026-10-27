# Source documents

Educational demo: **public documents only**. No FRA data, no private or classified material.

Selected pages for the versioned evaluation set (`evals/sources.json`):

- IMY, personal data incidents:
  <https://www.imy.se/verksamhet/dataskydd/det-har-galler-enligt-gdpr/personuppgiftsincidenter/>
- Digg, digital accessibility:
  <https://www.digg.se/kunskap-och-stod/digital-tillganglighet>
- Myndigheten för civilt försvar (MCF), public guidance landing page:
  <https://www.mcf.se/sv/rad-till-privatpersoner/>

1. Review each publisher's current terms and the exact page version before local use.
2. Save each page's text as a local Markdown file in this folder. `*.md` here is git-ignored, so
   third-party text is not redistributed.
3. Record for each file: page URL, retrieval date/version, and its licence or reuse terms. The
   evaluation only matches citations by these stable page URLs.
4. Ingest with
   `uv run python -m secure_rag_demo.ingest_cli FILE --title T --url URL --version V`.
