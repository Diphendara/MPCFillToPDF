## 1. Core Logic & Mapping

- [x] 1.1 Implement Moxfield card mapping logic in `WebLoadApp._start` to construct lists of fronts and backs, utilizing `sanitize_filename` to differentiate single-faced cards and DFCs
- [x] 1.2 Implement combining Moxfield cards with manually added local front/back cards from the GUI lists
- [x] 1.3 Build `local_crop_map` to assign `False` for all downloaded Scryfall card paths and read checkbox values for local manual cards
- [x] 1.4 Implement cardback validation: require `self.local_backs` in duplex mode and inject a dummy fallback (e.g., first front image path) in fronts-only mode to satisfy the pipeline's checks

## 2. GUI Integration & Controls

- [x] 2.1 Update buttons state logic in `WebLoadApp` to enable the "Generar PDF..." buttons when downloads complete, and disable them when a deck is cleared or during download
- [x] 2.2 Implement background thread runner in `WebLoadApp._start` calling `pipeline.run_locals_only` and posting progress to `self.events` queue
- [x] 2.3 Modify `WebLoadApp._drain_events` to call `self._handle(ev)` for unhandled event types (enabling standard pipeline progress and completion logic)
- [x] 2.4 Add a pre-check validation step in `WebLoadApp._start` to verify that all required images exist in the deck download folder on disk before running the pipeline

## 3. Testing & Verification

- [x] 3.1 Create automated tests in the test suite to verify Moxfield card mapping, DFC detection, crop map building, and empty cardback validation logic
- [x] 3.2 Manually verify PDF generation by loading a Moxfield deck, downloading images, specifying a default cardback, and generating both fronts-only and duplex PDFs
- [x] 3.3 Inspect output PDFs to verify correct layout, margins, and pairing of DFC backs vs default cardbacks

## 4. Documentation & Git Commit

- [x] 4.1 Update `README.md` to document Moxfield PDF generation capabilities and default cardback configuration using the optional images pane
- [x] 4.2 Update `CLAUDE.md` describing the new architecture and cardback management design
- [x] 4.3 Commit all changes to the local Git repository
