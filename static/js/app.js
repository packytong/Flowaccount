/* ========================================
   FlowAccount Clone - Main JavaScript
   ======================================== */

// ==================== ITEM ROW MANAGEMENT ====================

function addRow() {
    const tbody = document.getElementById('itemsBody');
    if (!tbody) return;

    const rowCount = tbody.querySelectorAll('.item-row').length + 1;
    const tr = document.createElement('tr');
    tr.className = 'item-row';
    tr.innerHTML = `
        <td>${rowCount}</td>
        <td><input type="text" name="item_description[]" value="" placeholder="รายละเอียดสินค้า/บริการ"></td>
        <td><input type="number" name="item_quantity[]" value="" step="any" min="0" class="qty-input" onchange="calcRow(this)"></td>
        <td><input type="text" name="item_unit[]" value="" placeholder="หน่วย"></td>
        <td><input type="number" name="item_unit_price[]" value="" step="any" min="0" class="price-input" onchange="calcRow(this)"></td>
        <td class="amount-cell">
            <span class="row-amount">0.00</span>
            <input type="hidden" name="item_amount[]" value="0">
        </td>
        <td class="row-delete"><button type="button" onclick="removeRow(this)"><i class="ri-close-line"></i></button></td>
    `;
    tbody.appendChild(tr);

    // Focus new description input
    tr.querySelector('input[name="item_description[]"]').focus();
}

function removeRow(btn) {
    const tbody = document.getElementById('itemsBody');
    const rows = tbody.querySelectorAll('.item-row');
    if (rows.length <= 1) return; // Keep at least 1 row

    btn.closest('tr').remove();
    renumberRows();
    calcTotals();
}

function renumberRows() {
    const tbody = document.getElementById('itemsBody');
    if (!tbody) return;
    const rows = tbody.querySelectorAll('.item-row');
    rows.forEach((row, i) => {
        row.querySelector('td:first-child').textContent = i + 1;
    });
}

// ==================== CALCULATIONS ====================

function calcRow(input) {
    const row = input.closest('tr');
    const qty = parseFloat(row.querySelector('.qty-input')?.value) || 0;
    const price = parseFloat(row.querySelector('.price-input')?.value) || 0;
    const amount = qty * price;

    row.querySelector('.row-amount').textContent = formatNumber(amount);
    row.querySelector('input[name="item_amount[]"]').value = amount.toFixed(2);

    calcTotals();
}

function calcTotals() {
    const rows = document.querySelectorAll('.item-row');
    let subtotal = 0;

    rows.forEach(row => {
        const amountInput = row.querySelector('input[name="item_amount[]"]');
        if (amountInput) {
            subtotal += parseFloat(amountInput.value) || 0;
        }
    });

    // Discount
    const discountPercent = parseFloat(document.getElementById('discountPercent')?.value) || 0;
    const discountAmount = subtotal * (discountPercent / 100);
    const afterDiscount = subtotal - discountAmount;

    // VAT
    const vatEnabled = document.getElementById('vatEnabled')?.checked;
    const vatAmount = vatEnabled ? afterDiscount * 0.07 : 0;
    const grandTotal = afterDiscount + vatAmount;

    // Withholding tax
    const whtEnabled = document.getElementById('whtEnabled')?.checked;
    const whtPercent = parseFloat(document.getElementById('whtPercent')?.value) || 3;
    const whtAmount = whtEnabled ? afterDiscount * (whtPercent / 100) : 0;
    const netTotal = grandTotal - whtAmount;

    // Update displays
    updateValue('subtotalDisplay', 'subtotal', subtotal);
    updateValue('discountDisplay', 'discountAmount', discountAmount);
    updateValue('afterDiscountDisplay', 'afterDiscount', afterDiscount);
    updateValue('vatDisplay', 'vatAmount', vatAmount);
    updateValue('grandTotalDisplay', 'grandTotal', grandTotal);
    updateValue('whtDisplay', 'whtAmount', whtAmount);
    updateValue('netTotalDisplay', 'netTotal', netTotal);

    // Show/hide net total row
    const netTotalRow = document.getElementById('netTotalRow');
    if (netTotalRow) {
        netTotalRow.style.display = whtEnabled ? 'flex' : 'none';
    }

    // Update header grand total
    const displayGrandTotal = document.getElementById('displayGrandTotal');
    if (displayGrandTotal) {
        displayGrandTotal.textContent = '฿' + formatNumber(grandTotal);
    }
}

