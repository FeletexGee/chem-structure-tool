/**
 * ============================================================
 * ChemStructure Tool — 前端交互逻辑
 * ============================================================
 */

// ── 全局状态 ───────────────────────────────────────────────

const state = {
    currentSmiles: null,
    currentPdbData: null,
    showAtomIndices: false,
    viewer3d: null,
};

// ── DOM 元素缓存 ──────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
    // 输入
    textInput: $("#text-input"),
    btnParseText: $("#btn-parse-text"),
    textStatus: $("#text-status"),
    // 图片
    uploadZone: $("#upload-zone"),
    imageInput: $("#image-input"),
    btnUpload: $("#btn-upload"),
    imagePreview: $("#image-preview"),
    previewImg: $("#preview-img"),
    btnParseImage: $("#btn-parse-image"),
    btnClearImage: $("#btn-clear-image"),
    imageStatus: $("#image-status"),
    // 结果
    resultSection: $("#result-section"),
    moleculeInfo: $("#molecule-info"),
    validationInfo: $("#validation-info"),
    render2dArea: $("#render-2d-area"),
    viewer3d: $("#viewer-3d"),
    exportOutput: $("#export-output"),
    // 加载
    loadingOverlay: $("#loading-overlay"),
};

// ── 工具函数 ───────────────────────────────────────────────

function showLoading() { dom.loadingOverlay.style.display = "flex"; }
function hideLoading() { dom.loadingOverlay.style.display = "none"; }

function showStatus(el, type, msg) {
    el.className = `status-msg ${type}`;
    el.textContent = msg;
    el.style.display = "block";
}

function hideStatus(el) {
    el.style.display = "none";
    el.className = "status-msg";
}

/**
 * 调用 API 并处理错误
 */
async function apiCall(url, options = {}) {
    const defaultOpts = {
        headers: { "Content-Type": "application/json" },
    };
    const resp = await fetch(url, { ...defaultOpts, ...options });
    const data = await resp.json();
    if (!resp.ok && !data.success) {
        throw new Error(data.error || `HTTP ${resp.status}`);
    }
    return data;
}

// ── 选项卡切换 ─────────────────────────────────────────────

document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        const tabName = btn.dataset.tab;
        // 切换按钮状态
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        // 切换面板
        document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
        $(`#panel-${tabName}`).classList.add("active");
    });
});

// ── 示例链接 ───────────────────────────────────────────────

document.querySelectorAll(".example-link").forEach((link) => {
    link.addEventListener("click", (e) => {
        e.preventDefault();
        dom.textInput.value = link.dataset.text;
        parseText();
    });
});

// ── 文本解析 ───────────────────────────────────────────────

dom.btnParseText.addEventListener("click", parseText);
dom.textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") parseText();
});

async function parseText() {
    const userInput = dom.textInput.value.trim();
    if (!userInput) {
        showStatus(dom.textStatus, "error", "请输入化学名称、分子式或 SMILES");
        return;
    }

    hideStatus(dom.textStatus);
    showLoading();

    try {
        const data = await apiCall("/api/process", {
            method: "POST",
            body: JSON.stringify({ input: userInput }),
        });

        if (!data.success) {
            throw new Error(data.error || "解析失败");
        }

        state.currentSmiles = data.smiles;
        state.currentPdbData = data.pdb_data;

        showStatus(dom.textStatus, "success",
            `✅ 解析成功 — 来源: ${data.source || "未知"}, SMILES: ${data.smiles}`);

        // 渲染所有结果
        renderResults(data);
    } catch (err) {
        showStatus(dom.textStatus, "error", `❌ ${err.message}`);
    } finally {
        hideLoading();
    }
}

// ── 图片上传 ───────────────────────────────────────────────

dom.btnUpload.addEventListener("click", () => dom.imageInput.click());

dom.imageInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) handleImageFile(file);
});

// 拖拽上传
dom.uploadZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dom.uploadZone.classList.add("drag-over");
});

dom.uploadZone.addEventListener("dragleave", () => {
    dom.uploadZone.classList.remove("drag-over");
});

dom.uploadZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dom.uploadZone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) handleImageFile(file);
});

// 粘贴板粘贴
document.addEventListener("paste", (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of items) {
        if (item.type.startsWith("image/")) {
            e.preventDefault();
            const file = item.getAsFile();
            handleImageFile(file);
            return;
        }
    }
});

let currentImageFile = null;

function handleImageFile(file) {
    currentImageFile = file;
    const reader = new FileReader();
    reader.onload = (e) => {
        dom.previewImg.src = e.target.result;
        dom.uploadZone.style.display = "none";
        dom.imagePreview.style.display = "block";
    };
    reader.readAsDataURL(file);
}

