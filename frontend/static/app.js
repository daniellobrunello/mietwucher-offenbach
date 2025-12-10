// Global state
let apartments = [];
let sortColumn = null;
let sortDirection = 'asc';
let priceChart = null;

// Price per square meter thresholds
const PRICE_LOW_THRESHOLD = 11;
const PRICE_HIGH_THRESHOLD = 13;

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    loadApartments();
    loadStatistics();
    setupEventListeners();
    updateTimestamp();
});

/**
 * Setup event listeners for filters and sorting
 */
function setupEventListeners() {
    // Filter checkboxes
    document.getElementById('filter-high-rent').addEventListener('change', applyFilters);
    document.getElementById('filter-low-rent').addEventListener('change', applyFilters);
    
    // Table header sorting
    document.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const column = th.dataset.sort;
            handleSort(column);
        });
    });
}

/**
 * Load apartments from API
 */
async function loadApartments() {
    try {
        const response = await fetch('/api/apartments');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        // API now returns array directly
        apartments = Array.isArray(data) ? data : (data.apartments || []);
        
        // Calculate price per square meter for each apartment
        apartments = apartments.map(apt => {
            const price = parseFloat(apt.price) || 0;
            const size = parseFloat(apt.size) || 0;
            const pricePerSqm = size > 0 ? price / size : 0;
            
            return {
                ...apt,
                price_per_sqm: pricePerSqm,
                price_category: getPriceCategory(pricePerSqm)
            };
        });
        
        updateStats();
        renderTable();
        
    } catch (error) {
        console.error('Error loading apartments:', error);
        document.getElementById('apartments-tbody').innerHTML = `
            <tr>
                <td colspan="9" class="empty-state">
                    <h3>Fehler beim Laden der Wohnungen</h3>
                    <p>Verbindung zum Server fehlgeschlagen. Bitte versuchen Sie es später erneut.</p>
                </td>
            </tr>
        `;
    }
}

/**
 * Load statistics from API and display them
 */
async function loadStatistics() {
    try {
        const response = await fetch('/api/statistics');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update stat cards
        document.getElementById('stat-niedrig').textContent = data.total.niedrig;
        document.getElementById('stat-normal').textContent = data.total.normal;
        document.getElementById('stat-hoch').textContent = data.total.hoch;
        
        // Create chart
        createChart(data.timeline);
        
    } catch (error) {
        console.error('Error loading statistics:', error);
        document.getElementById('stat-niedrig').textContent = 'Fehler';
        document.getElementById('stat-normal').textContent = 'Fehler';
        document.getElementById('stat-hoch').textContent = 'Fehler';
    }
}

/**
 * Create chart showing price categories over time
 */
function createChart(timeline) {
    const ctx = document.getElementById('priceChart');
    
    if (!ctx) {
        console.error('Canvas element not found');
        return;
    }
    
    // Destroy existing chart if any
    if (priceChart) {
        priceChart.destroy();
    }
    
    // Extract data for chart
    const labels = timeline.map(item => {
        const date = new Date(item.date);
        return date.toLocaleDateString('de-DE', { month: 'short', day: 'numeric' });
    });
    
    const niedrigData = timeline.map(item => item.niedrig);
    const normalData = timeline.map(item => item.normal);
    const hochData = timeline.map(item => item.hoch);
    
    // Create chart
    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Niedrig (≤ 11 EUR/m²)',
                    data: niedrigData,
                    borderColor: '#22c55e',
                    backgroundColor: 'rgba(34, 197, 94, 0.1)',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: true,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#22c55e'
                },
                {
                    label: 'Normal (11-13 EUR/m²)',
                    data: normalData,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: true,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#3b82f6'
                },
                {
                    label: 'Hoch (> 13 EUR/m²)',
                    data: hochData,
                    borderColor: '#ef4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: true,
                    pointRadius: 3,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#ef4444'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#374151',
                        font: {
                            size: 13,
                            family: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
                        },
                        padding: 15,
                        usePointStyle: true,
                        boxWidth: 8,
                        boxHeight: 8
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#ffffff',
                    bodyColor: '#ffffff',
                    borderColor: '#e5e7eb',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    titleFont: {
                        size: 13,
                        weight: '600'
                    },
                    bodyFont: {
                        size: 12
                    },
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + context.parsed.y + ' Wohnungen';
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: '#f3f4f6',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b7280',
                        maxRotation: 45,
                        minRotation: 45,
                        font: {
                            size: 11
                        }
                    }
                },
                y: {
                    grid: {
                        color: '#f3f4f6',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#6b7280',
                        font: {
                            size: 11
                        },
                        stepSize: 1
                    },
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Anzahl Wohnungen',
                        color: '#374151',
                        font: {
                            size: 12,
                            weight: '600'
                        }
                    }
                }
            }
        }
    });
}

/**
 * Get price category based on price per square meter
 */
