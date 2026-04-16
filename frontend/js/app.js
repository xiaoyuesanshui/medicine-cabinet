/**
 * 药品管理系统 - 前端逻辑
 */

const API_BASE = '';  // 同域部署
let currentMedicines = [];
let currentDetailId = null;
let currentFilter = 'all';  // 当前筛选状态: all, warning, expired

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
    // 默认选中"全部药品"
    document.getElementById('cardAll').classList.add('active');
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
    
    // 位置搜索
    document.getElementById('locationFilter').addEventListener('input', debounce(() => {
        loadMedicines();
    }, 300));
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

// 解码条形码 - 持续轮询方式
let codeReader = null;

async function decodeBarcode() {
    if (!isScanning) return;
    
    try {
        const video = document.getElementById('barcodeVideo');
        const canvas = document.getElementById('barcodeCanvas');
        const ctx = canvas.getContext('2d');
        
        if (!video.videoWidth || !video.videoHeight) {
            // 视频还未准备好，继续等待
            if (isScanning) {
                setTimeout(decodeBarcode, 100);
            }
            return;
        }
        
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // 创建图像数据源
        const luminanceSource = new ZXing.HTMLCanvasElementLuminanceSource(canvas);
        const binaryBitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(luminanceSource));
        
        // 尝试解码
        const reader = new ZXing.MultiFormatReader();
        const hints = new Map();
        hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [
            ZXing.BarcodeFormat.EAN_13,
            ZXing.BarcodeFormat.EAN_8,
            ZXing.BarcodeFormat.CODE_128,
            ZXing.BarcodeFormat.CODE_39,
            ZXing.BarcodeFormat.UPC_A,
            ZXing.BarcodeFormat.UPC_E
        ]);
        
        const result = reader.decode(binaryBitmap, hints);
        
        if (result) {
            // 识别成功
            stopBarcodeScan();
            document.getElementById('barcodeValue').textContent = result.text;
            document.getElementById('barcodeResult').style.display = 'block';
            showToast('条形码识别成功！');
            return;
        }
    } catch (error) {
        // 解码失败，继续下一帧
    }
    
    // 继续扫描（每 100ms 一帧，避免 CPU 占用过高）
    if (isScanning) {
        setTimeout(decodeBarcode, 100);
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

// 设置筛选状态
function setFilter(filter) {
    currentFilter = filter;
    
    // 更新卡片激活状态
    document.querySelectorAll('.stat-card').forEach(card => {
        card.classList.remove('active');
    });
    
    if (filter === 'all') {
        document.getElementById('cardAll').classList.add('active');
    } else if (filter === 'warning') {
        document.getElementById('cardWarning').classList.add('active');
    } else if (filter === 'expired') {
        document.getElementById('cardExpired').classList.add('active');
    }
    
    loadMedicines();
}

// 加载药品列表
async function loadMedicines() {
    const search = document.getElementById('searchInput').value;
    const category = document.getElementById('categoryFilter').value;
    const location = document.getElementById('locationFilter').value;
    
    let url = '/api/medicines?';
    if (search) url += `search=${encodeURIComponent(search)}&`;
    if (category) url += `category=${encodeURIComponent(category)}&`;
    if (location) url += `location=${encodeURIComponent(location)}&`;
    
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
        
        // 根据当前筛选状态过滤药品
        // 注意：后端返回的是聚合格式 {info, count, batches}
        let filteredMedicines = medicines;
        if (currentFilter === 'warning') {
            // 即将过期包括 warning(30天内) 和 danger(7天内)
            filteredMedicines = medicines.filter(group => {
                const batches = group.batches || [];
                return batches.some(m => m.expiry_status === 'warning' || m.expiry_status === 'danger');
            });
        } else if (currentFilter === 'expired') {
            filteredMedicines = medicines.filter(group => {
                const batches = group.batches || [];
                return batches.some(m => m.expiry_status === 'expired');
            });
        }
        
        renderMedicineList(filteredMedicines);
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
    
    console.log('渲染药品列表:', medicines.length, '种药品');
    
    // 新格式：聚合展示，每种药品一个卡片
    container.innerHTML = medicines.map((group, index) => {
        const med = group.info || group;  // 兼容旧格式
        const count = group.count || 1;
        const batches = group.batches || [med];
        
        // 计算最紧急的过期状态
        const urgentBatch = batches.reduce((urgent, batch) => {
            if (!urgent) return batch;
            const urgentDays = urgent.days_until_expiry !== null ? urgent.days_until_expiry : 9999;
            const batchDays = batch.days_until_expiry !== null ? batch.days_until_expiry : 9999;
            return batchDays < urgentDays ? batch : urgent;
        }, null);
        
        const expiryStatus = urgentBatch?.expiry_status || 'unknown';
        const expiryClass = (expiryStatus === 'expired' || expiryStatus === 'opened_expired') ? 'expired' : expiryStatus;
        
        const daysText = urgentBatch?.days_until_expiry !== null 
            ? (urgentBatch.days_until_expiry < 0 
                ? `已过期 ${Math.abs(urgentBatch.days_until_expiry)} 天` 
                : `还剩 ${urgentBatch.days_until_expiry} 天`)
            : '未知';
        
        const rxBadge = med.is_prescription === true 
            ? '<span class="medicine-badge badge-rx">RX</span>'
            : med.is_prescription === false
                ? '<span class="medicine-badge badge-otc">OTC</span>'
                : '';
        
        const locationBadges = batches
            .filter(b => b.location)
            .map(b => `<span class="medicine-badge badge-location">${b.location}</span>`)
            .slice(0, 3)  // 最多显示3个位置
            .join('');
        
        // 库存数量徽章
        const countBadge = count > 1 
            ? `<span class="medicine-badge badge-count">×${count}</span>` 
            : '';
        
        return `
            <div class="medicine-card ${expiryClass}" onclick="openDetailModal(${med.id})">
                <div class="medicine-header">
                    <span class="medicine-name">${escapeHtml(med.name || '未命名药品')}</span>
                    <div>
                        ${countBadge}
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

// 显示库存总览
async function showInventoryOverview() {
    document.getElementById('inventoryOverview').style.display = 'block';
    await loadInventoryList();
}

// 关闭库存总览
function toggleInventoryList() {
    document.getElementById('inventoryOverview').style.display = 'none';
}

// 加载库存列表（按药品名分组，显示每个名称的批次数）
async function loadInventoryList() {
    try {
        console.log('=== 开始加载库存列表 ===');
        const response = await fetch('/api/medicines?limit=1000');
        const result = await response.json();
        
        const medicines = Array.isArray(result) ? result : (result && result.data || []);
        console.log('库存列表API返回:', medicines.length, '条');
        
        if (!medicines.length) {
            document.getElementById('inventoryList').innerHTML = '<p style="padding:20px;text-align:center;color:#999;">暂无库存数据</p>';
            return;
        }
        
        // 按药品名分组（使用batches数组中的批次）
        const groups = {};
        let totalBatches = 0;
        let expiredCount = 0;
        let expiringSoonCount = 0;
        
        medicines.forEach(med => {
            const name = med.name || '未命名';
            const batches = med.batches || [med]; // 有batches字段用batches，没有则用自身
            if (!groups[name]) {
                groups[name] = { count: batches.length, earliest: null };
            } else {
                groups[name].count += batches.length;
            }
            
            // 统计过期数量
            batches.forEach(batch => {
                totalBatches++;
                const days = batch.days_until_expiry !== undefined ? batch.days_until_expiry : med.days_until_expiry;
                if (days < 0) expiredCount++;
                else if (days <= 30) expiringSoonCount++;
                
                // 记录最早过期的批次
                const existingExpiry = groups[name].earliest 
                    ? (groups[name].earliest.effective_expiry_date || groups[name].earliest.expiry_date) 
                    : null;
                const thisExpiry = batch.effective_expiry_date || batch.expiry_date || '';
                if (!groups[name].earliest || (thisExpiry < existingExpiry)) {
                    groups[name].earliest = batch;
                    groups[name].earliestId = batch.id;
                }
            });
        });
        
        document.getElementById('inventoryTotal').textContent = `共 ${totalBatches} 批次 (过期${expiredCount} 即将过期${expiringSoonCount})`;
        
        // 按名称排序后渲染（纯文本格式）
        const sortedNames = Object.keys(groups).sort((a, b) => a.localeCompare(b, 'zh-CN'));
        
        let text = '药品名称'.padEnd(24) + '批次数\n';
        text += '─'.repeat(32) + '\n';
        
        sortedNames.forEach(name => {
            const info = groups[name];
            text += name.padEnd(24) + `${info.count}\n`;
        });
        
        text += '─'.repeat(32) + '\n';
        text += `合计`.padEnd(24) + `${totalBatches}`;
        
        document.getElementById('inventoryList').innerHTML = `<pre style="margin:0; padding:16px; font-size:14px; line-height:1.6; white-space:pre; font-family:monospace; background:#fafafa; border-radius:8px;">${text}</pre>`;
    } catch (error) {
        console.error('加载库存列表失败:', error);
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
    setFieldValue('formAlias', data.alias || '');
    
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
        description: document.getElementById('formDescription')?.value || form.dataset.description || '',
        alias: document.getElementById('formAlias')?.value || '',
        location_row: document.getElementById('formLocationRow')?.value || null,
        location_col: document.getElementById('formLocationCol')?.value ? parseInt(document.getElementById('formLocationCol').value) : null,
        shelf_life_after_opening: document.getElementById('formShelfLifeAfterOpening')?.value ? parseInt(document.getElementById('formShelfLifeAfterOpening').value) : null
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
        
        // 获取该药品的所有批次
        let batches = [];
        let batchesHtml = '';
        let batchesEditHtml = '';
        try {
            const batchResponse = await fetch(`/api/medicines/batches?name=${encodeURIComponent(med.name)}`);
            if (batchResponse.ok) {
                const batchResult = await batchResponse.json();
                batches = batchResult.data?.batches || batchResult.batches || [];
                
                // 按过期日期排序（越早过期越靠前）
                batches.sort((a, b) => {
                    if (!a.expiry_date) return 1;
                    if (!b.expiry_date) return -1;
                    return new Date(a.expiry_date) - new Date(b.expiry_date);
                });
                
                // 构建查看模式的批次列表HTML
                batchesHtml = batches.map((batch, index) => {
                    const statusClass = batch.expiry_status === 'expired' || batch.expiry_status === 'opened_expired' ? 'expired' : 
                                       batch.expiry_status === 'danger' ? 'danger' : 
                                       batch.expiry_status === 'warning' ? 'warning' : 'safe';
                    
                    // 判断使用哪个有效期显示
                    const displayDate = batch.effective_expiry_date || batch.expiry_date;
                    const daysText = batch.days_until_expiry !== null 
                        ? (batch.days_until_expiry < 0 
                            ? `已过期 ${Math.abs(batch.days_until_expiry)} 天` 
                            : `还剩 ${batch.days_until_expiry} 天`)
                        : '未知';
                    
                    // 开封状态标签
                    const openedBadge = batch.is_opened 
                        ? `<span style="background:#ff9800;color:white;padding:1px 6px;border-radius:10px;font-size:11px;margin-left:6px;">已开封</span>` 
                        : '';
                    
                    // 开封按钮（仅在未开封且有开封保质期时显示）
                    const openBtn = !batch.is_opened && batch.shelf_life_after_opening 
                        ? `<button onclick="openMedicineBatch(${batch.id})" style="background:#ff9800;color:white;border:none;padding:2px 8px;border-radius:4px;font-size:12px;cursor:pointer;margin-left:8px;">开封</button>` 
                        : '';
                    
                    // 取消开封按钮
                    const unopenBtn = batch.is_opened 
                        ? `<button onclick="unopenMedicineBatch(${batch.id})" style="background:#999;color:white;border:none;padding:2px 8px;border-radius:4px;font-size:12px;cursor:pointer;margin-left:8px;">撤回开封</button>` 
                        : '';

                    return `
                        <div class="batch-item ${statusClass}" style="padding:5px 0; border-bottom:1px solid #eee; display:grid; grid-template-columns:48px 56px 110px 36px 150px auto; align-items:center; gap:4px; font-size:13px; justify-items:start;">
                            <span>批次${index + 1}</span>
                            <span style="min-width:${openedBadge ? '0' : '1px'};">${openedBadge || ''}</span>
                            <span style="font-size:11px;color:#999;white-space:nowrap;">${batch.is_opened && batch.opened_date ? '开封于 '+batch.opened_date : ''}</span>
                            <span style="white-space:nowrap;">${batch.location || ''}</span>
                            <span style="${batch.is_opened ? 'color:#ff9800;' : ''};white-space:nowrap;">${displayDate || '未设置'} (${daysText})</span>
                            <div style="display:flex; gap:3px;">
                                ${openBtn}${unopenBtn}
                                <button onclick="deleteBatch(${batch.id})" style="background:#e53935;color:white;border:none;padding:2px 6px;border-radius:4px;font-size:12px;cursor:pointer;">删除</button>
                            </div>
                        </div>
                    `;
                }).join('');
                
                // 构建编辑模式的批次列表HTML（可编辑位置和开封保质期）
                batchesEditHtml = batches.map((batch, index) => {
                    const statusClass = batch.expiry_status === 'expired' || batch.expiry_status === 'opened_expired' ? 'expired' : 
                                       batch.expiry_status === 'danger' ? 'danger' : 
                                       batch.expiry_status === 'warning' ? 'warning' : 'safe';
                    const daysText = batch.days_until_expiry !== null 
                        ? (batch.days_until_expiry < 0 
                            ? `已过期 ${Math.abs(batch.days_until_expiry)} 天` 
                            : `还剩 ${batch.days_until_expiry} 天`)
                        : '未知';
                    
                    const openedBadge = batch.is_opened 
                        ? `<span style="background:#ff9800;color:white;padding:1px 6px;border-radius:10px;font-size:11px;">已开封</span>` 
                        : '';
                    
                    return `
                        <div class="batch-item ${statusClass}" style="padding:8px 0; border-bottom:1px solid #eee; display:grid; grid-template-columns:48px 1fr 150px; align-items:center; gap:6px; font-size:13px; justify-items:start;">
                            <span>批次${index + 1}${openedBadge}</span>
                            <div style="display:flex; gap:8px; align-items:center; flex-wrap:nowrap;">
                                <div style="display:flex; gap:4px; align-items:center;">
                                    <span style="font-size:12px; color:#666;">位置:</span>
                                    <select name="batch_location_row_${batch.id}" style="width:55px; padding:4px;">
                                        <option value="">行</option>
                                        ${['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z'].map(r => 
                                            `<option value="${r}" ${batch.location_row === r ? 'selected' : ''}>${r}</option>`
                                        ).join('')}
                                    </select>
                                    <select name="batch_location_col_${batch.id}" style="width:55px; padding:4px;">
                                        <option value="">列</option>
                                        ${[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19].map(c => 
                                            `<option value="${c}" ${batch.location_col === c ? 'selected' : ''}>${c}</option>`
                                        ).join('')}
                                    </select>
                                </div>
                                <div style="display:flex; gap:4px; align-items:center;">
                                    <span style="font-size:12px; color:#666;">开封保质期:</span>
                                    <input type="number" name="batch_shelf_life_after_opening_${batch.id}" value="${batch.shelf_life_after_opening || ''}" min="1" max="3650" placeholder="天" style="width:55px; padding:4px;">
                                    <span style="font-size:12px; color:#999;">天</span>
                                </div>
                            </div>
                            <span style="color:#666; font-size:12px;">${batch.effective_expiry_date || batch.expiry_date || '未设置'} (${daysText})</span>
                        </div>
                    `;
                }).join('');
            }
        } catch (e) {
            console.log('获取批次信息失败:', e);
        }

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
        
        // 构建查看/编辑表单 - 使用与查询窗口相同的表单格式
        const htmlContent = `
            ${imageHtml}
            
            <form id="detailEditForm" data-medicine-id="${med.id}">
                <div class="form-group">
                    <label>药品名称 *</label>
                    <p class="view-mode">${escapeHtml(med.name || '未命名')}${med.alias ? ` <span style="color:#666; font-size:14px;">(${escapeHtml(med.alias)})</span>` : ''}</p>
                    <input type="text" class="edit-mode" name="name" value="${escapeHtml(med.name || '')}" style="display:none;">
                </div>
                <div class="form-group">
                    <label>别名</label>
                    <p class="view-mode">${escapeHtml(med.alias || '-')}</p>
                    <input type="text" class="edit-mode" name="alias" value="${escapeHtml(med.alias || '')}" style="display:none;" placeholder="例如：人工泪液">
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>规格</label>
                        <p class="view-mode">${escapeHtml(med.specification || '-')}</p>
                        <input type="text" class="edit-mode" name="specification" value="${escapeHtml(med.specification || '')}" style="display:none;" readonly>
                    </div>
                    <div class="form-group">
                        <label>剂型</label>
                        <p class="view-mode">${escapeHtml(med.drug_type || '-')}</p>
                        <input type="text" class="edit-mode" name="drug_type" value="${escapeHtml(med.drug_type || '')}" style="display:none;" readonly>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>成分</label>
                    <p class="view-mode">${escapeHtml(med.ingredients || '-')}</p>
                    <textarea class="edit-mode" name="ingredients" rows="2" style="display:none;">${escapeHtml(med.ingredients || '')}</textarea>
                </div>
                
                <div class="form-group">
                    <label>适应症</label>
                    <p class="view-mode">${escapeHtml(med.indications || med.disease || '-')}</p>
                    <textarea class="edit-mode" name="indications" rows="2" style="display:none;">${escapeHtml(med.indications || med.disease || '')}</textarea>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>分类</label>
                        <p class="view-mode">${categoryLabels[med.category] || med.category || '-'}</p>
                        <select class="edit-mode" name="category" style="display:none;">
                            <option value="internal" ${med.category === 'internal' ? 'selected' : ''}>内服</option>
                            <option value="external" ${med.category === 'external' ? 'selected' : ''}>外用</option>
                            <option value="topical" ${med.category === 'topical' ? 'selected' : ''}>局部用药</option>
                            <option value="supplement" ${med.category === 'supplement' ? 'selected' : ''}>保健品</option>
                            <option value="other" ${med.category === 'other' || !med.category ? 'selected' : ''}>其他</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>处方药</label>
                        <p class="view-mode">${rxText}</p>
                        <select class="edit-mode" name="is_prescription" style="display:none;">
                            <option value="" ${med.is_prescription === null ? 'selected' : ''}>未知</option>
                            <option value="true" ${med.is_prescription === true ? 'selected' : ''}>是</option>
                            <option value="false" ${med.is_prescription === false ? 'selected' : ''}>否</option>
                        </select>
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>位置</label>
                        <p class="view-mode">${med.location || '-'}</p>
                        <div class="edit-mode location-select" style="display:none;">
                            <select name="location_row">
                                <option value="">行</option>
                                ${['A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z'].map(r => 
                                    `<option value="${r}" ${med.location_row === r ? 'selected' : ''}>${r}</option>`
                                ).join('')}
                            </select>
                            <select name="location_col">
                                <option value="">列</option>
                                ${[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19].map(c => 
                                    `<option value="${c}" ${med.location_col === c ? 'selected' : ''}>${c}</option>`
                                ).join('')}
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>有效期 ${med.days_until_expiry !== null ? `(${expiryText})` : ''}</label>
                        <p class="view-mode">${med.expiry_date || '-'}${med.is_opened ? ` <span style="color:#ff9800;font-size:12px;">(已开封，实际有效期: ${med.effective_expiry_date || '-'})</span>` : ''}</p>
                        <input type="date" class="edit-mode" name="expiry_date" value="${med.expiry_date || ''}" style="display:none;">
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>开封后保质期</label>
                        <p class="view-mode">${med.shelf_life_after_opening ? med.shelf_life_after_opening + ' 天' : '-'}${med.is_opened ? ` <span style="color:#ff9800;font-size:12px;">(开封于 ${med.opened_date || '-'})</span>` : ''}</p>
                        <input type="number" class="edit-mode" name="shelf_life_after_opening" value="${med.shelf_life_after_opening || ''}" min="1" max="3650" placeholder="天数，如30" style="display:none;">
                    </div>
                    <div class="form-group">
                        <label>开封状态</label>
                        <p class="view-mode">${med.is_opened ? `<span style="color:#ff9800;">✅ 已开封 (${med.opened_date || '-'})</span>` : '未开封'}</p>
                        <div class="edit-mode" style="display:none;">
                            ${med.is_opened 
                                ? `<span style="color:#ff9800;">已开封 (${med.opened_date || '-'})</span>` 
                                : (med.shelf_life_after_opening 
                                    ? `<button type="button" onclick="openMedicineBatch(${med.id})" style="background:#ff9800;color:white;border:none;padding:4px 12px;border-radius:4px;font-size:13px;cursor:pointer;">确认开封</button><span style="font-size:11px;color:#999;margin-left:6px;">开封后有效期将变为${med.shelf_life_after_opening}天</span>` 
                                    : '<span style="color:#999;font-size:12px;">请先设置开封后保质期</span>')}
                        </div>
                    </div>
                </div>
                
                <!-- 批次管理 -->
                <div class="form-group">
                    <label>批次管理 (${batches.length}个批次)</label>
                    <div class="view-mode" style="display:inline-block; border:1px solid #e0e0e0; border-radius:4px; padding:0 12px;">
                        ${batchesHtml || '<p style="padding:8px 0; color:#999;">暂无批次信息</p>'}
                    </div>
                    <div class="edit-mode" style="display:none; inline-block; border:1px solid #e0e0e0; border-radius:4px; padding:0 12px;">
                        ${batchesEditHtml || '<p style="padding:8px 0; color:#999;">暂无批次信息</p>'}
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>参考价格</label>
                        <p class="view-mode">${escapeHtml(med.retail_price || '-')}</p>
                        <input type="text" class="edit-mode" name="retail_price" value="${escapeHtml(med.retail_price || '')}" style="display:none;" readonly>
                    </div>
                    <div class="form-group">
                        <label>生产厂家</label>
                        <p class="view-mode">${escapeHtml(med.manufacturer || '-')}</p>
                        <input type="text" class="edit-mode" name="manufacturer" value="${escapeHtml(med.manufacturer || '')}" style="display:none;">
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>批准文号</label>
                        <p class="view-mode">${escapeHtml(med.approval_number || '-')}</p>
                        <input type="text" class="edit-mode" name="approval_number" value="${escapeHtml(med.approval_number || '')}" style="display:none;" readonly>
                    </div>
                    <div class="form-group">
                        <label>条码</label>
                        <p class="view-mode">${escapeHtml(med.barcode || '-')}</p>
                        <input type="text" class="edit-mode" name="barcode" value="${escapeHtml(med.barcode || '')}" style="display:none;" readonly>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>用法用量</label>
                    <p class="view-mode">${escapeHtml(med.dosage || '-')}</p>
                    <textarea class="edit-mode" name="dosage" rows="2" style="display:none;">${escapeHtml(med.dosage || '')}</textarea>
                </div>
                
                <div class="form-group">
                    <label>说明书</label>
                    <p class="view-mode" style="white-space: pre-wrap; word-break: break-all; font-size: 12px; background: #f5f5f5; padding: 8px; border-radius: 4px; max-height: 150px; overflow-y: auto; max-width:100%;">${escapeHtml(med.description || '-')}</p>
                    <textarea class="edit-mode" name="description" rows="4" style="display:none; font-size: 12px;">${escapeHtml(med.description || '')}</textarea>
                </div>
                
                <div class="form-group">
                    <label>备注</label>
                    <p class="view-mode">${med.notes ? escapeHtml(med.notes) : '<span style="color:#999;">无备注</span>'}</p>
                    <textarea class="edit-mode" name="notes" rows="2" style="display:none;" placeholder="添加备注...">${escapeHtml(med.notes || '')}</textarea>
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
            <button class="btn-secondary" type="button" onclick="toggleEditMode()">取消</button>
            <button class="btn-primary" type="button" onclick="saveEdit()">保存</button>
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
        ingredients: formData.get('ingredients'),
        indications: formData.get('indications'),
        dosage: formData.get('dosage'),
        expiry_date: formData.get('expiry_date') || null,
        manufacturer: formData.get('manufacturer'),
        retail_price: formData.get('retail_price'),
        description: formData.get('description'),
        notes: formData.get('notes'),
        alias: formData.get('alias'),
        location_row: formData.get('location_row') || null,
        location_col: formData.get('location_col') ? parseInt(formData.get('location_col')) : null,
        shelf_life_after_opening: formData.get('shelf_life_after_opening') ? parseInt(formData.get('shelf_life_after_opening')) : null
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
        // 先保存主药品信息
        const response = await fetch(`/api/medicines/${currentDetailId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            const result = await response.json();
            showToast(result.error || '保存失败');
            return;
        }
        
        // 保存批次位置信息
        const batchUpdates = [];
        const form = document.getElementById('detailEditForm');
        const selects = form.querySelectorAll('select[name^="batch_location_row_"], select[name^="batch_location_col_"]');
        
        // 收集所有批次的位置信息和开封保质期
        const batchLocations = {};
        selects.forEach(select => {
            const match = select.name.match(/batch_location_(row|col)_(\d+)/);
            if (match) {
                const [, type, batchId] = match;
                if (!batchLocations[batchId]) {
                    batchLocations[batchId] = {};
                }
                batchLocations[batchId][type] = select.value;
            }
        });
        
        // 收集批次的开封保质期
        const shelfLifeInputs = form.querySelectorAll('input[name^="batch_shelf_life_after_opening_"]');
        shelfLifeInputs.forEach(input => {
            const match = input.name.match(/batch_shelf_life_after_opening_(\d+)/);
            if (match) {
                const batchId = match[1];
                if (!batchLocations[batchId]) {
                    batchLocations[batchId] = {};
                }
                batchLocations[batchId].shelf_life_after_opening = input.value ? parseInt(input.value) : null;
            }
        });
        
        // 更新每个批次的位置和开封保质期
        for (const [batchId, loc] of Object.entries(batchLocations)) {
            const updateData = {
                location_row: loc.row || null,
                location_col: loc.col ? parseInt(loc.col) : null
            };
            if (loc.shelf_life_after_opening !== undefined) {
                updateData.shelf_life_after_opening = loc.shelf_life_after_opening;
            }
            batchUpdates.push(
                fetch(`/api/medicines/${batchId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updateData)
                })
            );
        }
        
        // 等待所有批次更新完成
        if (batchUpdates.length > 0) {
            await Promise.all(batchUpdates);
        }
        
        showToast('保存成功');
        closeDetailModal();
        loadMedicines();
        loadStats();
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

// 打开批次详情弹窗
async function openBatchModal(medicineName) {
    console.log('打开批次详情:', medicineName);
    
    try {
        const response = await fetch(`/api/medicines/${encodeURIComponent(medicineName)}/batches`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const result = await response.json();
        
        const data = result.data || result;
        const med = data.info;
        const batches = data.batches || [];
        
        // 构建批次列表HTML
        const batchesHtml = batches.map((batch, index) => {
            const statusClass = batch.expiry_status === 'expired' ? 'expired' : 
                               batch.expiry_status === 'danger' ? 'danger' : 
                               batch.expiry_status === 'warning' ? 'warning' : 'safe';
            const daysText = batch.days_until_expiry !== null 
                ? (batch.days_until_expiry < 0 
                    ? `已过期 ${Math.abs(batch.days_until_expiry)} 天` 
                    : `还剩 ${batch.days_until_expiry} 天`)
                : '未知';
            
            return `
                <div class="batch-item ${statusClass}" onclick="openDetailModal(${batch.id})" style="cursor:pointer; padding:12px; border:1px solid #e0e0e0; border-radius:8px; margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <strong>批次 ${index + 1}</strong>
                            ${batch.location ? `<span class="medicine-badge badge-location" style="margin-left:8px;">${batch.location}</span>` : ''}
                        </div>
                        <span class="batch-status ${statusClass}">${daysText}</span>
                    </div>
                    <div style="margin-top:8px; color:#666; font-size:14px;">
                        保质期: ${batch.expiry_date || '未设置'}
                        ${batch.notes ? `<br>备注: ${escapeHtml(batch.notes)}` : ''}
                    </div>
                </div>
            `;
        }).join('');
        
        // 构建弹窗内容
        const htmlContent = `
            <div style="margin-bottom:20px;">
                <h3 style="margin:0 0 10px 0;">${escapeHtml(med.name || '未命名药品')}</h3>
                <p style="color:#666; margin:0;">${escapeHtml(med.manufacturer || '未知厂家')}</p>
                ${med.specification ? `<p style="color:#999; font-size:14px; margin:5px 0 0 0;">规格: ${escapeHtml(med.specification)}</p>` : ''}
            </div>
            
            <div style="margin-bottom:15px;">
                <h4 style="margin:0 0 10px 0; font-size:16px;">库存批次 (${batches.length})</h4>
                ${batchesHtml}
            </div>
            
            <div style="background:#f5f5f5; padding:12px; border-radius:8px; margin-top:15px;">
                <h4 style="margin:0 0 8px 0; font-size:14px; color:#666;">药品信息</h4>
                <p style="margin:0; font-size:14px; color:#333;">
                    <strong>适应症:</strong> ${escapeHtml(med.indications || med.disease || '-')}
                </p>
                ${med.dosage ? `<p style="margin:8px 0 0 0; font-size:14px; color:#333;"><strong>用法用量:</strong> ${escapeHtml(med.dosage)}</p>` : ''}
            </div>
        `;
        
        // 显示弹窗
        const modal = document.getElementById('detailModal');
        const body = modal.querySelector('.modal-body');
        const footer = modal.querySelector('.modal-footer');
        
        body.innerHTML = htmlContent;
        footer.innerHTML = `
            <button class="btn-secondary" onclick="closeDetailModal()">关闭</button>
        `;
        
        modal.classList.add('active');
        
    } catch (error) {
        console.error('获取批次详情失败:', error);
        showToast('获取批次详情失败: ' + error.message);
    }
}

// 开封药品批次
async function openMedicineBatch(batchId) {
    if (!confirm('确认开封此批次？开封后有效期将按开封后保质期重新计算。')) return;
    
    try {
        const response = await fetch(`/api/medicines/${batchId}/open`, { method: 'POST' });
        const result = await response.json();
        
        if (response.ok) {
            showToast('已标记为开封');
            // 重新加载详情弹窗
            if (currentDetailId) {
                openDetailModal(currentDetailId);
            }
            loadMedicines();
            loadStats();
        } else {
            showToast(result.error || '开封操作失败');
        }
    } catch (error) {
        console.error('开封操作失败:', error);
        showToast('开封操作失败');
    }
}

// 取消开封状态
async function unopenMedicineBatch(batchId) {
    if (!confirm('确认取消开封状态？有效期将恢复为原始有效期。')) return;
    
    try {
        const response = await fetch(`/api/medicines/${batchId}/unopen`, { method: 'POST' });
        const result = await response.json();
        
        if (response.ok) {
            showToast('已取消开封');
            if (currentDetailId) {
                openDetailModal(currentDetailId);
            }
            loadMedicines();
            loadStats();
        } else {
            showToast(result.error || '取消开封失败');
        }
    } catch (error) {
        console.error('取消开封失败:', error);
        showToast('取消开封失败');
    }
}

// 删除批次
async function deleteBatch(batchId) {
    if (!confirm('确认删除此批次？此操作不可恢复。')) return;
    
    try {
        const response = await fetch(`/api/medicines/${batchId}`, { method: 'DELETE' });
        const result = await response.json();
        
        if (response.ok) {
            showToast('批次已删除');
            closeDetailModal();
            loadMedicines();
            loadStats();
        } else {
            showToast(result.error || '删除失败');
        }
    } catch (error) {
        console.error('删除批次失败:', error);
        showToast('删除批次失败');
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
