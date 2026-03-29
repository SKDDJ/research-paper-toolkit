# Research Paper Toolkit — Roadmap

## Phase 1: Core Pipeline (Done)
- [x] Config/schema foundation (schema.json, profiles, LLM client)
- [x] Deep review Level 1 + Level 2 extraction
- [x] HTML report with editorial aesthetic
- [x] Multi-provider LLM client (Anthropic, OpenAI, Gemini, Runway, Custom)
- [x] Enhanced ar5iv parsing (tables, figures, formulas)
- [x] MathJax formula rendering in HTML reports
- [x] Bold/highlight emphasis for key terms
- [x] Key tables render actual parsed data (not just descriptions)
- [x] Figure URL injection from ar5iv
- [x] Modular SKILL.md with progressive disclosure (references/)
- [x] Profile-driven design (no hardcoded researcher info)
- [x] Git versioning (main + dev branches)

## Phase 1.5: Remaining Core Features
- [ ] Taxonomy management (taxonomy.py: init, bookmark, dismiss, show)
- [ ] Daily scan script (port existing SKILL.md logic to Python)
- [ ] Preference tracking (preferences.py + preferences.jsonl)
- [ ] Cross-paper comparison (cross_compare.py + comparison.html template)

## Phase 2: Rich Content & MineRU
- [ ] MineRU PDF parser integration (magic-pdf as optional dep)
  - Local PDF parsing for papers not on arXiv
  - Extract figures as image files, tables as markdown, formulas as LaTeX
  - Essential for fine-grained analysis of complex visualizations
- [ ] PDF download + caching in data/pdfs/
- [ ] Support non-arXiv papers (direct PDF URL, DOI lookup)

## Phase 3: Interactive Frontend
- [ ] Local localhost server for HTML reports with live interactions
- [ ] Bookmark/dismiss buttons in HTML reports (click -> updates preferences.jsonl)
- [ ] Dating-app style swipe interface for daily digest papers
- [ ] Real-time taxonomy tree browser with drag-and-drop reorganization

## Phase 4: Intelligent Features
- [ ] User onboarding: cold-start questionnaire -> auto-generate profile
- [ ] Customizable report focus (experiments, methodology, research gaps, motivation)
- [ ] Research gap identification (per Dr. Lan's requirements)
- [ ] Mini-experiment planner (idea -> minimal testable prototype)
- [ ] Preference-based recommendation model (beyond keyword TF-IDF)
- [ ] Embedding-based paper similarity for taxonomy suggestions
- [ ] Dynamic model cascade based on cost budget (rule-based -> embedding -> cheap LLM -> strong LLM)

## Phase 5: Multi-Source Ingestion
- [ ] Google Scholar alerts integration
- [ ] X.com (Twitter) monitoring for highlight authors
- [ ] Conference proceeding feeds (SIGMOD, VLDB, KDD notifications)
- [ ] Anthropic/OpenAI/Google research blog RSS feeds

## Phase 6: Cloud Deployment + Team Sharing
- [ ] OpenClaw-compatible deployment
- [ ] Cloud-hosted paper database (avoid duplicate downloads/parsing)
- [ ] Per-user sub-databases with version management and caching
- [ ] Shared taxonomy with team merge/sync
- [ ] Team dashboard showing all members' research progress
