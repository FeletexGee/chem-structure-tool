<p align="center">
  <h1 align="center">🧪 ChemStructure Tool</h1>
  <p align="center"><strong>化学结构智能生成工具</strong> — 面向化学教学场景，多种输入一键生成标准化学结构图</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.0+-green.svg" alt="Flask">
  <img src="https://img.shields.io/badge/RDKit-2024.03+-red.svg" alt="RDKit">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

---

## 📖 项目背景

当前通用生成式 AI（如 ChatGPT、Midjourney）**无法准确绘制化学分子结构**——这是化学教育领域的一大痛点。教师备课时使用 ChemDraw 等专业工具操作复杂、耗时长，学生自学时难以绘制复杂分子的键线式和三维结构。

**ChemStructure Tool** 针对这一痛点，集成多个成熟的开源化学信息学工具，提供 **"输入即所得"** 的极简体验：只需输入化学名称、分子式或上传结构图片，即可一键生成标准、准确的 2D 结构图和 3D 球棍模型。

> **设计哲学**：化学准确性 > AI 炫技。项目使用 **确定性算法**（OPSIN 文法解析 + RDKit 化学规则校验）保证结构 100% 符合化学原理，同时可选接入 LLM 作为"名称翻译器"（只翻译名称、不生成结构），从根源避免 AI 幻觉。

---

## ✨ 功能特性

### 输入方式
| 方式 | 说明 | 状态 |
|------|------|------|
| ✏️ IUPAC 命名 | 如 `1,3,7-trimethylpurine-2,6-dione` | ✅ |
| 📛 通用名称 | 如 `caffeine`、`aspirin` | ✅ |
| 🔢 分子式 | 如 `C6H12O6`、`C2H5OH` | ✅ |
| 🧬 SMILES | 如 `CC(=O)Oc1ccccc1C(=O)O` | ✅ |
| 📷 结构图片 | 拍照/截图/文献图 → 自动识别为 SMILES | ✅ |
| ✍️ 手绘结构 | 手绘化学结构 → AI 识别 | ✅ |
| 🤖 LLM 辅助 | 俗名/中文名 → IUPAC 名（需要 DeepSeek API Key） | 🔧 |

### 输出能力
| 输出 | 技术 | 
|------|------|
| 🔬 **2D 结构图**（键线式/结构式/含原子编号） | RDKit Draw (PNG/SVG) |
| 🧬 **3D 球棍模型**（可旋转/缩放/切换样式） | RDKit ETKDG + 3Dmol.js |
| ⚽ **空间填充模型** | 3Dmol.js sphere style |
| 📋 **分子信息**（分子式/分子量/LogP/氢键供受体/TPSA...） | RDKit Descriptors |
| ✅ **结构校验**（价键合理性检查） | RDKit |
| 📦 **多格式导出** | MOL / SDF / PDB / InChI / SMILES / PNG / SVG |

---

## 🏗️ 技术架构

```
用户输入（名称 / 分子式 / 图片 / 自然语言）
         │
    ┌────┴────────────────────┐
    │                         │
    ▼ 文本通道                ▼ 图像通道 (OCSR)
┌──────────────┐      ┌──────────────────┐
│ OPSIN API    │      │ DECIMER          │
│ PubChem API  │      │ (EfficientNet-V2 │
│ RDKit 验证   │      │  + Transformer)  │
└──────┬───────┘      │ Img2Mol (备选)   │
       │              └────────┬─────────┘
       └──────────┬────────────┘
                  ▼
          统一输出: SMILES
                  │
                  ▼
        ┌─────────────────┐
        │  RDKit 结构处理   │
        │  · 2D 坐标生成   │
        │  · 3D 构象优化   │
        │  · 化学规则校验   │
        └────────┬────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
  2D 结构图              3D 模型
  (PNG/SVG)              (PDB → 3Dmol.js)
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端框架 | **Flask 3** | 轻量 Python Web 框架 |
| 化学信息学 | **RDKit** | 行业标准开源 cheminformatics 库 |
| 名称→结构 | **OPSIN API** | 剑桥大学/EMBL-EBI IUPAC 解析服务 |
| 数据库查询 | **PubChem API** | NIH 化合物数据库 REST 接口 |
| 图像→结构 | **DECIMER** | Nature Comms 2023, EfficientNet-V2 + Transformer |
| 2D 渲染 | **RDKit Draw** | 键线式/结构式矢量图 |
| 3D 渲染 | **3Dmol.js** | WebGL 分子可视化（球棍/空间填充/线型） |
| LLM 辅助 | **DeepSeek** | 俗名→IUPAC 名称翻译（可选，避免幻觉） |
| 前端 | **原生 HTML/CSS/JS** | 零依赖，响应式设计 |

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- RDKit（推荐 conda 安装）

### 安装

```bash
# 1. 克隆项目
git clone <repo-url>
cd chem-structure-tool

# 2. 安装 RDKit
conda install -c conda-forge rdkit

# 3. 安装 Python 依赖
pip install -r requirements.txt

# 4. （可选）启用 LLM 辅助名称解析
# Windows PowerShell:
$env:DEEPSEEK_API_KEY = "sk-xxxxxxxxxxxxxxxx"
# Linux/macOS:
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"

# 5. （可选）启用图像识别
pip install decimer

