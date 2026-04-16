/**
 * 药品管理系统 - 前端逻辑
 */

const API_BASE = '';  // 同域部署
let currentMedicines = [];
let currentDetailId = null;

// 分类标签映射
const categoryLabels = {
    internal: '内服',
    external: '外用',
    topical: '局部',
    supplement: '保健',
    other: '其他'
};

// 条形码扫描相关
let barcodeReader = null;
let isScanning = false;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadMedicines();
    loadStats();
});

// 事件监听
function initEventListeners() {
    // 扫码按钮
    document.getElementById('scanBtn').addEventListener('click', openScanModal);
    
    // 上传区域点击
    document.getElementById('uploadArea').addEventListener('click', () => {
        document.getElementById('imageInput').click();
    });
    
    // 文件选择
    document.getElementById('imageInput').addEventListener('change', handleImageSelect);
    
    // 搜索
    document.getElementById('searchInput').addEventListener('input', debounce(() => {
        loadMedicines();
    }, 300));
    
    // 分类过滤
    document.getElementById('categoryFilter').addEventListener('change', () => {
        loadMedicines();
    });
}

// 防抖函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 切换扫描模式
function switchScanMode(mode) {
    document.querySelectorAll('.scan-tab').forEach(tab => tab.classList.remove('active'));
    event.target.classList.add('active');
    
    if (mode === 'barcode') {
        document.getElementById('barcodeScanArea').style.display = 'block';
        document.getElementById('photoScanArea').style.display = 'none';
        stopBarcodeScan();
    } else {
        document.getElementById('barcodeScanArea').style.display = 'none';
        document.getElementById('photoScanArea').style.display = 'block';
        stopBarcodeScan();
    }
}

// 开始条形码扫描
async function startBarcodeScan() {
    try {
        const video = document.getElementById('barcodeVideo');
        const placeholder = document.getElementById('barcodePlaceholder');
        
        // 请求摄像头权限 - 尝试获取最佳条码扫描设置
        const constraints = {
            video: {
                facingMode: 'environment',
                width: { ideal: 1920 },
                height: { ideal: 1080 }
            }
        };
        
        // 尝试获取支持的约束
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        
        video.srcObject = stream;
        video.style.display = 'block';
        placeholder.style.display = 'none';
        
        await video.play();
        isScanning = true;
        
        // 尝试设置自动对焦
        const track = stream.getVideoTracks()[0];
        const capabilities = track.getCapabilities();
        
        if (capabilities.focusMode) {
            try {
                await track.applyConstraints({
                    advanced: [{ focusMode: 'continuous' }]
                });
            } catch (e) {
                console.log('自动对焦设置失败:', e);
            }
        }
        
        // 显示提示
        showToast('请将条码对准框内，保持稳定');
        
        // 开始解码
        decodeBarcode();
        
    } catch (error) {
        console.error('摄像头启动失败:', error);
        showToast('无法访问摄像头，请检查权限设置');
    }
}

// 解码条形码
async function decodeBarcode() {
    if (!isScanning) return;
    
    try {
        const video = document.getElementById('barcodeVideo');
        const canvas = document.getElementById('barcodeCanvas');
        const ctx = canvas.getContext('2d');
        
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // 使用 ZXing 解码
        const codeReader = new ZXing.BrowserMultiFormatReader();
        const result = await codeReader.decodeFromVideoElement(video);
        
        if (result) {
            // 识别成功
            stopBarcodeScan();
            document.getElementById('barcodeValue').textContent = result.text;
            document.getElementById('barcodeResult').style.display = 'block';
            showToast('条形码识别成功！');
        }
    } catch (error) {
        // 继续扫描
        if (isScanning) {
            requestAnimationFrame(decodeBarcode);
        }
    }
}

// 停止扫描
function stopBarcodeScan() {
    isScanning = false;
    const video = document.getElementById('barcodeVideo');
    if (video.srcObject) {
        video.srcObject.getTracks().forEach(track => track.stop());
        video.srcObject = null;
    }
    video.style.display = 'none';
    document.getElementById('barcodePlaceholder').style.display = 'block';
}

