<template>
  <div class="restocking">
    <div class="page-header">
      <h2>Restocking</h2>
      <p>Set a budget and submit a restock order based on demand forecasts.</p>
    </div>

    <div v-if="loading" class="loading">Loading...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div v-if="lastSubmittedOrder" class="success-banner">
        <strong>Order {{ lastSubmittedOrder.order_number }} submitted.</strong>
        Expected delivery: {{ formatDate(lastSubmittedOrder.expected_delivery) }}.
        <router-link to="/orders" class="banner-link">View in Orders</router-link>
      </div>

      <div class="card controls-card">
        <div class="card-header">
          <h3 class="card-title">Budget &amp; Lead Time</h3>
          <div class="totals-inline">
            <span class="totals-label">Budget</span>
            <span class="totals-value">${{ budget.toLocaleString() }}</span>
          </div>
        </div>
        <div class="controls">
          <div class="slider-row">
            <input
              type="range"
              min="0"
              max="200000"
              step="1000"
              v-model.number="budget"
              class="slider"
              aria-label="Budget"
            />
            <div class="slider-bounds">
              <span>$0</span>
              <span>$200,000</span>
            </div>
          </div>
          <div class="lead-time-row">
            <label for="lead-time">Delivery lead time</label>
            <select id="lead-time" v-model.number="leadTimeDays" class="lead-time-select">
              <option :value="7">7 days</option>
              <option :value="14">14 days</option>
              <option :value="30">30 days</option>
            </select>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">Recommended Restocks ({{ recommendations.picks.length }})</h3>
          <div class="summary-row">
            <span class="summary-chip">Total: <strong>${{ recommendations.total.toLocaleString(undefined, { maximumFractionDigits: 2 }) }}</strong></span>
            <span class="summary-chip">Remaining: <strong>${{ remaining.toLocaleString(undefined, { maximumFractionDigits: 2 }) }}</strong></span>
          </div>
        </div>

        <div v-if="recommendations.picks.length === 0" class="empty-state">
          No items fit within the current budget. Raise the budget to see recommendations.
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>SKU</th>
                <th>Item</th>
                <th>Trend</th>
                <th>Current → Forecast</th>
                <th>Quantity</th>
                <th>Unit Cost</th>
                <th>Line Cost</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="pick in recommendations.picks" :key="pick.sku">
                <td><strong>{{ pick.sku }}</strong></td>
                <td>{{ pick.name }}</td>
                <td>
                  <span :class="['badge', pick.trend]">{{ pick.trend }}</span>
                </td>
                <td>{{ pick.current_demand }} → {{ pick.forecasted_demand }}</td>
                <td>{{ pick.quantity.toLocaleString() }}</td>
                <td>${{ pick.unit_price.toFixed(2) }}</td>
                <td><strong>${{ pick.line_cost.toLocaleString(undefined, { maximumFractionDigits: 2 }) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="actions">
          <button
            type="button"
            class="btn-primary"
            :disabled="recommendations.picks.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? 'Submitting…' : 'Place Order' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'

export default {
  name: 'Restocking',
  setup() {
    const loading = ref(true)
    const error = ref(null)
    const submitting = ref(false)
    const lastSubmittedOrder = ref(null)

    const forecasts = ref([])
    const inventory = ref([])

    const budget = ref(50000)
    const leadTimeDays = ref(14)

    const skuToInventory = computed(() => {
      const m = new Map()
      for (const item of inventory.value) m.set(item.sku, item)
      return m
    })

    const recommendations = computed(() => {
      const trendRank = { increasing: 0, stable: 1, decreasing: 2 }
      const sorted = [...forecasts.value]
        .filter(f => f.forecasted_demand > f.current_demand && skuToInventory.value.has(f.item_sku))
        .sort((a, b) => {
          const tr = (trendRank[a.trend] ?? 99) - (trendRank[b.trend] ?? 99)
          if (tr !== 0) return tr
          return b.forecasted_demand - a.forecasted_demand
        })

      const picks = []
      let spent = 0
      // Greedy fit: iterate by priority and include any items whose line cost still fits.
      // Cheaper items further down the list can still be picked up after a too-expensive one is skipped.
      for (const f of sorted) {
        const inv = skuToInventory.value.get(f.item_sku)
        const qty = f.forecasted_demand - f.current_demand
        const unitPrice = inv.unit_cost
        const lineCost = qty * unitPrice
        if (spent + lineCost > budget.value) continue
        picks.push({
          sku: f.item_sku,
          name: f.item_name,
          quantity: qty,
          unit_price: unitPrice,
          line_cost: lineCost,
          trend: f.trend,
          current_demand: f.current_demand,
          forecasted_demand: f.forecasted_demand,
        })
        spent += lineCost
      }
      return { picks, total: spent }
    })

    const remaining = computed(() => budget.value - recommendations.value.total)

    const formatDate = (dateString) => {
      if (!dateString) return ''
      const d = new Date(dateString)
      if (isNaN(d.getTime())) return dateString
      return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    }

    const loadData = async () => {
      try {
        loading.value = true
        error.value = null
        const [forecastsData, inventoryData] = await Promise.all([
          api.getDemandForecasts(),
          api.getInventory()
        ])
        forecasts.value = forecastsData
        inventory.value = inventoryData
      } catch (err) {
        error.value = 'Failed to load data: ' + err.message
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      if (recommendations.value.picks.length === 0) return
      try {
        submitting.value = true
        error.value = null
        const payload = {
          items: recommendations.value.picks.map(p => ({
            sku: p.sku,
            name: p.name,
            quantity: p.quantity,
            unit_price: p.unit_price,
          })),
          lead_time_days: leadTimeDays.value,
        }
        const created = await api.createOrder(payload)
        lastSubmittedOrder.value = created
      } catch (err) {
        error.value = 'Failed to place order: ' + err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadData)

    return {
      loading,
      error,
      submitting,
      lastSubmittedOrder,
      budget,
      leadTimeDays,
      recommendations,
      remaining,
      placeOrder,
      formatDate,
    }
  }
}
</script>

<style scoped>
.controls-card {
  margin-bottom: 1.25rem;
}

.controls {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.slider-row {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.slider {
  width: 100%;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: #e2e8f0;
  border-radius: 3px;
  outline: none;
}

.slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.slider-bounds {
  display: flex;
  justify-content: space-between;
  font-size: 0.813rem;
  color: #64748b;
}

.lead-time-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.lead-time-row label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #334155;
}

.lead-time-select {
  padding: 0.4rem 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 0.875rem;
  color: #0f172a;
  background: white;
  cursor: pointer;
}

.lead-time-select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.totals-inline {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.totals-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  font-weight: 600;
}

.totals-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.summary-row {
  display: flex;
  gap: 0.75rem;
}

.summary-chip {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.375rem 0.75rem;
  font-size: 0.813rem;
  color: #475569;
}

.summary-chip strong {
  color: #0f172a;
  margin-left: 0.25rem;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.actions {
  margin-top: 1.25rem;
  display: flex;
  justify-content: flex-end;
}

.btn-primary {
  background: #2563eb;
  color: white;
  border: none;
  padding: 0.625rem 1.5rem;
  font-size: 0.938rem;
  font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.success-banner {
  background: #d1fae5;
  border: 1px solid #6ee7b7;
  color: #065f46;
  padding: 0.875rem 1.125rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
  font-size: 0.938rem;
}

.banner-link {
  margin-left: 0.75rem;
  color: #065f46;
  text-decoration: underline;
  font-weight: 600;
}
</style>
