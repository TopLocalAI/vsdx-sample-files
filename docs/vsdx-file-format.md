# `.vsdx` 文件格式结构说明

[English](vsdx-file-format.en.md) | 简体中文

`.vsdx` 是 Microsoft Visio 自 Visio 2013 起采用的默认绘图文件格式。它遵循 **Open Packaging Conventions（OPC，开放打包约定，ECMA-376 / ISO/IEC 29500-2）**，本质上是一个包含多个 UTF-8 XML 部件和媒体资源的 **ZIP 压缩包**（文件头前 4 个字节为标准 ZIP 签名 `50 4B 03 04`）。

本文中的所有路径、元素名与属性均直接核对自本仓库 [`../samples/`](../samples/) 目录下的真实 `.vsdx` 样例文件，你可以直接用 `unzip` 或 [`../tools/inspect_vsdx.py`](../tools/inspect_vsdx.py) 解压验证。

---

## 1. 解压后的包目录结构

以单页流程图 [`01-basic-flowchart.vsdx`](../samples/01-basic-flowchart.vsdx)、多页文档 [`08-multi-page-handbook.vsdx`](../samples/08-multi-page-handbook.vsdx) 和含内嵌图标的 [`09-embedded-media-icons.vsdx`](../samples/09-embedded-media-icons.vsdx) 为例，解压后的目录树如下：

```text
example.vsdx (ZIP 归档)
├── [Content_Types].xml                 # 声明包内各扩展名与部件路径的 MIME 类型
├── _rels/
│   └── .rels                           # 根级关系表：指向 visio/document.xml 与 docProps/*
├── docProps/
│   ├── app.xml                         # 应用扩展属性（如 Application、AppVersion）
│   ├── core.xml                        # Dublin Core 核心元数据（标题、创建者、语言等）
│   └── custom.xml                      # 自定义文档属性
└── visio/
    ├── document.xml                    # 绘图主文档：全局设置、调色板、字体表、样式表
    ├── windows.xml                     # 视图窗口状态
    ├── _rels/
    │   └── document.xml.rels           # 主文档关系表：关联 masters.xml、pages.xml、windows.xml
    ├── masters/
    │   ├── masters.xml                 # 母版清单（如 ID="4" NameU="Dynamic connector"）
    │   ├── master1.xml                 # 单个母版的几何与公式原型定义
    │   └── _rels/
    │       └── masters.xml.rels        # 将 masters.xml 中的条目映射到 master1.xml
    ├── pages/
    │   ├── pages.xml                   # 页面索引：列出所有 Page 及其尺寸、图层和 r:id
    │   ├── page1.xml                   # 第 1 页内容：Shapes（形状与连接线）和 Connects（粘连关系）
    │   ├── page2.xml                   # 多页文档中的后续页面（如 08-multi-page-handbook.vsdx）
    │   └── _rels/
    │       ├── pages.xml.rels          # 将 pages.xml 中的 r:id 映射到 page1.xml、page2.xml…
    │       └── page1.xml.rels          # 单页引用的外部部件（如 master1.xml、../media/image1.png）
    └── media/                          # 仅当包含内嵌图片时存在（如 09-embedded-media-icons.vsdx）
        ├── image1.png
        └── ...
```

你可以直接在终端运行以下命令查看包内条目：

```bash
unzip -l samples/09-embedded-media-icons.vsdx
```

---

## 2. 主要部件职责说明

### 2.1 `[Content_Types].xml` 与 `_rels/.rels`（OPC 寻址层）

- **`[Content_Types].xml`**：OPC 包的必需入口文件。通过 `<Default Extension="..." ContentType="..."/>` 定义通用扩展名类型（如 `rels`、`xml`、`png`），并通过 `<Override PartName="..." ContentType="..."/>` 标记 Visio 专有部件类型：
  - `/visio/document.xml` → `application/vnd.ms-visio.drawing.main+xml`
  - `/visio/pages/pages.xml` → `application/vnd.ms-visio.pages+xml`
  - `/visio/pages/page1.xml` → `application/vnd.ms-visio.page+xml`
  - `/visio/masters/masters.xml` → `application/vnd.ms-visio.masters+xml`
  - `/visio/masters/master1.xml` → `application/vnd.ms-visio.master+xml`
- **`_rels/.rels`** 与各级 **`_rels/*.rels`**：OPC 不鼓励硬编码文件路径，而是通过 `<Relationship Id="rId..." Type="..." Target="..."/>` 建立有向引用：
  1. `_rels/.rels` 指向主文档 `visio/document.xml`（类型后缀 `/relationships/document`）及 `docProps/` 元数据。
  2. `visio/_rels/document.xml.rels` 从主文档指向 `pages/pages.xml`、`masters/masters.xml` 和 `windows.xml`。
  3. `visio/pages/_rels/pages.xml.rels` 从页面索引指向具体的 `page1.xml`、`page2.xml` 等。

### 2.2 `visio/document.xml`（绘图主文档）

根元素为 `<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main">`，管辖整份文档共享的全局定义，不包含具体页面上的图形：

- `<DocumentSettings>`：粘连（`GlueSettings`）、对齐网格（`SnapSettings`、`DynamicGridEnabled`）与保护开关。
- `<Colors>`：`<ColorEntry IX="..." RGB="#RRGGBB"/>` 调色板索引表。
- `<FaceNames>`：文档用到的字体声明列表。
- `<StyleSheets>`：线条、填充与文本的默认样式表链。