// 根据条形码查询药品
async function queryByBarcode() {
    const barcode = document.getElementById('barcodeValue').textContent;
    
    try {
        const response = await fetch(`/api/scan/barcode?code=${encodeURIComponent(barcode)}`);
        const result = await response.json();
        
        if (result.success) {
            // API 返回的数据在 drug_info 字段中
            const drugData = result.data?.drug_info || result.data || {};
            fillFormWithParsedData(drugData);
            // 隐藏扫码区域，切换到表单视图
            document.getElementById('barcodeScanArea').style.display = 'none';
            document.getElementById('photoScanArea').style.display = 'block';
            document.getElementById('uploadArea').style.display = 'none';
            document.getElementById('previewArea').style.display = 'none';
            // 显示结果表单
            document.getElementById('scanResult').style.display = 'block';
            document.getElementById('confirmBtn').style.display = 'inline-block';
            showToast('查询成功，请确认信息');
        } else {
            showToast(result.error || '未找到药品信息');
        }
    } catch (error) {
        console.error('查询失败:', error);
        showToast('查询失败，请手动输入');
    }
}

// 加载药品列表
async function loadMedicines() {
    const search = document.getElementById('searchInput').value;
    const category = document.getElementById('categoryFilter').value;
    
    let url = '/api/medicines?';
    if (search) url += `search=${encodeURIComponent(search)}&`;
    if (category) url += `category=${encodeURIComponent(category)}&`;
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        // 处理不同的返回格式
        let medicines = data;
        if (data && data.success && Array.isArray(data.data)) {
            medicines = data.data;
        } else if (!Array.isArray(data)) {
            showToast('数据格式错误');
            return;
        }
        
        currentMedicines = medicines;
        renderMedicineList(medicines);
    } catch (error) {
        showToast('加载失败: ' + error.message);
    }
}

// 渲染药品列表
function renderMedicineList(medicines) {
    const container = document.getElementById('medicineList');
    const emptyState = document.getElementById('emptyState');
    
    if (medicines.length === 0) {
        container.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }
    
    emptyState.style.display = 'none';
    
    console.log('渲染药品列表:', medicines.length, '条记录');
    
    container.innerHTML = medicines.map((med, index) => {
        const expiryStatus = med.expiry_status || 'unknown';
        const expiryClass = expiryStatus === 'expired' ? 'expired' : expiryStatus;
        const daysText = med.days_until_expiry !== null 
            ? (med.days_until_expiry < 0 
                ? `已过期 ${Math.abs(med.days_until_expiry)} 天` 
                : `还剩 ${med.days_until_expiry} 天`)
            : '未知';
        
        const rxBadge = med.is_prescription === true 
            ? '<span class="medicine-badge badge-rx">RX</span>'
            : med.is_prescription === false
                ? '<span class="medicine-badge badge-otc">OTC</span>'
                : '';
        
        const medId = med.id;
        if (!medId) {
            console.warn(`药品[${index}]缺少 ID:`, med);
            // 使用索引作为临时 ID，确保卡片可以显示
            return `
                <div class="medicine-card ${expiryClass}">
                    <div class="medicine-header">
                        <span class="medicine-name">${escapeHtml(med.name || '未命名药品')}</span>
                        <div>
                            ${rxBadge}
                            <span class="medicine-badge badge-category">${categoryLabels[med.category] || '其他'}</span>
                        </div>
                    </div>
                    <div class="medicine-info">
                        ${med.indications ? escapeHtml(med.indications.substring(0, 50)) + '...' : '暂无适应症信息'}
                    </div>
                    <div class="medicine-expiry">
                        <span>${med.manufacturer || '未知厂家'}</span>
                        <span class="expiry-tag ${expiryClass}">${daysText}</span>
                    </div>
                </div>
            `;
        }
        return `
            <div class="medicine-card ${expiryClass}" onclick="openDetailModal(${parseInt(medId)})">
                <div class="medicine-header">
                    <span class="medicine-name">${escapeHtml(med.name || '未命名药品')}</span>
                    <div>
                        ${rxBadge}
                        <span class="medicine-badge badge-category">${categoryLabels[med.category] || '其他'}</span>
                    </div>
                </div>
                <div class="medicine-info">
                    ${med.indications ? escapeHtml(med.indications.substring(0, 50)) + '...' : '暂无适应症信息'}
                </div>
                <div class="medicine-expiry">
                    <span>${med.manufacturer || '未知厂家'}</span>
                    <span class="expiry-tag ${expiryClass}">${daysText}</span>
                </div>
            </div>
        `;
    }).join('');
}

// 加载统计
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        document.getElementById('statTotal').textContent = stats.total;
        document.getElementById('statWarning').textContent = stats.expiring_soon;
        document.getElementById('statExpired').textContent = stats.expired;
    } catch (error) {
        console.error('加载统计失败:', error);
    }
}

