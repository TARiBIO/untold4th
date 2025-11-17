const params = new URLSearchParams(window.location.search);
const API_BASE = window.AI_BACKEND_URL || 'http://127.0.0.1:8000';
const productId = params.get('id');

const PRODUCTS = {
  product1: {
    name: 'Minimal Black Tee',
    price: 50,
    img: 'assets/marianne-bos-WV6hCFDT9Rg-unsplash.jpg'
  },
  product2: {
    name: 'Stone Hoodie',
    price: 90,
    img: 'assets/ricardo-lopez-nebjAZknedw-unsplash.jpg'
  },
  product3: {
    name: 'Stone Joggers',
    price: 120,
    img: 'assets/marcel-eberle-FGYv8CDQBmg-unsplash.jpg'
  }
};

if (!productId || !PRODUCTS[productId]) {
  document.body.innerHTML = "<h2 style='padding:40px'>Error: No product selected.</h2>";
  throw new Error('Missing or unknown product ID in URL');
}

const product = PRODUCTS[productId];
const productNameEl = document.getElementById('productName');
const productPriceEl = document.getElementById('productPrice');
const productImgEl = document.getElementById('productImg');
const sizeButtons = Array.from(document.querySelectorAll('#sizeOptions button'));

if (productNameEl) productNameEl.textContent = product.name;
if (productPriceEl) productPriceEl.textContent = `$${product.price}`;
if (productImgEl) productImgEl.src = product.img;
document.title = `${product.name} — Untold 4th`;

let selectedSize = null;

sizeButtons.forEach(btn => {
  btn.setAttribute('aria-pressed', 'false');
  btn.addEventListener('click', () => selectSize(btn.dataset.size));
});

function selectSize(size) {
  if (!size) return;
  selectedSize = size;
  sizeButtons.forEach(btn => {
    const isActive = btn.dataset.size === size;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-pressed', String(isActive));
  });
}

function aiAssist() {
  // Open the AI modal instead of a simple alert
  const overlay = document.getElementById('aiOverlay');
  const modal = document.getElementById('aiModal');
  if (overlay) overlay.classList.add('active');
  if (modal) modal.classList.add('open');
}

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

  const variantId = `${productId}-${selectedSize}`;
  const cartSystem = window.cartSystem;

  if (cartSystem && cartSystem.cart) {
    const { cart, saveCart, renderCart, openCart } = cartSystem;
    const existing = cart.find(item => item.id === variantId);

    if (existing) {
      existing.qty += 1;
    } else {
      cart.push({
        id: variantId,
        baseId: productId,
        name: `${product.name} (${selectedSize})`,
        size: selectedSize,
        price: product.price,
        qty: 1,
        image: product.img
      });
    }

    saveCart();
    renderCart();
    openCart();

    showAddToast(`${product.name} (${selectedSize}) added to your bag.`);
    return;
  }

  // Fallback if cart system isn't available
  const legacyCart = JSON.parse(localStorage.getItem('ut_cart') || '[]');
  const legacyExisting = legacyCart.find(item => item.id === variantId);

  if (legacyExisting) {
    legacyExisting.qty += 1;
  } else {
    legacyCart.push({
      id: variantId,
      baseId: productId,
      name: `${product.name} (${selectedSize})`,
      size: selectedSize,
      price: product.price,
      qty: 1,
      image: product.img
    });
  }

  localStorage.setItem('ut_cart', JSON.stringify(legacyCart));
  showAddToast(`${product.name} (${selectedSize}) added to your bag.`);
}