function updateValue(displayId, inputId, value) {
    const displayEl = document.getElementById(displayId);
    const inputEl = document.getElementById(inputId);
    if (displayEl) displayEl.textContent = formatNumber(value);
    if (inputEl) inputEl.value = value.toFixed(2);
}

function formatNumber(num) {
    return num.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// ==================== DUE DATE CALCULATION ====================

function updateDueDate() {
    const docDate = document.getElementById('docDate');
    const creditDays = document.getElementById('creditDays');
    const dueDate = document.getElementById('dueDate');

    if (!docDate || !creditDays || !dueDate) return;

    const date = new Date(docDate.value);
    const days = parseInt(creditDays.value) || 0;
    date.setDate(date.getDate() + days);

    dueDate.value = date.toISOString().split('T')[0];
}

// Listen to doc_date changes
document.addEventListener('DOMContentLoaded', function () {
    const docDate = document.getElementById('docDate');
    if (docDate) {
        docDate.addEventListener('change', updateDueDate);
    }
});

// ==================== CUSTOMER AUTOCOMPLETE ====================

let customerTimeout = null;

function initCustomerAutocomplete() {
    const input = document.getElementById('customerName');
    const dropdown = document.getElementById('customerDropdown');

    if (!input || !dropdown) return;

    input.addEventListener('input', function () {
        clearTimeout(customerTimeout);
        const query = this.value.trim();

        if (query.length < 1) {
            dropdown.classList.remove('show');
            return;
        }

        customerTimeout = setTimeout(() => {
            fetch('/api/customers?q=' + encodeURIComponent(query))
                .then(r => r.json())
                .then(customers => {
                    if (customers.length === 0) {
                        dropdown.innerHTML = '<div class="customer-dropdown-item"><div class="name" style="color:var(--accent-blue)">+ เพิ่มลูกค้าใหม่: "' + query + '"</div></div>';
                        dropdown.classList.add('show');
                        dropdown.querySelector('.customer-dropdown-item').addEventListener('click', () => {
                            document.getElementById('customerId').value = 'new';
                            dropdown.classList.remove('show');
                        });
                        return;
                    }

                    dropdown.innerHTML = customers.map(c => `
                        <div class="customer-dropdown-item" data-id="${c.id}" data-name="${c.name}" data-address="${c.address}" data-phone="${c.phone}" data-tax-id="${c.tax_id}" data-branch="${c.branch}">
                            <div class="name">${c.name}</div>
                            <div class="detail">${c.phone || ''} ${c.tax_id ? '| Tax: ' + c.tax_id : ''}</div>
                        </div>
                    `).join('');

                    dropdown.classList.add('show');

                    dropdown.querySelectorAll('.customer-dropdown-item').forEach(item => {
                        item.addEventListener('click', function () {
                            document.getElementById('customerId').value = this.dataset.id;
                            document.getElementById('customerName').value = this.dataset.name;

                            const addressField = document.querySelector('textarea[name="customer_address"]');
                            const phoneField = document.querySelector('input[name="customer_phone"]');
                            const taxField = document.querySelector('input[name="customer_tax_id"]');
                            const branchField = document.querySelector('input[name="customer_branch"]');

                            if (addressField) addressField.value = this.dataset.address || '';
                            if (phoneField) phoneField.value = this.dataset.phone || '';
                            if (taxField) taxField.value = this.dataset.taxId || '';
                            if (branchField) branchField.value = this.dataset.branch || '';

                            dropdown.classList.remove('show');
                        });
                    });
                })
                .catch(() => {
                    dropdown.classList.remove('show');
                });
        }, 300);
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function (e) {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.remove('show');
        }
    });
}

// ==================== FLASH MESSAGE AUTO-CLOSE ====================

document.addEventListener('DOMContentLoaded', function () {
    // Auto-close flash messages after 5 seconds
    document.querySelectorAll('.flash-message').forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = '0';
            msg.style.transform = 'translateY(-10px)';
            setTimeout(() => msg.remove(), 300);
        }, 5000);
    });
});