// 打开扫描弹窗
function openScanModal() {
    // 关闭其他弹窗，避免重叠
    closeDetailModal();
    document.getElementById('scanModal').classList.add('active');
    resetScanModal();
}

// 关闭扫描弹窗
function closeScanModal() {
    document.getElementById('scanModal').classList.remove('active');
}

// 重置扫描弹窗
function resetScanModal() {
    // 重置区域显示状态 - 默认显示扫码区域
    document.getElementById('barcodeScanArea').style.display = 'block';
    document.getElementById('photoScanArea').style.display = 'none';
    
    // 重置拍照区域内部状态
    document.getElementById('uploadArea').style.display = 'block';
    document.getElementById('previewArea').style.display = 'none';
    document.getElementById('scanResult').style.display = 'none';
    document.getElementById('confirmBtn').style.display = 'none';
    document.getElementById('imageInput').value = '';
    
    // 重置扫码区域状态
    document.getElementById('barcodeResult').style.display = 'none';
    document.getElementById('barcodeValue').textContent = '';
    
    // 重置表单内容
    document.getElementById('medicineForm').reset();
    
    // 重置 tab 状态
    document.querySelectorAll('.scan-tab').forEach(tab => tab.classList.remove('active'));
    document.querySelector('.scan-tab:first-child').classList.add('active');
    
    // 停止摄像头
    stopBarcodeScan();
}

// 处理图片选择
async function handleImageSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    // 显示预览
    const reader = new FileReader();
    reader.onload = (event) => {
        document.getElementById('previewImage').src = event.target.result;
        document.getElementById('uploadArea').style.display = 'none';
        document.getElementById('previewArea').style.display = 'block';
    };
    reader.readAsDataURL(file);
    
    // 上传并识别
    await scanMedicine(file);
}

// 扫描识别
async function scanMedicine(file) {
    const formData = new FormData();
    formData.append('image', file);
    
    try {
        const response = await fetch('/api/scan', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            const data = result.data || {};
            fillFormWithParsedData(data.parsed || {});
            
            // 显示条码/追溯码识别结果
            let barcodeInfo = '';
            if (data.parsed && data.parsed.traceability_code) {
                barcodeInfo = `<div class="barcode-info success">
                    <p>✅ 识别到药品追溯码: <strong>${data.parsed.traceability_code}</strong></p>
                    <p class="hint">已自动填充到表单</p>
                </div>`;
            } else if (data.parsed && data.parsed.barcode) {
                barcodeInfo = `<div class="barcode-info">
                    <p>📦 识别到条形码: <strong>${data.parsed.barcode}</strong></p>
                </div>`;
            }
            
            // 显示追溯码/批准文号信息
            if (data.approval_lookup && data.approval_lookup.code) {
                const lookupInfo = document.getElementById('lookupInfo') || createLookupInfoElement();
                const codeType = data.approval_lookup.type === 'traceability' ? '追溯码' : '批准文号';
                lookupInfo.innerHTML = barcodeInfo + `
                    <div class="lookup-info">
                        <p>识别到${codeType}: <strong>${data.approval_lookup.code}</strong></p>
                        ${data.approval_lookup.query_info ? 
                            `<p>${data.approval_lookup.query_info.note || ''}</p>` : ''}
                        ${data.approval_lookup.search_urls ? 
                            `<a href="${data.approval_lookup.search_urls.nmpa}" target="_blank">查询药监局</a>` : ''}
                    </div>
                `;
            } else if (barcodeInfo) {
                // 只有条码信息时也要显示
                const lookupInfo = document.getElementById('lookupInfo') || createLookupInfoElement();
                lookupInfo.innerHTML = barcodeInfo;
            }
            
            document.getElementById('scanProgress').style.display = 'none';
            document.getElementById('scanResult').style.display = 'block';
            document.getElementById('confirmBtn').style.display = 'inline-block';
            
            // 如果有识别到条码，显示成功提示
            if (data.parsed && (data.parsed.traceability_code || data.parsed.barcode)) {
                showToast('条码识别成功！');
            }
        } else {
            showToast(result.error || '识别失败');
            document.getElementById('scanProgress').style.display = 'none';
            // 仍然显示表单，让用户手动输入
            document.getElementById('scanResult').style.display = 'block';
            document.getElementById('confirmBtn').style.display = 'inline-block';
        }
    } catch (error) {
        console.error('扫描失败:', error);
        showToast('识别失败，请重试');
        document.getElementById('scanProgress').style.display = 'none';
    }
}

