# Source documents

Educational demo: **public documents only**. No FRA data, no private or classified material.

Selected pages for the versioned evaluation set (`evals/sources.json`):

- IMY, personal data incidents:
  <https://www.imy.se/verksamhet/dataskydd/det-har-galler-enligt-gdpr/personuppgiftsincidenter/>
- Digg, digital accessibility:
  <https://www.digg.se/kunskap-och-stod/digital-tillganglighet>
- Myndigheten för civilt försvar (MCF), public guidance landing page:
  <https://www.mcf.se/sv/rad-till-privatpersoner/>

Additional public pages for a broader demo corpus. These are not yet covered by the evaluation set:

- MCF, home preparedness basics:
  <https://www.mcf.se/sv/rad-till-privatpersoner/hemberedskap---preppa-for-en-vecka/grunder-i-hemberedskap/>
- MCF, growing your own food:
  <https://www.mcf.se/sv/rad-till-privatpersoner/hemberedskap---preppa-for-en-vecka/mat/att-odla-sjalv/>
- Försäkringskassan, introduction for expecting parents:
  <https://www.forsakringskassan.se/privatperson/familj-och-barn/introduktion-till-dig-som-ska-bli-foralder>
- Försäkringskassan, parental benefit (föräldrapenning):
  <https://www.forsakringskassan.se/privatperson/familj-och-barn/foraldrapenning>

1. Review each publisher's current terms and the exact page version before local use.
2. Save each page's text as a local Markdown file in this folder. `*.md` here is git-ignored, so
   third-party text is not redistributed.
3. Record for each file: page URL, retrieval date/version, and its licence or reuse terms. The
   evaluation only matches citations by these stable page URLs.
4. Ingest with
   `uv run python -m secure_rag_demo.ingest_cli FILE --title T --url URL --version V`.