function getPriceCategory(pricePerSqm) {
    if (pricePerSqm <= PRICE_LOW_THRESHOLD) return 'low';
    if (pricePerSqm <= PRICE_HIGH_THRESHOLD) return 'normal';
    return 'high';
}

/**
 * Update statistics in header
 */
function updateStats() {
    const highRentCount = apartments.filter(apt => apt.price_category === 'high').length;
    const lowRentCount = apartments.filter(apt => apt.price_category === 'low').length;
    
    document.getElementById('total-count').textContent = 
        `Gesamt: ${apartments.length} Wohnungen`;
    
    document.getElementById('high-rent-count').textContent = 
        `Hoch: ${highRentCount} | Niedrig: ${lowRentCount}`;
}

/**
 * Apply filters to the table
 */
function applyFilters() {
    const filterHighRent = document.getElementById('filter-high-rent').checked;
    const filterLowRent = document.getElementById('filter-low-rent').checked;
    
    const rows = document.querySelectorAll('#apartments-tbody tr');
    
    rows.forEach((row, index) => {
        if (index >= apartments.length) return; // Skip if out of bounds
        
        const apt = apartments[index];
        let show = true;
        
        if (filterHighRent && filterLowRent) {
            // Show only high OR low
            show = apt.price_category === 'high' || apt.price_category === 'low';
        } else if (filterHighRent) {
            show = apt.price_category === 'high';
        } else if (filterLowRent) {
            show = apt.price_category === 'low';
        }
        
        row.classList.toggle('hidden', !show);
    });
}

/**
 * Handle sorting of table columns
 */
function handleSort(column) {
    if (sortColumn === column) {
        // Toggle direction if same column
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        // New column, default to ascending
        sortColumn = column;
        sortDirection = 'asc';
    }
    
    // Sort apartments array
    apartments.sort((a, b) => {
        let aVal = a[column];
        let bVal = b[column];
        
        // Handle special cases
        if (column === 'price' || column === 'size') {
            aVal = parseFloat(aVal) || 0;
            bVal = parseFloat(bVal) || 0;
        } else if (column === 'rooms') {
            aVal = parseFloat(aVal) || 0;
            bVal = parseFloat(bVal) || 0;
        } else if (column === 'price_per_sqm') {
            aVal = a.price_per_sqm || 0;
            bVal = b.price_per_sqm || 0;
        } else if (column === 'furnished') {
            // Sort furnished: yes > no > unknown
            aVal = getFurnishedSortValue(aVal);
            bVal = getFurnishedSortValue(bVal);
        } else {
            aVal = String(aVal || '').toLowerCase();
            bVal = String(bVal || '').toLowerCase();
        }
        
        if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
        return 0;
    });
    
    renderTable();
}

/**
 * Render the table with current apartments
 */