// 创建查询信息元素
function createLookupInfoElement() {
    const infoDiv = document.createElement('div');
    infoDiv.id = 'lookupInfo';
    infoDiv.className = 'lookup-info-container';
    const form = document.getElementById('medicineForm');
    form.parentNode.insertBefore(infoDiv, form);
    return infoDiv;
}

// 安全设置表单字段值
function setFieldValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value || '';
}

// 填充表单
function fillFormWithParsedData(data) {
    // 基础字段
    setFieldValue('formName', data.name);
    setFieldValue('formIngredients', data.ingredients);
    setFieldValue('formIndications', data.indications || data.disease);
    setFieldValue('formCategory', data.category || 'other');
    
    // 处方药类型: 1=Rx, 2=OTC
    const prescription = data.prescription_type || data.prescription;
    const prescriptionEl = document.getElementById('formPrescription');
    if (prescriptionEl) {
        if (prescription === 1) {
            prescriptionEl.value = 'true';
        } else if (prescription === 2) {
            prescriptionEl.value = 'false';
        } else {
            prescriptionEl.value = '';
        }
    }
    
    setFieldValue('formExpiry', data.expiry_date);
    setFieldValue('formManufacturer', data.manufacturer);
    setFieldValue('formDosage', data.dosage);
    
    // API 返回的扩展字段 - 直接显示在表单中
    setFieldValue('formSpecification', data.specification || data.spec);
    setFieldValue('formDrugType', data.drug_type || data.type);
    setFieldValue('formDisease', data.disease);
    setFieldValue('formApprovalNumber', data.approval_number);
    setFieldValue('formBarcode', data.barcode);
    setFieldValue('formRetailPrice', data.retail_price);
    setFieldValue('formDescription', data.description || data.desc);
    
    // 从描述中解析的额外字段
    setFieldValue('formDosage', data.dosage);
    setFieldValue('formIngredients', data.ingredients);
    setFieldValue('formIndications', data.indications || data.disease);
    
    // 隐藏字段
    setFieldValue('formMedicineId', data.medicine_id);
    setFieldValue('formUnit', data.unit);
    setFieldValue('formDrugImage', data.drug_image || data.image);
    setFieldValue('formPrescriptionType', prescription || 0);
    
    // 同时存储到 dataset 供保存时使用（兼容旧代码）
    const form = document.getElementById('medicineForm');
    if (form) {
        form.dataset.medicineId = data.medicine_id || '';
        form.dataset.barcode = data.barcode || '';
        form.dataset.approvalNumber = data.approval_number || '';
        form.dataset.specification = data.specification || data.spec || '';
        form.dataset.drugType = data.drug_type || data.type || '';
        form.dataset.unit = data.unit || '';
        form.dataset.disease = data.disease || '';
        form.dataset.prescriptionType = prescription || 0;
        form.dataset.retailPrice = data.retail_price || '';
        form.dataset.drugImage = data.drug_image || data.image || '';
        form.dataset.description = data.description || data.desc || '';
    }
}

// 保存药品
async function saveMedicine() {
    const form = document.getElementById('medicineForm');
    const data = {
        name: document.getElementById('formName').value,
        ingredients: document.getElementById('formIngredients').value,
        indications: document.getElementById('formIndications').value,
        category: document.getElementById('formCategory').value,
        is_prescription: document.getElementById('formPrescription').value === 'true' 
            ? true 
            : document.getElementById('formPrescription').value === 'false' 
                ? false 
                : null,
        expiry_date: document.getElementById('formExpiry').value || null,
        manufacturer: document.getElementById('formManufacturer').value,
        dosage: document.getElementById('formDosage').value,
        notes: document.getElementById('formNotes')?.value || '',
        // 扩展字段（从 API 获取的）- 优先从隐藏字段读取，兼容 dataset
        medicine_id: document.getElementById('formMedicineId')?.value || form.dataset.medicineId || '',
        barcode: document.getElementById('formBarcode')?.value || form.dataset.barcode || '',
        approval_number: document.getElementById('formApprovalNumber')?.value || form.dataset.approvalNumber || '',
        specification: document.getElementById('formSpecification')?.value || form.dataset.specification || '',
        drug_type: document.getElementById('formDrugType')?.value || form.dataset.drugType || '',
        unit: document.getElementById('formUnit')?.value || form.dataset.unit || '',
        disease: document.getElementById('formDisease')?.value || form.dataset.disease || '',
        prescription_type: parseInt(document.getElementById('formPrescriptionType')?.value || form.dataset.prescriptionType || '0'),
        retail_price: document.getElementById('formRetailPrice')?.value || form.dataset.retailPrice || '',
        drug_image: document.getElementById('formDrugImage')?.value || form.dataset.drugImage || '',
        description: document.getElementById('formDescription')?.value || form.dataset.description || ''
    };
    
    if (!data.name) {
        showToast('请输入药品名称');
        return;
    }
    
    if (!data.expiry_date) {
        showToast('请输入有效期');
        return;
    }
    
    try {
        const response = await fetch('/api/medicines', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showToast('保存成功');
            closeScanModal();
            loadMedicines();
            loadStats();
        } else {
            showToast('保存失败');
        }
    } catch (error) {
        console.error('保存失败:', error);
        showToast('保存失败，请检查网络');
    }
}

