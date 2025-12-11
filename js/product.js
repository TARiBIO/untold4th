document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const productId = params.get('id');

  const PRODUCTS = {
    product1: {
      name: 'Minimal White Tee',
      price: 50,
      img: 'assets/image-web-a3d92171-6f04-49c0-ba62-4087113390f6-default 2.jpg'
    },
    product2: {
      name: 'Stone Hoodie',
      price: 90,
      img: 'assets/04729300505-e1.jpg'
    },
    product3: {
      name: 'Stone Jeans',
      price: 120,
      img: 'assets/01300355401-a1.jpg'
    },
    product4: {
      name: 'Summer Floral Dress',
      price: 140,
      img: 'assets/09077198800-e1.jpg'
    }
  };

  if (!productId || !PRODUCTS[productId]) {
    document.body.innerHTML = "<h2 style='padding:40px'>Error: No product selected.</h2>";
    return;
  }

  const product = PRODUCTS[productId];
  const productNameEl = document.getElementById('productName');
  const productPriceEl = document.getElementById('productPrice');
  const productImgEl = document.getElementById('productImg');
  const sizeButtons = Array.from(document.querySelectorAll('#sizeOptions button'));
  const aiModal = document.getElementById('aiModal');
  const aiOverlay = document.getElementById('aiOverlay');
  const closeAiModalBtn = document.getElementById('closeAiModal');
  const aiResultEl = document.getElementById('aiResult');
  let aiOptionButtons = Array.from(document.querySelectorAll('.ai-options button'));
  const aiAssistForm = document.getElementById('aiAssistForm');
  const aiPhotoInput = document.getElementById('aiPhotoInput');
  const aiFileName = document.getElementById('aiFileName');
  const aiHeightInput = document.getElementById('aiHeightInput');
  const aiWeightInput = document.getElementById('aiWeightInput');
  const aiPhotoPreview = document.getElementById('aiPhotoPreview');
  const aiStatusEl = document.getElementById('aiStatus');
  const aiUploadField = document.getElementById('aiUploadField');
  const aiHeightField = document.getElementById('aiHeightField');
  const aiWeightField = document.getElementById('aiWeightField');

  if (productNameEl) productNameEl.textContent = product.name;
  if (productPriceEl) productPriceEl.textContent = `$${product.price}`;
  if (productImgEl) productImgEl.src = product.img;
  document.title = `${product.name} — Untold 4th`;

  let selectedSize = null;
  let selectedAiMode = null;
  let aiBusy = false;
  const backendBase = window.AI_BACKEND_URL || window.BACKEND_BASE_URL || 'http://localhost:8000';
  const apiKey = window.AI_API_KEY || window.AI_BACKEND_API_KEY || '';

  // Hide Option B (metrics-only) for jeans product3.
  if (productId === 'product3') {
    document.querySelectorAll('.ai-options button[data-mode="metrics"]').forEach(btn => btn.remove());
    aiOptionButtons = aiOptionButtons.filter(btn => btn.dataset.mode !== 'metrics');
  }

  function selectSize(size) {
    if (!size) return;
    selectedSize = size;
    sizeButtons.forEach(btn => {
      const isActive = btn.dataset.size === size;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-pressed', String(isActive));
    });
  }

  sizeButtons.forEach(btn => {
    btn.setAttribute('aria-pressed', 'false');
    btn.addEventListener('click', () => selectSize(btn.dataset.size));
  });

  function openAiModal() {
    if (!aiModal || !aiOverlay) return;
    aiModal.classList.add('open');
    aiOverlay.classList.add('active');
    aiModal.setAttribute('aria-hidden', 'false');
    aiOverlay.setAttribute('aria-hidden', 'false');
  }

  function closeAiModal() {
    if (!aiModal || !aiOverlay) return;
    aiModal.classList.remove('open');
    aiOverlay.classList.remove('active');
    aiModal.setAttribute('aria-hidden', 'true');
    aiOverlay.setAttribute('aria-hidden', 'true');
  }

  function aiAssist() {
    selectedAiMode = null;
    updateAiFields();
    if (aiResultEl) aiResultEl.textContent = 'Pick an option to get a tailored recommendation.';
    if (aiStatusEl) aiStatusEl.textContent = '';
    if (aiAssistForm) aiAssistForm.reset();
    if (aiPhotoPreview) {
      aiPhotoPreview.src = '';
      aiPhotoPreview.classList.add('hidden');
    }
    if (aiFileName) aiFileName.textContent = 'No file chosen';
    openAiModal();
  }

  function updateAiFields() {
    const hasMode = Boolean(selectedAiMode);
    const needsUpload = selectedAiMode === 'upload' || selectedAiMode === 'both';
    const needsHeight =
      selectedAiMode === 'upload' || selectedAiMode === 'metrics' || selectedAiMode === 'both';
    const needsWeight = selectedAiMode === 'metrics' || selectedAiMode === 'both';
    if (aiAssistForm) aiAssistForm.classList.toggle('hidden', !hasMode);
    if (aiUploadField) aiUploadField.classList.toggle('hidden', !needsUpload);
    if (aiHeightField) aiHeightField.classList.toggle('hidden', !needsHeight);
    if (aiWeightField) aiWeightField.classList.toggle('hidden', !needsWeight);
  }

  function describeMode(mode) {
    switch (mode) {
      case 'upload':
        return 'Upload a photo and include your height for a precise match.';
      case 'metrics':
        return 'Provide height and weight for a quick estimate.';
      case 'both':
        return 'Upload a photo plus height and weight for the highest accuracy.';
      default:
        return 'Pick an option to continue.';
    }
  }

  function handleOptionSelection(mode) {
    selectedAiMode = mode;
    updateAiFields();
    if (aiResultEl) aiResultEl.textContent = describeMode(mode);
  }

  aiOptionButtons.forEach(btn => {
    btn.addEventListener('click', () => handleOptionSelection(btn.dataset.mode));
  });

  function setAiStatus(msg) {
    if (aiStatusEl) aiStatusEl.textContent = msg || '';
  }

  function formatComparison(comparison) {
    if (!comparison) return '';
    return Object.entries(comparison)
      .map(([key, data]) => {
        const range = Array.isArray(data?.target_range) ? data.target_range.join('–') : data?.target_range;
        const diff = typeof data?.diff === 'number' ? `diff ${data.diff.toFixed(1)}cm` : '';
        const value = typeof data?.value === 'number' ? `${data.value.toFixed(1)}cm` : data?.value;
        return `${key.toUpperCase()}: ${value} vs target ${range}${diff ? ` (${diff})` : ''}`;
      })
      .join('<br>');
  }

  async function maybeConvertHeic(file) {
    if (!file) return null;
    const lower = file.name.toLowerCase();
    if (!(lower.endsWith('.heic') || lower.endsWith('.heif'))) {
      return file;
    }
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          const canvas = document.createElement('canvas');
          canvas.width = img.width;
          canvas.height = img.height;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0);
          canvas.toBlob(blob => {
            if (!blob) {
              reject(new Error('Failed to convert HEIC to JPEG.'));
              return;
            }
            resolve(new File([blob], file.name.replace(/\.(heic|heif)$/i, '.jpg'), { type: 'image/jpeg' }));
          }, 'image/jpeg', 0.92);
        };
        img.onerror = () => reject(new Error('Invalid HEIC image data.'));
        img.src = e.target.result;
      };
      reader.onerror = () => reject(new Error('Unable to read HEIC file.'));
      reader.readAsDataURL(file);
    });
  }

  async function submitAiAssist(event) {
    event.preventDefault();
    if (!selectedAiMode) {
      setAiStatus('Select an option first.');
      return;
    }
    if (aiBusy) return;
    const needsUpload = selectedAiMode === 'upload' || selectedAiMode === 'both';
    const needsHeight =
      selectedAiMode === 'upload' || selectedAiMode === 'metrics' || selectedAiMode === 'both';
    const needsWeight = selectedAiMode === 'metrics' || selectedAiMode === 'both';
    const photoFile = aiPhotoInput?.files?.[0];
    const heightValue = aiHeightInput ? parseInt(aiHeightInput.value, 10) : null;
    const weightValue = aiWeightInput ? parseInt(aiWeightInput.value, 10) : null;

    if (needsUpload && !photoFile) {
      setAiStatus('Please upload a reference photo.');
      return;
    }
    if (needsHeight && !heightValue) {
      setAiStatus('Please enter your height.');
      return;
    }
    if (needsWeight && !weightValue) {
      setAiStatus('Please enter your weight.');
      return;
    }

    const formData = new FormData();
    formData.append('mode', selectedAiMode);
    formData.append('product_id', productId);
    let uploadFile = photoFile;
    if (needsUpload && uploadFile) {
      try {
        uploadFile = await maybeConvertHeic(uploadFile);
      } catch (conversionErr) {
        console.error(conversionErr);
        setAiStatus(conversionErr.message || 'Unable to convert HEIC file.');
        return;
      }
      formData.append('file', uploadFile);
    }
    if (needsUpload && uploadFile && aiPhotoPreview) {
      aiPhotoPreview.src = URL.createObjectURL(uploadFile);
      aiPhotoPreview.classList.remove('hidden');
    }
    if (needsUpload && uploadFile && aiFileName) {
      aiFileName.textContent = uploadFile.name;
    }
    if (needsHeight && heightValue) {
      formData.append('height_cm', heightValue.toString());
    }
    if (needsWeight && weightValue) {
      formData.append('weight_kg', weightValue.toString());
    }

    aiBusy = true;
    setAiStatus('Analyzing fit...');
    try {
      const response = await fetch(`${backendBase}/fit-assist`, {
        method: 'POST',
        headers: apiKey ? { 'x-api-key': apiKey } : undefined,
        body: formData
      });
      const payload = await response.json();
      if (!response.ok) {
        const detail = payload?.detail || payload?.error || 'Unable to fetch recommendation.';
        throw new Error(detail);
      }
      const recommendedSize = payload?.recommendation?.size;
      if (recommendedSize) {
        selectSize(recommendedSize);
        const score = payload?.recommendation?.score;
        const comparisonHtml = formatComparison(payload?.recommendation?.comparison);
        if (aiResultEl) {
          const baseMsg = `AI recommends <strong>${recommendedSize}</strong>${typeof score === 'number' ? ` (score ${score.toFixed(1)})` : ''}.`;
          aiResultEl.innerHTML = comparisonHtml ? `${baseMsg}<br><small>${comparisonHtml}</small>` : baseMsg;
        }
      } else if (aiResultEl) {
        aiResultEl.textContent = 'We could not determine a size. Try a different option.';
      }
      setAiStatus('Recommendation ready.');
    } catch (err) {
      console.error(err);
      setAiStatus(err.message || 'Something went wrong.');
    } finally {
      aiBusy = false;
    }
  }

  if (aiAssistForm) aiAssistForm.addEventListener('submit', submitAiAssist);

  if (closeAiModalBtn) closeAiModalBtn.addEventListener('click', closeAiModal);
  if (aiOverlay) aiOverlay.addEventListener('click', closeAiModal);
  if (productId === 'product3') {
    document.querySelectorAll('.ai-options button[data-mode="metrics"], .ai-options button[data-mode="both"]').forEach(btn => btn.remove());
  }
  if (aiPhotoInput) {
    aiPhotoInput.addEventListener('change', () => {
      const file = aiPhotoInput.files && aiPhotoInput.files[0];
      if (file) {
        if (aiPhotoPreview) {
          aiPhotoPreview.src = URL.createObjectURL(file);
          aiPhotoPreview.classList.remove('hidden');
        }
        if (aiFileName) {
          aiFileName.textContent = file.name;
        }
      } else {
        if (aiPhotoPreview) {
          aiPhotoPreview.src = '';
          aiPhotoPreview.classList.add('hidden');
        }
        if (aiFileName) aiFileName.textContent = 'No file chosen';
      }
    });
  }
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeAiModal();
  });

  function showAddToast(message) {
    const toast = document.createElement('div');
    toast.textContent = message;
    toast.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.8);color:#fff;padding:8px 12px;border-radius:6px;z-index:9999;font-family:inherit;';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 1200);
  }

  function addToCart() {
    if (!selectedSize) {
      showAddToast('Please select a size before adding to cart.');
      return;
    }

    const cartSystem = window.cartSystem;
    const cartRef = cartSystem && Array.isArray(cartSystem.cart)
      ? cartSystem.cart
      : JSON.parse(localStorage.getItem('ut_cart') || '[]');
    const variantId = `${productId}-${selectedSize}`;
    const existing = cartRef.find(item => item.id === variantId);

    if (existing) {
      existing.qty += 1;
    } else {
      cartRef.push({
        id: variantId,
        baseId: productId,
        name: `${product.name} (${selectedSize})`,
        size: selectedSize,
        price: product.price,
        qty: 1,
        image: product.img
      });
    }

    if (cartSystem && typeof cartSystem.saveCart === 'function') {
      cartSystem.saveCart();
      if (typeof cartSystem.renderCart === 'function') cartSystem.renderCart();
      if (typeof cartSystem.openCart === 'function') cartSystem.openCart();
    } else {
      localStorage.setItem('ut_cart', JSON.stringify(cartRef));
    }

    closeAiModal();
    showAddToast(`${product.name} (${selectedSize}) added to your bag.`);
  }

  window.aiAssist = aiAssist;
  window.addToCart = addToCart;
});