function renderTable() {
    const tbody = document.getElementById('apartments-tbody');
    
    if (apartments.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="empty-state">
                    <h3>Keine Wohnungen gefunden</h3>
                    <p>Es sind noch keine Wohnungen in der Datenbank.</p>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = apartments.map(apt => createTableRow(apt)).join('');
    
    // Reapply filters after rendering
    applyFilters();
}

/**
 * Create a table row for an apartment
 */
function createTableRow(apt) {
    const pricePerSqm = apt.price_per_sqm > 0 
        ? apt.price_per_sqm.toFixed(2) 
        : 'N/A';
    
    const priceClass = apt.price_category;
    const rowClass = `price-${priceClass}`;
    
    // Format furnished status
    const furnishedBadge = getFurnishedBadge(apt.furnished);
    
    // Check if we should show "Verklagen" button
    const shouldShowReportButton = apt.price_category === 'high' && !isFurnished(apt.furnished);
    const reportButton = shouldShowReportButton 
                ? `<a href="${generateReportEmail(apt)}" class="btn-report" title="Mietwucher melden">VERKLAGEN</a>`
        : '';
    
    return `
        <tr class="${rowClass}">
            <td class="title-cell">
                <strong>${escapeHtml(apt.title || 'Ohne Titel')}</strong>
            </td>
            <td>${escapeHtml(apt.address || 'N/A')}</td>
            <td>${escapeHtml(apt.price_str || 'N/A')}</td>
            <td>${escapeHtml(apt.size_str || 'N/A')}</td>
            <td>${escapeHtml(apt.rooms || 'N/A')}</td>
            <td class="price-cell ${priceClass}">${pricePerSqm} €/m²</td>
            <td class="furnished-cell">${furnishedBadge}</td>
            <td>${escapeHtml(apt.crawler || 'N/A')}</td>
            <td class="link-cell">
                <a href="${escapeHtml(apt.url)}" target="_blank" rel="noopener noreferrer" class="btn-view">
                    Ansehen →
                </a>
                ${reportButton}
            </td>
        </tr>
    `;
}

/**
 * Get furnished badge HTML
 */
function getFurnishedBadge(furnished) {
    if (!furnished || furnished === 'N/A' || furnished === 'None' || furnished === 'null') {
        return '<span class="badge badge-unknown">?</span>';
    }
    
    const furnishedLower = String(furnished).toLowerCase();
    
    if (furnishedLower === 'ja' || furnishedLower === 'yes' || furnishedLower === 'true' || 
        furnishedLower === 'möbliert' || furnishedLower === 'teilmöbliert') {
        return '<span class="badge badge-yes">JA</span>';
    }
    
    if (furnishedLower === 'nein' || furnishedLower === 'no' || furnishedLower === 'false' || 
        furnishedLower === 'unmöbliert') {
        return '<span class="badge badge-no">NEIN</span>';
    }
    
    return '<span class="badge badge-unknown">N/A</span>';
}

/**
 * Get sort value for furnished status (for sorting)
 */
function getFurnishedSortValue(furnished) {
    if (!furnished || furnished === 'N/A' || furnished === 'None' || furnished === 'null') {
        return 0; // Unknown
    }
    
    const furnishedLower = String(furnished).toLowerCase();
    
    if (furnishedLower === 'ja' || furnishedLower === 'yes' || furnishedLower === 'true' || 
        furnishedLower === 'möbliert' || furnishedLower === 'teilmöbliert') {
        return 2; // Yes (highest)
    }
    
    if (furnishedLower === 'nein' || furnishedLower === 'no' || furnishedLower === 'false' || 
        furnishedLower === 'unmöbliert') {
        return 1; // No
    }
    
    return 0; // Unknown
}

/**
 * Check if apartment is furnished
 */
function isFurnished(furnished) {
    if (!furnished || furnished === 'N/A' || furnished === 'None' || furnished === 'null') {
        return false;
    }
    
    const furnishedLower = String(furnished).toLowerCase();
    
    return furnishedLower === 'ja' || furnishedLower === 'yes' || furnishedLower === 'true' || 
           furnishedLower === 'möbliert' || furnishedLower === 'teilmöbliert';
}

/**
 * Generate mailto link for reporting rent profiteering
 */
function generateReportEmail(apt) {
    const recipient = 'ordnungsamt@offenbach.de';
    const subject = 'Anzeige Mietwucher';
    
    const body = `Sehr geehrte Damen und Herren,

hiermit möchte ich einen möglichen Fall von Mietwucher gemäß § 291 StGB zur Prüfung anzeigen.

ANGABEN ZUR WOHNUNG:
─────────────────────────────────────────
• Titel: ${apt.title || 'Ohne Titel'}
• Adresse: ${apt.address || 'Nicht angegeben'}
• Miete: ${apt.price_str || 'N/A'}
• Wohnfläche: ${apt.size_str || 'N/A'}
• Zimmer: ${apt.rooms || 'N/A'}
• Preis pro m²: ${apt.price_per_sqm ? apt.price_per_sqm.toFixed(2) + ' EUR/m²' : 'N/A'}
• Möblierung: ${apt.furnished === 'ja' || apt.furnished === 'yes' ? 'Ja' : 'Nein'}
• Link zum Inserat: ${apt.url}

RECHTLICHE GRUNDLAGEN:
─────────────────────────────────────────
Der geforderte Mietpreis liegt deutlich über dem ortsüblichen Vergleichswert. Nach § 5 WiStrG (Mietpreisüberhöhung) liegt ein Verstoß vor, wenn die Miete die ortsübliche Vergleichsmiete um mehr als 20% übersteigt.

Gemäß § 291 StGB (Wucher) macht sich strafbar, wer unter Ausbeutung der Zwangslage, der Unerfahrenheit, des Mangels an Urteilsvermögen oder der erheblichen Willensschwäche eines anderen sich für eine Leistung Vermögensvorteile versprechen oder gewähren lässt, die in einem auffälligen Missverhältnis zu der Leistung stehen.

BITTE UM PRÜFUNG:
─────────────────────────────────────────
Ich bitte Sie höflich, diesen Sachverhalt zu prüfen und gegebenenfalls die erforderlichen rechtlichen Schritte einzuleiten. Die aktuelle Wohnungsnot wird durch solche überhöhten Mietforderungen weiter verschärft.

Für Rückfragen stehe ich Ihnen gerne zur Verfügung.

Mit freundlichen Grüßen

[Ihr Name]
[Ihre Adresse]
[Ihre Telefonnummer]
[Ihre E-Mail-Adresse]


─────────────────────────────────────────
Diese Anzeige wurde automatisch über Flathunter erstellt.
Datum: ${new Date().toLocaleDateString('de-DE', { 
    year: 'numeric', 
    month: 'long', 
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
})}`;
    
    // Encode for mailto URL
    return `mailto:${recipient}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

/**
 * Update the timestamp in the footer
 */
function updateTimestamp() {
    const now = new Date();
    const options = { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    const timestamp = now.toLocaleDateString('de-DE', options) + ' Uhr';
    const timestampElement = document.getElementById('last-update');
    if (timestampElement) {
        timestampElement.textContent = timestamp;
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}