dom.btnClearImage.addEventListener("click", () => {
    currentImageFile = null;
    dom.imageInput.value = "";
    dom.uploadZone.style.display = "block";
    dom.imagePreview.style.display = "none";
    hideStatus(dom.imageStatus);
});

dom.btnParseImage.addEventListener("click", parseImage);

async function parseImage() {
    if (!currentImageFile) {
        showStatus(dom.imageStatus, "error", "请先选择或拖拽上传图片");
        return;
    }

    hideStatus(dom.imageStatus);
    showLoading();

    try {
        const formData = new FormData();
        formData.append("image", currentImageFile);

        const resp = await fetch("/api/parse-image", {
            method: "POST",
            body: formData,
        });
        const data = await resp.json();

        if (!data.success) {
            throw new Error(data.error || "图像识别失败");
        }

        state.currentSmiles = data.smiles;

        showStatus(dom.imageStatus, "success",
            `✅ 识别成功 — 工具: ${data.source || "未知"}, SMILES: ${data.smiles}`);

        // 转换到文本输入面板并显示结果
        dom.textInput.value = data.smiles;

        // 获取完整的处理结果
        const processData = await apiCall("/api/process", {
            method: "POST",
            body: JSON.stringify({ input: data.smiles }),
        });
        state.currentPdbData = processData.pdb_data;
        renderResults(processData);
    } catch (err) {
        showStatus(dom.imageStatus, "error", `❌ ${err.message}`);
    } finally {
        hideLoading();
    }
}

// ── 结果渲染 ───────────────────────────────────────────────

function renderResults(data) {
    dom.resultSection.style.display = "block";
    dom.resultSection.scrollIntoView({ behavior: "smooth" });

    // 分子信息
    renderMoleculeInfo(data.molecule_info);

    // 结构校验
    renderValidation(data.validation);

    // 2D 渲染
    render2D(data.image_2d_base64, data.smiles);

    // 3D 渲染
    if (data.pdb_data) {
        render3D(data.pdb_data);
    }

    // 滚动到结果区
    dom.resultSection.scrollIntoView({ behavior: "smooth" });
}

function renderMoleculeInfo(info) {
    if (!info || info.error) {
        dom.moleculeInfo.innerHTML = `<p class="placeholder-text">暂无信息</p>`;
        return;
    }

    const fields = [
        ["分子式", "formula"],
        ["分子量", "molecular_weight"],
        ["原子数", "num_atoms"],
        ["化学键数", "num_bonds"],
        ["环数", "num_rings"],
        ["LogP", "logP"],
        ["氢键受体", "h_bond_acceptors"],
        ["氢键供体", "h_bond_donors"],
        ["可旋转键", "rotatable_bonds"],
        ["TPSA", "TPSA"],
    ];

    let html = '<div class="info-grid">';
    for (const [label, key] of fields) {
        const val = info[key] !== undefined ? info[key] : "—";
        html += `
            <div class="info-item">
                <span class="info-label">${label}</span>
                <span class="info-value">${val}</span>
            </div>`;
    }
    html += "</div>";
    dom.moleculeInfo.innerHTML = html;
}

function renderValidation(validation) {
    if (!validation) {
        dom.validationInfo.innerHTML = `<p class="placeholder-text">暂无校验信息</p>`;
        return;
    }

    let html = "";
    if (validation.valid) {
        html += '<p style="color:var(--success)">✅ 结构校验通过</p>';
    } else {
        html += '<p style="color:var(--danger)">❌ 结构校验未通过</p>';
        if (validation.issues) {
            html += "<ul>";
            validation.issues.forEach((i) => { html += `<li>${i}</li>`; });
            html += "</ul>";
        }
    }
    if (validation.warnings && validation.warnings.length > 0) {
        html += '<p style="color:var(--warning); margin-top:0.5rem;">⚠️ 警告：</p><ul>';
        validation.warnings.forEach((w) => { html += `<li>${w}</li>`; });
        html += "</ul>";
    }
    dom.validationInfo.innerHTML = html;
}

function render2D(imageBase64, smiles) {
    if (!imageBase64) {
        dom.render2dArea.innerHTML = `<p class="placeholder-text">2D 渲染失败</p>`;
        return;
    }

    dom.render2dArea.innerHTML = `
        <img src="data:image/png;base64,${imageBase64}"
             alt="2D Structure"
             style="max-width:100%; height:auto;">
    `;
}

// ── 3D 渲染 (3Dmol.js) ──────────────────────────────────────