// 打开详情弹窗
async function openDetailModal(id) {
    console.log('=== openDetailModal 被调用, id:', id);
    // 转换并验证 ID
    const numericId = parseInt(id, 10);
    console.log('转换后的 numericId:', numericId);
    if (!numericId || numericId <= 0 || isNaN(numericId)) {
        showToast('无效的药品ID: ' + id);
        return;
    }
    currentDetailId = numericId;

    try {
        console.log('开始请求 API:', `/api/medicines/${id}`);
        const response = await fetch(`/api/medicines/${id}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const result = await response.json();
        
        // 后端返回 {success: true, data: {...}} 格式
        const med = result.data || result;
        
        console.log('med对象:', med);
        console.log('med.name:', med.name);

        const expiryText = med.days_until_expiry !== null
            ? (med.days_until_expiry < 0
                ? `已过期 ${Math.abs(med.days_until_expiry)} 天`
                : `还剩 ${med.days_until_expiry} 天`)
            : '未知';
        
        const rxText = med.is_prescription === true 
            ? '处方药 (RX)' 
            : med.is_prescription === false 
                ? '非处方药 (OTC)' 
                : (med.prescription_type === 1 ? '处方药 (RX)' : med.prescription_type === 2 ? '非处方药 (OTC)' : '未知');
        
        // 优先使用 API 返回的官方图片
        const imageHtml = med.drug_image 
            ? `<img src="${med.drug_image}" class="detail-image" alt="药品图片" onerror="this.style.display='none'">`
            : (med.image_path ? `<img src="/uploads/${med.image_path}" class="detail-image" alt="药品图片">` : '');
        
        // 构建查看/编辑表单
        const htmlContent = `
            ${imageHtml}
            
            <form id="detailEditForm" data-medicine-id="${med.id}">
                <div class="detail-section">
                    <h3>药品名称</h3>
                    <p class="view-mode">${escapeHtml(med.name || '未命名')}</p>
                    <input type="text" class="edit-mode" name="name" value="${escapeHtml(med.name || '')}" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                    ${med.specification ? `<p class="detail-sub view-mode">规格: ${escapeHtml(med.specification)}</p>` : ''}
                    <input type="text" class="edit-mode" name="specification" value="${escapeHtml(med.specification || '')}" placeholder="规格" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px; margin-top:8px;">
                </div>

                <div class="detail-section">
                    <h3>分类 / 处方</h3>
                    <p class="view-mode">${categoryLabels[med.category] || med.drug_type || '其他'} / ${rxText}</p>
                    <div class="edit-mode" style="display:none;">
                        <select name="category" style="width:48%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                            <option value="internal" ${med.category === 'internal' ? 'selected' : ''}>内服</option>
                            <option value="external" ${med.category === 'external' ? 'selected' : ''}>外用</option>
                            <option value="topical" ${med.category === 'topical' ? 'selected' : ''}>局部</option>
                            <option value="supplement" ${med.category === 'supplement' ? 'selected' : ''}>保健</option>
                            <option value="other" ${med.category === 'other' || !med.category ? 'selected' : ''}>其他</option>
                        </select>
                        <select name="is_prescription" style="width:48%; padding:8px; border:1px solid #ddd; border-radius:4px; margin-left:4%;">
                            <option value="" ${med.is_prescription === null ? 'selected' : ''}>未知</option>
                            <option value="true" ${med.is_prescription === true ? 'selected' : ''}>处方药</option>
                            <option value="false" ${med.is_prescription === false ? 'selected' : ''}>非处方药</option>
                        </select>
                    </div>
                </div>

                ${med.barcode || med.approval_number ? `
                <div class="detail-section">
                    <h3>条码 / 批准文号</h3>
                    ${med.barcode ? `<p class="view-mode">条码: ${escapeHtml(med.barcode)}</p>` : ''}
                    <input type="text" class="edit-mode" name="barcode" value="${escapeHtml(med.barcode || '')}" placeholder="条码" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px; margin-bottom:8px;">
                    ${med.approval_number ? `<p class="view-mode">批准文号: ${escapeHtml(med.approval_number)}</p>` : ''}
                    <input type="text" class="edit-mode" name="approval_number" value="${escapeHtml(med.approval_number || '')}" placeholder="批准文号" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                </div>
                ` : ''}

                ${med.disease ? `
                <div class="detail-section">
                    <h3>适应疾病</h3>
                    <p class="view-mode">${escapeHtml(med.disease)}</p>
                    <textarea class="edit-mode" name="disease" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px; min-height:60px; resize:vertical;">${escapeHtml(med.disease || '')}</textarea>
                </div>
                ` : ''}

                ${med.ingredients ? `
                <div class="detail-section">
                    <h3>成分</h3>
                    <p class="view-mode">${escapeHtml(med.ingredients)}</p>
                    <textarea class="edit-mode" name="ingredients" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px; min-height:60px; resize:vertical;">${escapeHtml(med.ingredients || '')}</textarea>
                </div>
                ` : ''}

                ${med.indications ? `
                <div class="detail-section">
                    <h3>适应症</h3>
                    <p class="view-mode">${escapeHtml(med.indications)}</p>
                    <textarea class="edit-mode" name="indications" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px; min-height:60px; resize:vertical;">${escapeHtml(med.indications || '')}</textarea>
                </div>
                ` : ''}

                ${med.dosage ? `
                <div class="detail-section">
                    <h3>用法用量</h3>
                    <p class="view-mode">${escapeHtml(med.dosage)}</p>
                    <textarea class="edit-mode" name="dosage" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px; min-height:60px; resize:vertical;">${escapeHtml(med.dosage || '')}</textarea>
                </div>
                ` : ''}

                <div class="detail-section">
                    <h3>有效期</h3>
                    <p class="view-mode">${med.expiry_date || '未知'} (${expiryText})</p>
                    <input type="date" class="edit-mode" name="expiry_date" value="${med.expiry_date || ''}" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                </div>

                ${med.manufacturer ? `
                <div class="detail-section">
                    <h3>生产厂家</h3>
                    <p class="view-mode">${escapeHtml(med.manufacturer)}</p>
                    <input type="text" class="edit-mode" name="manufacturer" value="${escapeHtml(med.manufacturer || '')}" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                </div>
                ` : ''}

                ${med.retail_price ? `
                <div class="detail-section">
                    <h3>参考价格</h3>
                    <p class="view-mode">${escapeHtml(med.retail_price)}</p>
                    <input type="text" class="edit-mode" name="retail_price" value="${escapeHtml(med.retail_price || '')}" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                </div>
                ` : ''}

                ${med.description ? `
                <div class="detail-section">
                    <h3>说明书</h3>
                    <pre class="view-mode" style="white-space: pre-wrap; font-family: inherit; line-height: 1.6;">${escapeHtml(med.description)}</pre>
                    <textarea class="edit-mode" name="description" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px; min-height:120px; resize:vertical;">${escapeHtml(med.description || '')}</textarea>
                </div>
                ` : ''}

                <div class="detail-section">
                    <h3>备注</h3>
                    <p class="view-mode">${med.notes ? escapeHtml(med.notes) : '<span style="color:#999;">无备注</span>'}</p>
                    <textarea class="edit-mode" name="notes" style="display:none; width:100%; padding:8px; border:1px solid #ddd; border-radius:4px; min-height:60px; resize:vertical;" placeholder="添加备注...">${escapeHtml(med.notes || '')}</textarea>
                </div>
            </form>
        `;
        
        const detailContentEl = document.getElementById('detailContent');
        if (detailContentEl) {
            detailContentEl.innerHTML = htmlContent;
        }
        
        // 更新弹窗标题和按钮
        document.querySelector('#detailModal .modal-header h2').textContent = '药品详情';
        document.getElementById('detailModal').classList.add('active');
    } catch (error) {
        console.error('加载详情失败:', error);
        showToast('加载详情失败: ' + error.message);
    }
}

// 切换编辑模式
function toggleEditMode() {
    const isEditing = document.querySelector('.edit-mode')?.style.display !== 'none';
    
    document.querySelectorAll('.view-mode').forEach(el => {
        el.style.display = isEditing ? 'block' : 'none';
    });
    document.querySelectorAll('.edit-mode').forEach(el => {
        el.style.display = isEditing ? 'none' : 'block';
    });
    
    // 更新按钮
    const footer = document.querySelector('#detailModal .modal-footer');
    if (isEditing) {
        // 退出编辑模式
        footer.innerHTML = `
            <button class="btn-danger" onclick="deleteMedicine()">删除</button>
            <button class="btn-secondary" onclick="toggleEditMode()">编辑</button>
            <button class="btn-secondary" onclick="closeDetailModal()">关闭</button>
        `;
    } else {
        // 进入编辑模式
        footer.innerHTML = `
            <button class="btn-secondary" onclick="toggleEditMode()">取消</button>
            <button class="btn-primary" onclick="saveEdit()">保存</button>
        `;
    }
}

// 保存编辑
async function saveEdit() {
    const form = document.getElementById('detailEditForm');
    if (!form) return;
    
    const formData = new FormData(form);
    const data = {
        name: formData.get('name'),
        specification: formData.get('specification'),
        category: formData.get('category'),
        is_prescription: formData.get('is_prescription') === 'true' ? true : formData.get('is_prescription') === 'false' ? false : null,
        barcode: formData.get('barcode'),
        approval_number: formData.get('approval_number'),
        disease: formData.get('disease'),
        ingredients: formData.get('ingredients'),
        indications: formData.get('indications'),
        dosage: formData.get('dosage'),
        expiry_date: formData.get('expiry_date') || null,
        manufacturer: formData.get('manufacturer'),
        retail_price: formData.get('retail_price'),
        description: formData.get('description'),
        notes: formData.get('notes')
    };
    
    // 移除空值字段
    Object.keys(data).forEach(key => {
        if (data[key] === '' || data[key] === undefined) {
            delete data[key];
        }
    });
    
    if (!data.name) {
        showToast('药品名称不能为空');
        return;
    }
    
    try {
        const response = await fetch(`/api/medicines/${currentDetailId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            showToast('保存成功');
            closeDetailModal();
            loadMedicines();
            loadStats();
        } else {
            const result = await response.json();
            showToast(result.error || '保存失败');
        }
    } catch (error) {
        console.error('保存失败:', error);
        showToast('保存失败，请检查网络');
    }
}

// 关闭详情弹窗
function closeDetailModal() {
    document.getElementById('detailModal').classList.remove('active');
    currentDetailId = null;
    // 重置为查看模式
    document.querySelectorAll('.view-mode').forEach(el => el.style.display = 'block');
    document.querySelectorAll('.edit-mode').forEach(el => el.style.display = 'none');
    // 重置按钮
    const footer = document.querySelector('#detailModal .modal-footer');
    if (footer) {
        footer.innerHTML = `
            <button class="btn-danger" onclick="deleteMedicine()">删除</button>
            <button class="btn-secondary" onclick="toggleEditMode()">编辑</button>
            <button class="btn-secondary" onclick="closeDetailModal()">关闭</button>
        `;
    }
}

// 删除药品
async function deleteMedicine() {
    if (!currentDetailId) return;
    
    if (!confirm('确定要删除这个药品记录吗？')) return;
    
    try {
        const response = await fetch(`/api/medicines/${currentDetailId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showToast('删除成功');
            closeDetailModal();
            loadMedicines();
            loadStats();
        } else {
            showToast('删除失败');
        }
    } catch (error) {
        console.error('删除失败:', error);
        showToast('删除失败，请检查网络');
    }
}

// 转义HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 显示提示
function showToast(message) {
    // 简单的toast实现
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        bottom: 80px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0,0,0,0.8);
        color: white;
        padding: 12px 24px;
        border-radius: 24px;
        font-size: 14px;
        z-index: 10000;
        animation: fadeIn 0.3s;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 2000);
}

// 点击弹窗外部关闭
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.classList.remove('active');
    }
}