### 2.3 `visio/pages/pages.xml` 与 `visio/pages/pageN.xml`（页面与画布元素）

- **`visio/pages/pages.xml`**：按顺序定义文档中的所有页面。每个 `<Page ID="..." Name="..." NameU="...">` 包含：
  - `<PageSheet>`：记录页面级属性，如 `<Cell N="PageWidth" V="..."/>`、`<Cell N="PageHeight" V="..."/>`（Visio 内部长度单位为**英寸**）以及图层 `<Section N="Layer">`。
  - `<Rel r:id="rId1"/>`：结合 `pages.xml.rels` 定位到对应的 `page1.xml`。

- **`visio/pages/pageN.xml`**：根元素为 `<PageContents>`，存放该页的实际图元与连接拓扑：
  1. **`<Shapes>`（二维形状与一维连接线）**：所有可视元素均为 `<Shape ID="..." NameU="..." Type="Shape">`：
     - **普通二维形状（节点、分组容器、标题文本）**：通过 `<Cell N="PinX">`、`<Cell N="PinY">`、`<Cell N="Width">`、`<Cell N="Height">` 定义中心坐标与宽高（英寸），通过 `<Section N="Geometry">`（如 `RelMoveTo`、`RelLineTo` 等行）描述轮廓路径，通过 `<Cell N="FillForegnd">` / `<Cell N="LineColor">` 设置填色与描边。
     - **一维连接线（Connector）**：同样表示为 `<Shape>`，但带有 `<Cell N="BeginX">`、`<Cell N="BeginY">`、`<Cell N="EndX">`、`<Cell N="EndY">` 起点/终点单元格，并通常带有 `Master="4"` 属性以继承 `Dynamic connector` 母版的自动路由行为。
     - **文字（`<Text>`）**：无论是形状标签还是连接线上的分支文字（如 `yes` / `no`），都存放在对应 `<Shape>` 的 `<Text>` 子元素内（其中可含 `<cp IX="..."/>` 字符样式标记与 `<pp IX="..."/>` 段落样式标记）。
     - **内嵌位图（`<ForeignData>`）**：如 [`09-embedded-media-icons.vsdx`](../samples/09-embedded-media-icons.vsdx) 所示，图片形状内含 `<ForeignData ForeignType="Bitmap" CompressionType="PNG"><Rel r:id="rId2"/></ForeignData>`，通过 `visio/pages/_rels/page1.xml.rels` 解析到 `../media/image1.png`。
  2. **`<Connects>`（连接线吸附关系）**：
     ```xml
     <Connects>
       <Connect FromSheet="16" FromCell="BeginX" ToSheet="5"/>
       <Connect FromSheet="16" FromCell="EndX" ToSheet="7"/>
     </Connects>
     ```
     每条 `<Connect>` 记录连接线形状（`FromSheet="16"`）的起点（`BeginX`）或终点（`EndX`）粘连到了哪个目标形状（`ToSheet="5"` / `ToSheet="7"`）。编辑软件据此在拖动节点时让连接线自动跟随重排。

### 2.4 `visio/masters/`（母版 / Stencil Masters）

- **`visio/masters/masters.xml`**：列出文档内嵌的所有母版元数据（`ID`、`Name`、`NameU` 等），并通过 `<Rel r:id="..."/>` 关联到具体的 `master1.xml`。
- **`visio/masters/master1.xml`**：根元素为 `<MasterContents>`，保存母版的原型 `<Shapes>` 与 ShapeSheet 公式（如 `Dynamic connector` 的 `GUARD` 表达式和动态路由控制）。页面中的 `<Shape Master="4">` 只需写入覆盖属性即可复用母版定义，减小文件体积并保持行为一致。

---

## 3. `.vsdx` 与旧版二进制 `.vsd` 的区别

| 维度 | `.vsdx`（Visio 2013 及以后） | `.vsd`（Visio 2003–2010 及更早） |
| --- | --- | --- |
| **容器格式** | 标准 ZIP 压缩包（OPC 开放打包约定），文件头为 `50 4B 03 04`（`PK\x03\x04`） | Microsoft 复合文档二进制格式（OLE2 / Compound File），文件头为 `D0 CF 11 E0 A1 B1 1A E1` |
| **内部表示** | 分部件存储的 UTF-8 XML 文件（`document.xml`、`page1.xml`、`masters.xml` 等） | 专有二进制记录块、流（Streams）与偏移指针树 |
| **可读性与调试** | 可直接用 `unzip` 解压阅读 XML，用 Python 标准库 `zipfile` + `xml.etree` 即可提取页面、形状、连线和文字 | 无法用普通解压工具打开，需专用二进制解析库解码记录结构 |
| **内嵌图片资源** | 作为独立图片文件存放在 `visio/media/` 目录下，通过 `.rels` 关联 | 编码封装在二进制流内部 |

---

## 4. 用 Python 标准库快速核对样例

本仓库提供的 [`tools/inspect_vsdx.py`](../tools/inspect_vsdx.py) 仅依赖 Python 标准库 `zipfile` 与 `xml.etree.ElementTree`，按上述 OPC 关系链读取 `.vsdx`：

```bash
# 查看多页样例的页面、形状数、连接线数、文字和母版引用
python3 tools/inspect_vsdx.py samples/08-multi-page-handbook.vsdx

# 输出结构化 JSON 以便集成到自动化测试脚本
python3 tools/inspect_vsdx.py --json samples/09-embedded-media-icons.vsdx
```