function render3D(pdbData) {
    // 清除旧 viewer
    if (state.viewer3d) {
        state.viewer3d.clear();
        state.viewer3d = null;
    }

    // 确保容器可见且有尺寸
    const container = dom.viewer3d;
    container.innerHTML = "";

    try {
        const viewer = $3Dmol.createViewer(container, {
            backgroundColor: "white",
        });

        viewer.addModel(pdbData, "pdb");
        viewer.setStyle({}, { stick: { radius: 0.2 }, sphere: { scale: 0.3 } });
        viewer.zoomTo();
        viewer.render();

        state.viewer3d = viewer;
    } catch (err) {
        console.error("3D 渲染失败:", err);
        container.innerHTML = `<p class="placeholder-text">3D 渲染失败: ${err.message}</p>`;
    }
}

// 3D 样式切换按钮
$("#btn-style-stick").addEventListener("click", () => {
    if (!state.viewer3d) return;
    state.viewer3d.setStyle({}, { stick: { radius: 0.2 }, sphere: { scale: 0.3 } });
    state.viewer3d.render();
});

$("#btn-style-sphere").addEventListener("click", () => {
    if (!state.viewer3d) return;
    state.viewer3d.setStyle({}, { sphere: { scale: 1.0 } });
    state.viewer3d.render();
});

$("#btn-style-line").addEventListener("click", () => {
    if (!state.viewer3d) return;
    state.viewer3d.setStyle({}, { line: {} });
    state.viewer3d.render();
});

$("#btn-style-cartoon").addEventListener("click", () => {
    if (!state.viewer3d) return;
    state.viewer3d.setStyle({}, { cartoon: {} });
    state.viewer3d.render();
});

// ── 2D 控制 ─────────────────────────────────────────────────

$("#btn-toggle-indices").addEventListener("click", async () => {
    if (!state.currentSmiles) return;
    state.showAtomIndices = !state.showAtomIndices;

    showLoading();
    try {
        const data = await apiCall("/api/render-2d", {
            method: "POST",
            body: JSON.stringify({
                smiles: state.currentSmiles,
                show_indices: state.showAtomIndices,
            }),
        });
        if (data.success) {
            render2D(data.image_base64);
        }
    } catch (err) {
        console.error("切换原子编号失败:", err);
    } finally {
        hideLoading();
    }
});

// ── 下载功能 ────────────────────────────────────────────────

function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

$("#btn-download-png").addEventListener("click", async () => {
    if (!state.currentSmiles) return;
    try {
        const data = await apiCall("/api/render-2d", {
            method: "POST",
            body: JSON.stringify({ smiles: state.currentSmiles, format: "PNG" }),
        });
        if (data.success) {
            const byteChars = atob(data.image_base64);
            const byteNums = new Array(byteChars.length);
            for (let i = 0; i < byteChars.length; i++) {
                byteNums[i] = byteChars.charCodeAt(i);
            }
            const byteArr = new Uint8Array(byteNums);
            downloadFile(byteArr, `structure_${Date.now()}.png`, "image/png");
        }
    } catch (err) {
        console.error("下载 PNG 失败:", err);
    }
});

$("#btn-download-svg").addEventListener("click", async () => {
    if (!state.currentSmiles) return;
    try {
        const data = await apiCall("/api/render-2d", {
            method: "POST",
            body: JSON.stringify({ smiles: state.currentSmiles, format: "SVG" }),
        });
        if (data.success) {
            const svgText = atob(data.image_base64);
            downloadFile(svgText, `structure_${Date.now()}.svg`, "image/svg+xml");
        }
    } catch (err) {
        console.error("下载 SVG 失败:", err);
    }
});

$("#btn-download-pdb").addEventListener("click", () => {
    if (!state.currentPdbData) return;
    downloadFile(state.currentPdbData, `structure_${Date.now()}.pdb`, "chemical/x-pdb");
});

// ── 导出格式 ────────────────────────────────────────────────

document.querySelectorAll(".export-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
        if (!state.currentSmiles) return;
        const format = btn.dataset.format;

        showLoading();
        try {
            const data = await apiCall("/api/export", {
                method: "POST",
                body: JSON.stringify({ smiles: state.currentSmiles, format: format }),
            });
            if (data.success) {
                dom.exportOutput.style.display = "block";
                dom.exportOutput.textContent = data.data;
            }
        } catch (err) {
            dom.exportOutput.style.display = "block";
            dom.exportOutput.textContent = `导出失败: ${err.message}`;
        } finally {
            hideLoading();
        }
    });
});

// ── 初始化 ──────────────────────────────────────────────────

console.log("🧪 ChemStructure Tool 前端已就绪");
console.log("   RDKit + OPSIN + DECIMER + 3Dmol.js");
