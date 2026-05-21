# MPCFillToPDF

Automated pipeline that converts an MPCFill XML project file into a print-ready PDF for a local print shop.

## What it does

1. Parses an MPCFill XML file to extract card front/back assignments and Google Drive image IDs
2. Downloads images from Google Drive
3. Crops images (removes MPC bleed border: 4.2% width + 3.1% height per side)
4. Generates a duplex-ready PDF with fronts on page 1 and mirrored backs on page 2

## XML structure (MPCFill format)

- `<fronts>` and `<backs>` contain `<card>` entries with `<id>` (Google Drive file ID), `<slots>`, `<name>`, `<query>`
- Slot numbers pair fronts with backs (same slot number = same physical card)
- `<cardback>` is the default back for all slots not listed in `<backs>`
- Cards without a specific entry in `<backs>` use the default cardback

## PDF layout

- Paper: A4 portrait
- Grid: 3 columns × 3 rows = 9 cards per page
- Cards are evenly spaced; crop marks appear in the page margins (not between cards)
- Page 1: front faces in slot order (slots 0–8, left to right, top to bottom)
- Page 2: backs horizontally mirrored so duplex printing aligns correctly
  - Mirroring means slot positions: [2,1,0 / 5,4,3 / 8,7,6] on back page
  - Each slot uses its specific back if defined in `<backs>`, otherwise uses `<cardback>`

## Tech stack

- **Language**: Python 3.10+
- **XML parsing**: `xml.etree.ElementTree` (stdlib)
- **Image download**: `requests` (with Google Drive large-file redirect handling)
- **Image processing**: `Pillow`
- **PDF generation**: `reportlab`

## Interfaces

The project targets three delivery modes, built in this order:

1. **CLI** — accepts XML path, outputs PDF path; basis for the other interfaces
2. **Desktop GUI** — file picker + progress display; for end users on Windows/Mac/Linux
3. **Web app** — upload XML → download PDF; hosted publicly so anyone can use it without installing anything

## Project structure

```
MPCFillToPDF/
├── src/
│   ├── parser.py          # XML parsing → structured card data
│   ├── downloader.py      # Google Drive image download
│   ├── cropper.py         # Bleed removal (Pillow)
│   ├── pdf_generator.py   # PDF layout (reportlab)
│   └── pipeline.py        # Orchestrates the full flow
├── cli/
│   └── main.py            # CLI entry point (argparse)
├── gui/
│   └── app.py             # Desktop GUI (TBD: tkinter or similar)
├── web/
│   └── app.py             # Web app (TBD: Flask or FastAPI)
├── examples/
│   ├── example.xml        # Reference MPCFill project file
│   ├── example.pdf        # Target PDF output (reference)
│   └── imgsPdf/           # Screenshots of the reference PDF layout
├── scripts/
│   └── crop.py            # Original standalone crop script (reference)
└── tests/
```

## Key implementation notes

### Image download
- The mpc-autofill desktop tool uses the official Google Drive API with service account credentials; our tool targets public use without credentials
- Use `gdown` library instead: it handles the virus-scan warning redirect automatically
  - `gdown.download(f"https://drive.google.com/uc?id={drive_id}", output_path, quiet=False)`
- Fallback raw URL (may require manual bypass): `https://drive.google.com/uc?export=download&id={id}`
- Download with 5 parallel threads (matches mpc-autofill behaviour)

### Image cropping
- Crop formula: `border_x = round(width * 0.042)`, `border_y = round(height * 0.031)`
- Crop box: `(border_x, border_y, width - border_x, height - border_y)`

### PDF layout (Copistería Soriano profile)
- Paper: A4 portrait (210mm × 297mm)
- Grid: 3 columns × 3 rows = 9 cards per page
- Card size after crop: standard poker 63mm × 88mm
- Gap between cards: 2mm (sangrado/bleed from PNP Tool profile)
- Crop marks in page margins (not between cards); mark length ~3mm, line width 0.25pt
- Page 1 fronts slot order: left→right, top→bottom (slots 0–8)
- Page 2 backs are horizontally mirrored: `col_back = 2 - col_front`, same row
  - Each slot uses its specific back if in `<backs>`, otherwise uses `<cardback>`

### Cards per page
- Always 9 (3×3); when total cards > 9 generate multiple front/back page pairs
- Last page pair may have fewer than 9 cards; empty slots left blank