# 6. 启动服务
python app.py
```

浏览器访问 **http://127.0.0.1:5000**

---

## 📡 API 端点

| 方法 | 路由 | 功能 |
|------|------|------|
| `GET` | `/` | 主页面 |
| `POST` | `/api/process` | 🔥 一键处理（文本→全部结果） |
| `POST` | `/api/parse-text` | 文本→SMILES |
| `POST` | `/api/parse-image` | 图片→SMILES |
| `POST` | `/api/render-2d` | 生成 2D 结构图 |
| `POST` | `/api/render-3d` | 生成 3D 构象 (PDB) |
| `POST` | `/api/molecule-info` | 分子属性查询 |
| `POST` | `/api/export` | 多格式导出 |

### 示例请求

```bash
# 文本解析
curl -X POST http://127.0.0.1:5000/api/process \
  -H "Content-Type: application/json" \
  -d '{"input": "caffeine"}'

# 图像识别
curl -X POST http://127.0.0.1:5000/api/parse-image \
  -F "image=@structure.png"
```

---

## 📁 项目结构

```
chem-structure-tool/
├── app.py                      # Flask 主应用（7 个 API 路由）
├── config.py                   # 全局配置
├── requirements.txt            # Python 依赖
├── .gitignore                  # Git 忽略规则
├── README.md                   # 项目文档
├── modules/
│   ├── __init__.py
│   ├── text_parser.py          # 文本解析模块
│   │   ├── OPSIN API（IUPAC→SMILES）
│   │   ├── PubChem API（名称/分子式→SMILES）
│   │   └── SMILES 验证与规范化
│   ├── llm_name_resolver.py    # LLM 名称翻译模块
│   │   └── DeepSeek（俗名→IUPAC 名）
│   ├── image_parser.py         # 图像识别模块 (OCSR)
│   │   ├── DECIMER（EfficientNet-V2 + Transformer）
│   │   └── Img2Mol（CNN + CDDD Decoder，备选）
│   └── structure_processor.py  # 结构处理与渲染模块
│       ├── SMILES→2D 结构图 (PNG/SVG)
│       ├── SMILES→3D 构象 (PDB)
│       ├── 分子信息提取
│       ├── 化学规则校验
│       └── 多格式导出
├── static/
│   ├── css/
│   │   └── style.css           # 响应式样式
│   └── js/
│       └── main.js             # 前端交互逻辑
├── templates/
│   └── index.html              # 主页面模板
└── uploads/                    # 用户上传图片临时目录
```

---

## 🔬 解析流程详解

输入 `aspirin` 时的解析链路：

```
aspirin
  ├─ 1. SMILES 直解 ───────── ❌ 不是有效 SMILES
  ├─ 2. 分子式匹配 ───────── ❌ 不符合分子式格式
  ├─ 3. OPSIN IUPAC ─────── ❌ aspirin 是俗名非 IUPAC 名
  ├─ 4. PubChem 名称查询 ── ✅ CID 2244 → SMILES CC(=O)Oc1ccccc1C(=O)O
  └─ 5. LLM 辅助 (需 Key) ─ (已在前序步骤成功，跳过)
```

输入 `C6H12O6` 时的解析链路：

```
C6H12O6
  ├─ 1. SMILES 直解 ───────── ❌ 不是有效 SMILES
  ├─ 2. 分子式匹配 ───────── ✅ PubChem fastformula → 葡萄糖 SMILES
  └─ ...
```

---

## 🤖 LLM 辅助解析（可选）

当 PubChem 和 OPSIN 均无法解析时，可启用 DeepSeek 作为兜底：

```
用户输入 "维生素C"
  → DeepSeek 翻译 → "(5R)-5-[(1S)-1,2-dihydroxyethyl]-3,4-dihydroxyfuran-2(5H)-one"
  → OPSIN 解析 → SMILES ✅
```

**为何避免幻觉？** LLM 只做**名称翻译**，结构仍由 OPSIN（基于语法规则，非概率模型）确定性生成。Nature Reviews Chemistry (2025) 明确指出化学家应禁止用生成式 AI 直接绘制分子图。

配置方式：
```bash
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"
```

---

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE) 文件。

本项目集成了以下开源项目：
- [RDKit](https://github.com/rdkit/rdkit) — BSD License
- [OPSIN](https://github.com/dan2097/opsin) — MIT License
- [3Dmol.js](https://github.com/3dmol/3Dmol.js) — BSD License
- [DECIMER](https://github.com/Kohulan/DECIMER-Image_Transformer) — MIT License
- [Img2Mol](https://github.com/bayer-science-for-a-better-life/Img2Mol) — Apache 2.0

---

## 📚 参考文献

1. Rajan, K., et al. "DECIMER.ai: an open platform for automated optical chemical structure identification, segmentation and recognition in scientific publications." *Nature Communications*, 2023.
2. Clevert, D.A., et al. "Img2Mol – accurate SMILES recognition from molecular graphical depictions." *Chemical Science*, 2021.
3. Walden, J., et al. "Why chemists should ban generative AI for molecular images." *Nature Reviews Chemistry*, 2025.
4. Lowe, D.M. "OPSIN: Open Parser for Systematic IUPAC Nomenclature." University of Cambridge / EMBL-EBI.
5. Rego, N. & Koes, D. "3Dmol.js: molecular visualization with WebGL." *Bioinformatics*, 2015.
