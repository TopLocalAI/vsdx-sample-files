# Inside the `.vsdx` File Format

English | [简体中文](vsdx-file-format.md)

`.vsdx` is the default drawing file format introduced in Microsoft Visio 2013. Built on the **Open Packaging Conventions (OPC, ECMA-376 / ISO/IEC 29500-2)** standard, a `.vsdx` file is an ordinary **ZIP archive** (starting with the 4-byte signature `50 4B 03 04`) containing UTF-8 XML parts, relationship manifests, and optional media files.

Every path, XML element, and attribute described below has been verified directly against the sample files in [`../samples/`](../samples/), which you can unpack and inspect yourself with `unzip` or [`../tools/inspect_vsdx.py`](../tools/inspect_vsdx.py).

---

## 1. Package Directory Layout

Unpacking single-page [`01-basic-flowchart.vsdx`](../samples/01-basic-flowchart.vsdx), multi-page [`08-multi-page-handbook.vsdx`](../samples/08-multi-page-handbook.vsdx), or icon-bearing [`09-embedded-media-icons.vsdx`](../samples/09-embedded-media-icons.vsdx) reveals the following layout:

```text
example.vsdx (ZIP archive)
├── [Content_Types].xml                 # Declares MIME types for file extensions and part paths
├── _rels/
│   └── .rels                           # Package-level relationships to visio/document.xml and docProps/*
├── docProps/
│   ├── app.xml                         # Extended application properties (Application, AppVersion)
│   ├── core.xml                        # Dublin Core metadata (title, creator, language, etc.)
│   └── custom.xml                      # Custom document properties
└── visio/
    ├── document.xml                    # Main drawing document: settings, color palette, fonts, stylesheets
    ├── windows.xml                     # Window view state
    ├── _rels/
    │   └── document.xml.rels           # Links document.xml to masters.xml, pages.xml, and windows.xml
    ├── masters/
    │   ├── masters.xml                 # Master catalog (e.g. ID="4" NameU="Dynamic connector")
    │   ├── master1.xml                 # Prototype shapes and ShapeSheet formulas for a master
    │   └── _rels/
    │       └── masters.xml.rels        # Maps entries in masters.xml to master1.xml
    ├── pages/
    │   ├── pages.xml                   # Page index: lists each Page, dimensions, layers, and r:id
    │   ├── page1.xml                   # Page 1 drawing contents: Shapes and Connects
    │   ├── page2.xml                   # Additional pages in multi-page files (e.g. 08-multi-page-handbook.vsdx)
    │   └── _rels/
    │       ├── pages.xml.rels          # Maps r:id references in pages.xml to page1.xml, page2.xml, ...
    │       └── page1.xml.rels          # Page-level relationships (e.g. master1.xml, ../media/image1.png)
    └── media/                          # Present when images are embedded (e.g. 09-embedded-media-icons.vsdx)
        ├── image1.png
        └── ...
```

You can list the package contents of any sample directly from a terminal:

```bash
unzip -l samples/09-embedded-media-icons.vsdx
```

---

## 2. Core Parts and Their Responsibilities

### 2.1 `[Content_Types].xml` and `_rels/*.rels` (OPC Addressing Layer)

- **`[Content_Types].xml`**: Required at the root of every OPC package. It maps generic file extensions via `<Default Extension="..." ContentType="..."/>` (`rels`, `xml`, `png`, etc.) and declares Visio-specific part types via `<Override PartName="..." ContentType="..."/>`:
  - `/visio/document.xml` → `application/vnd.ms-visio.drawing.main+xml`
  - `/visio/pages/pages.xml` → `application/vnd.ms-visio.pages+xml`
  - `/visio/pages/page1.xml` → `application/vnd.ms-visio.page+xml`
  - `/visio/masters/masters.xml` → `application/vnd.ms-visio.masters+xml`
  - `/visio/masters/master1.xml` → `application/vnd.ms-visio.master+xml`
- **`_rels/.rels` and per-folder `_rels/*.rels`**: Instead of relying on hardcoded file names, OPC parts reference one another through `<Relationship Id="rId..." Type="..." Target="..."/>` entries:
  1. `_rels/.rels` points to `visio/document.xml` (relationship type ending in `/relationships/document`) and the `docProps/` metadata files.
  2. `visio/_rels/document.xml.rels` links `visio/document.xml` to `pages/pages.xml`, `masters/masters.xml`, and `windows.xml`.
  3. `visio/pages/_rels/pages.xml.rels` resolves each `<Page>`'s `<Rel r:id="..."/>` to `page1.xml`, `page2.xml`, and so on.

### 2.2 `visio/document.xml` (Document-Wide Definitions)

Rooted at `<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main">`, this file stores shared settings across the entire drawing rather than individual canvas shapes:

- `<DocumentSettings>`: Glue behavior (`GlueSettings`), snap/grid flags (`SnapSettings`, `DynamicGridEnabled`), and protection flags.
- `<Colors>`: Indexed `<ColorEntry IX="..." RGB="#RRGGBB"/>` palette entries.
- `<FaceNames>`: Font family declarations referenced by character styles.
- `<StyleSheets>`: Document-level line, fill, and text style definitions.