// --- AI Modal + Fit Assist integration with backend ---
(function setupAiAssist() {
  const overlay = document.getElementById('aiOverlay');
  const modal = document.getElementById('aiModal');
  const closeBtn = document.getElementById('closeAiModal');
  const optionsContainer = modal ? modal.querySelector('.ai-options') : null;
  const form = document.getElementById('aiAssistForm');
  const uploadField = document.getElementById('aiUploadField');
  const metricsField = document.getElementById('aiMetricsField');
  const photoInput = document.getElementById('aiPhotoInput');
  const heightInput = document.getElementById('aiHeightInput');
  const weightInput = document.getElementById('aiWeightInput');
  const statusEl = document.getElementById('aiStatus');
  const resultEl = document.getElementById('aiResult');

  if (!modal || !optionsContainer || !form) {
    // No AI modal present on this page
    return;
  }

  let selectedMode = null;

  function openModal() {
    if (overlay) overlay.classList.add('active');
    modal.classList.add('open');
  }

  function closeModal() {
    if (overlay) overlay.classList.remove('active');
    modal.classList.remove('open');
    selectedMode = null;
    if (statusEl) statusEl.textContent = '';
    if (resultEl) resultEl.textContent = 'Pick an option to get a tailored recommendation.';
    if (form) form.classList.add('hidden');
    if (uploadField) uploadField.classList.add('hidden');
    if (metricsField) metricsField.classList.add('hidden');
    if (photoInput) photoInput.value = '';
    if (heightInput) heightInput.value = '';
    if (weightInput) weightInput.value = '';
  }

  // Ensure global aiAssist uses this modal
  window.aiAssist = function () {
    openModal();
  };

  if (overlay) {
    overlay.addEventListener('click', closeModal);
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', closeModal);
  }

  // Handle mode selection buttons (upload / metrics / both)
  optionsContainer.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-mode]');
    if (!btn) return;

    selectedMode = btn.dataset.mode;

    // Show form section
    form.classList.remove('hidden');

    // Toggle fields based on mode
    if (uploadField) {
      const needsUpload = selectedMode === 'upload' || selectedMode === 'both';
      uploadField.classList.toggle('hidden', !needsUpload);
    }
    if (metricsField) {
      const needsMetrics = selectedMode === 'metrics' || selectedMode === 'both';
      metricsField.classList.toggle('hidden', !needsMetrics);
    }

    if (resultEl) {
      resultEl.textContent = `Mode selected: ${selectedMode.toUpperCase()}. Fill in the details and tap Analyze.`;
    }
  });

  // Submit form to /fit-assist backend
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!selectedMode) {
      if (statusEl) statusEl.textContent = 'Please pick an option first.';
      return;
    }

    const formData = new FormData();
    formData.append('mode', selectedMode);
    formData.append('product_id', productId || 'product1');

    // Metrics
    if (selectedMode === 'metrics' || selectedMode === 'both') {
      const h = heightInput ? heightInput.value.trim() : '';
      const w = weightInput ? weightInput.value.trim() : '';
      if (!h || !w) {
        if (statusEl) statusEl.textContent = 'Enter height and weight.';
        return;
      }
      formData.append('height_cm', h);
      formData.append('weight_kg', w);
    }

    // Photo
    if (selectedMode === 'upload' || selectedMode === 'both') {
      const file = photoInput && photoInput.files && photoInput.files[0];
      if (!file) {
        if (statusEl) statusEl.textContent = 'Select a reference photo.';
        return;
      }
      formData.append('file', file);
    }

    if (statusEl) {
      statusEl.textContent = 'Analyzing fit...';
    }

    try {
      const res = await fetch(`${API_BASE}/fit-assist`, {
        method: 'POST',
        body: formData
      });

      const data = await res.json();

      if (!res.ok) {
        const msg = data.detail || data.error || 'AI fit assist failed.';
        if (statusEl) statusEl.textContent = msg;
        return;
      }

      const rec = data.recommendation || data;
      const size = rec.size || rec.recommendedSize || rec.size_label || 'M';

      if (resultEl) {
        resultEl.innerHTML = `
          Recommended size: <strong>${size}</strong><br>
          Based on your profile and our size chart.
        `;
      }
      if (statusEl) statusEl.textContent = 'Size selected for you.';

      // Auto-select the size button if present
      selectSize(size);
    } catch (err) {
      console.error('AI Assist error:', err);
      if (statusEl) statusEl.textContent = 'Network error talking to AI backend.';
    }
  });
})();