### 2.3 `visio/pages/pages.xml` and `visio/pages/pageN.xml` (Pages, Shapes, and Glue)

- **`visio/pages/pages.xml`**: Ordered manifest of pages in the document. Each `<Page ID="..." Name="..." NameU="...">` contains:
  - `<PageSheet>`: Page-level cells including `<Cell N="PageWidth" V="..."/>` and `<Cell N="PageHeight" V="..."/>` (Visio stores internal coordinates in **inches**) plus `<Section N="Layer">` definitions.
  - `<Rel r:id="rId1"/>`: Resolved through `pages.xml.rels` to locate `page1.xml`.

- **`visio/pages/pageN.xml`**: Rooted at `<PageContents>`, holding the drawing elements on that page:
  1. **`<Shapes>` (2D Shapes and 1D Connectors)**: Every visual object on the canvas is a `<Shape ID="..." NameU="..." Type="Shape">` element:
     - **2D shapes (nodes, group containers, title blocks)**: Positioned via `<Cell N="PinX">`, `<Cell N="PinY">`, `<Cell N="Width">`, and `<Cell N="Height">` (in inches), with path geometry in `<Section N="Geometry">` (`RelMoveTo`, `RelLineTo`, etc.) and styling cells such as `<Cell N="FillForegnd">` and `<Cell N="LineColor">`.
     - **1D connectors**: Also represented as `<Shape>` elements, distinguished by endpoint cells `<Cell N="BeginX">`, `<Cell N="BeginY">`, `<Cell N="EndX">`, and `<Cell N="EndY">`, typically carrying `Master="4"` to inherit routing behavior from the `Dynamic connector` master.
     - **Text labels (`<Text>`)**: Both node labels and edge labels (such as `yes` / `no`) live inside the `<Text>` child of their `<Shape>`, optionally interleaved with `<cp IX="..."/>` (character property) and `<pp IX="..."/>` (paragraph property) markers.
     - **Embedded bitmaps (`<ForeignData>`)**: As seen in [`09-embedded-media-icons.vsdx`](../samples/09-embedded-media-icons.vsdx), image shapes contain `<ForeignData ForeignType="Bitmap" CompressionType="PNG"><Rel r:id="rId2"/></ForeignData>`, which resolves via `visio/pages/_rels/page1.xml.rels` to `../media/image1.png`.
  2. **`<Connects>` (Connector Glue Table)**:
     ```xml
     <Connects>
       <Connect FromSheet="16" FromCell="BeginX" ToSheet="5"/>
       <Connect FromSheet="16" FromCell="EndX" ToSheet="7"/>
     </Connects>
     ```
     Each `<Connect>` entry records which connector shape (`FromSheet="16"`) has its start (`BeginX`) or end (`EndX`) glued to a target shape (`ToSheet="5"` / `ToSheet="7"`), allowing connectors to stay attached when shapes are moved.

### 2.4 `visio/masters/` (Stencil Masters)

- **`visio/masters/masters.xml`**: Lists the master definitions embedded in the document (`ID`, `Name`, `NameU`, etc.) and links each entry via `<Rel r:id="..."/>` to a `masterN.xml` part.
- **`visio/masters/master1.xml`**: Rooted at `<MasterContents>`, storing prototype `<Shapes>` and ShapeSheet formulas (such as `GUARD` expressions on `Dynamic connector`). Shapes on a page with `Master="4"` inherit from this prototype and override only per-instance cells.

---

## 3. `.vsdx` vs. Legacy Binary `.vsd`

| Aspect | `.vsdx` (Visio 2013 and later) | `.vsd` (Visio 2003–2010 and earlier) |
| --- | --- | --- |
| **Container** | Standard ZIP archive (Open Packaging Conventions), magic bytes `50 4B 03 04` (`PK\x03\x04`) | OLE2 Compound File Binary container, magic bytes `D0 CF 11 E0 A1 B1 1A E1` |
| **Internal Representation** | Separate UTF-8 XML parts (`document.xml`, `page1.xml`, `masters.xml`, etc.) | Proprietary binary streams, record chunks, and offset pointer trees |
| **Inspectability** | Directly readable with `unzip` and standard libraries (`zipfile` + `xml.etree` in Python) | Cannot be unpacked with ZIP tools; requires a dedicated binary `.vsd` parser |
| **Embedded Media** | Stored as standalone image files under `visio/media/` and linked via `.rels` | Packed inside binary streams |

---

## 4. Verifying the Samples from the Command Line

[`tools/inspect_vsdx.py`](../tools/inspect_vsdx.py) uses only Python's standard library (`zipfile` + `xml.etree.ElementTree`) to walk the OPC relationships described above:

```bash
# Inspect pages, shape counts, connector counts, text labels, and masters
python3 tools/inspect_vsdx.py samples/08-multi-page-handbook.vsdx

# Emit machine-readable JSON for parser or converter test suites
python3 tools/inspect_vsdx.py --json samples/09-embedded-media-icons.vsdx
```
