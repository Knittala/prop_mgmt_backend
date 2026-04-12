<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  API_BASE_URL,
  createExpense,
  createIncome,
  getArrears,
  getExpenses,
  getIncomeRecords,
  getProperties,
  getVacantProperties,
  markExpensePaid,
  updateProperty,
} from './api'

const properties = ref([])
const propertiesLoading = ref(false)
const propertiesError = ref('')
const selectedPropertyId = ref('')

const incomeRecords = ref([])
const incomeLoading = ref(false)
const incomeError = ref('')

const expenses = ref([])
const expensesLoading = ref(false)
const expensesError = ref('')

const vacantProperties = ref([])
const vacantLoading = ref(false)
const vacantError = ref('')

const arrears = ref([])
const arrearsLoading = ref(false)
const arrearsError = ref('')

const propertyUpdateForm = reactive({
  name: '',
  tenant_name: '',
  monthly_rent: '',
})

const incomeForm = reactive({
  amount: '',
  source: '',
  payment_date: '',
})

const expenseForm = reactive({
  amount: '',
  category: '',
  description: '',
  expense_date: '',
})

const propertyFeedback = ref(null)
const incomeFeedback = ref(null)
const expenseFeedback = ref(null)

const hasProperties = computed(() => properties.value.length > 0)

const selectedProperty = computed(() =>
  properties.value.find((property) => String(property.property_id) === selectedPropertyId.value),
)

function formatCurrency(value) {
  const amount = Number(value)
  return Number.isFinite(amount) ? amount.toFixed(2) : '0.00'
}

function setFeedback(target, type, message) {
  target.value = { type, message }
}

function resetPropertyForm() {
  propertyUpdateForm.name = ''
  propertyUpdateForm.tenant_name = ''
  propertyUpdateForm.monthly_rent = ''
}

function resetIncomeForm() {
  incomeForm.amount = ''
  incomeForm.source = ''
  incomeForm.payment_date = ''
}

function resetExpenseForm() {
  expenseForm.amount = ''
  expenseForm.category = ''
  expenseForm.description = ''
  expenseForm.expense_date = ''
}

async function loadProperties() {
  propertiesLoading.value = true
  propertiesError.value = ''

  try {
    const result = await getProperties()
    properties.value = Array.isArray(result) ? result : []

    const stillExists = properties.value.some(
      (property) => String(property.property_id) === selectedPropertyId.value,
    )

    if (!stillExists) {
      selectedPropertyId.value = properties.value.length
        ? String(properties.value[0].property_id)
        : ''
    }
  } catch (error) {
    propertiesError.value = error.message
    properties.value = []
    selectedPropertyId.value = ''
  } finally {
    propertiesLoading.value = false
  }
}

async function loadIncome() {
  if (!selectedPropertyId.value) {
    incomeRecords.value = []
    return
  }

  incomeLoading.value = true
  incomeError.value = ''
  try {
    const result = await getIncomeRecords(Number(selectedPropertyId.value))
    incomeRecords.value = Array.isArray(result) ? result : []
  } catch (error) {
    incomeError.value = error.message
    incomeRecords.value = []
  } finally {
    incomeLoading.value = false
  }
}

async function loadExpenses() {
  if (!selectedPropertyId.value) {
    expenses.value = []
    return
  }

  expensesLoading.value = true
  expensesError.value = ''
  try {
    const result = await getExpenses(Number(selectedPropertyId.value))
    expenses.value = Array.isArray(result) ? result : []
  } catch (error) {
    expensesError.value = error.message
    expenses.value = []
  } finally {
    expensesLoading.value = false
  }
}

async function loadVacantProperties() {
  vacantLoading.value = true
  vacantError.value = ''
  try {
    const result = await getVacantProperties()
    vacantProperties.value = Array.isArray(result) ? result : []
  } catch (error) {
    vacantError.value = error.message
    vacantProperties.value = []
  } finally {
    vacantLoading.value = false
  }
}

async function loadArrears() {
  arrearsLoading.value = true
  arrearsError.value = ''
  try {
    const result = await getArrears()
    arrears.value = Array.isArray(result) ? result : []
  } catch (error) {
    arrearsError.value = error.message
    arrears.value = []
  } finally {
    arrearsLoading.value = false
  }
}

async function loadSelectedPropertyData() {
  await Promise.all([loadIncome(), loadExpenses()])
}

async function submitPropertyUpdate() {
  propertyFeedback.value = null
  if (!selectedPropertyId.value) {
    setFeedback(propertyFeedback, 'error', 'Select a property first.')
    return
  }

  const payload = {}
  if (propertyUpdateForm.name.trim()) {
    payload.name = propertyUpdateForm.name.trim()
  }
  if (propertyUpdateForm.tenant_name.trim()) {
    payload.tenant_name = propertyUpdateForm.tenant_name.trim()
  }
  if (propertyUpdateForm.monthly_rent !== '') {
    const parsedRent = Number(propertyUpdateForm.monthly_rent)
    if (Number.isNaN(parsedRent)) {
      setFeedback(propertyFeedback, 'error', 'Monthly rent must be a valid number.')
      return
    }
    payload.monthly_rent = parsedRent
  }

  if (Object.keys(payload).length === 0) {
    setFeedback(propertyFeedback, 'error', 'Enter at least one field to update.')
    return
  }

  try {
    await updateProperty(Number(selectedPropertyId.value), payload)
    setFeedback(propertyFeedback, 'success', 'Property updated successfully.')
    resetPropertyForm()
    await loadProperties()
  } catch (error) {
    setFeedback(propertyFeedback, 'error', error.message)
  }
}

async function submitIncome() {
  incomeFeedback.value = null
  if (!selectedPropertyId.value) {
    setFeedback(incomeFeedback, 'error', 'Select a property before adding income.')
    return
  }

  const payload = {
    amount: Number(incomeForm.amount),
    source: incomeForm.source.trim(),
    payment_date: incomeForm.payment_date,
  }

  if (Number.isNaN(payload.amount)) {
    setFeedback(incomeFeedback, 'error', 'Income amount must be a number.')
    return
  }

  try {
    await createIncome(Number(selectedPropertyId.value), payload)
    setFeedback(incomeFeedback, 'success', 'Income record added.')
    resetIncomeForm()
    await loadIncome()
  } catch (error) {
    setFeedback(incomeFeedback, 'error', error.message)
  }
}

async function submitExpense() {
  expenseFeedback.value = null
  if (!selectedPropertyId.value) {
    setFeedback(expenseFeedback, 'error', 'Select a property before adding an expense.')
    return
  }

  const payload = {
    amount: Number(expenseForm.amount),
    category: expenseForm.category.trim(),
    description: expenseForm.description.trim(),
    expense_date: expenseForm.expense_date,
  }

  if (Number.isNaN(payload.amount)) {
    setFeedback(expenseFeedback, 'error', 'Expense amount must be a number.')
    return
  }

  try {
    await createExpense(Number(selectedPropertyId.value), payload)
    setFeedback(expenseFeedback, 'success', 'Expense created.')
    resetExpenseForm()
    await loadExpenses()
    await loadArrears()
  } catch (error) {
    setFeedback(expenseFeedback, 'error', error.message)
  }
}

async function payExpense(expenseId) {
  expenseFeedback.value = null
  try {
    await markExpensePaid(expenseId)
    setFeedback(expenseFeedback, 'success', `Expense ${expenseId} marked as paid.`)
    await loadExpenses()
  } catch (error) {
    setFeedback(expenseFeedback, 'error', error.message)
  }
}

watch(selectedPropertyId, async () => {
  propertyFeedback.value = null
  incomeFeedback.value = null
  expenseFeedback.value = null
  await loadSelectedPropertyData()
})

onMounted(async () => {
  await loadProperties()
  await Promise.all([loadSelectedPropertyData(), loadVacantProperties(), loadArrears()])
})
</script>

<template>
  <main class="layout">
    <header>
      <h1>Property Management Dashboard</h1>
      <p>
        Front-end API target:
        <code>{{ API_BASE_URL }}</code>
      </p>
    </header>

    <section class="panel">
      <div class="panel-header">
        <h2>Properties</h2>
        <button type="button" @click="loadProperties" :disabled="propertiesLoading">
          {{ propertiesLoading ? "Refreshing..." : "Refresh" }}
        </button>
      </div>

      <p v-if="propertiesError" class="feedback error">{{ propertiesError }}</p>
      <p v-else-if="propertiesLoading">Loading properties...</p>
      <p v-else-if="properties.length === 0" class="empty-state">
        No properties found. The app stays usable and shows empty lists instead of failing.
      </p>
      <div v-else class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Tenant</th>
              <th>Rent</th>
              <th>City</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="property in properties" :key="property.property_id">
              <td>{{ property.property_id }}</td>
              <td>{{ property.name }}</td>
              <td>{{ property.tenant_name || "Vacant" }}</td>
              <td>${{ formatCurrency(property.monthly_rent) }}</td>
              <td>{{ property.city }}</td>
              <td>{{ property.state }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>Property Actions</h2>

      <div class="field-group">
        <label for="property-picker">Select property</label>
        <select id="property-picker" v-model="selectedPropertyId" :disabled="!hasProperties">
          <option value="" disabled>Select property...</option>
          <option v-for="property in properties" :key="property.property_id" :value="String(property.property_id)">
            #{{ property.property_id }} - {{ property.name }}
          </option>
        </select>
      </div>

      <p v-if="selectedProperty" class="context-line">
        Managing: <strong>{{ selectedProperty.name }}</strong>
      </p>

      <form class="stack" @submit.prevent="submitPropertyUpdate">
        <h3>Update Property</h3>
        <div class="grid">
          <label>
            Name
            <input v-model="propertyUpdateForm.name" type="text" placeholder="Updated name" />
          </label>
          <label>
            Tenant name
            <input v-model="propertyUpdateForm.tenant_name" type="text" placeholder="Updated tenant" />
          </label>
          <label>
            Monthly rent
            <input v-model="propertyUpdateForm.monthly_rent" type="number" min="0" step="0.01" placeholder="1950.00" />
          </label>
        </div>
        <button type="submit">Submit Property Update</button>
        <p v-if="propertyFeedback" class="feedback" :class="propertyFeedback.type">
          {{ propertyFeedback.message }}
        </p>
      </form>
    </section>

    <section class="panel panel-grid">
      <div>
        <h2>Income</h2>

        <form class="stack" @submit.prevent="submitIncome">
          <div class="grid">
            <label>
              Amount
              <input v-model="incomeForm.amount" type="number" min="0" step="0.01" required />
            </label>
            <label>
              Source
              <input v-model="incomeForm.source" type="text" placeholder="Rent payment" required />
            </label>
            <label>
              Payment date
              <input v-model="incomeForm.payment_date" type="date" required />
            </label>
          </div>
          <button type="submit">Add Income</button>
          <p v-if="incomeFeedback" class="feedback" :class="incomeFeedback.type">
            {{ incomeFeedback.message }}
          </p>
        </form>

        <p v-if="incomeError" class="feedback error">{{ incomeError }}</p>
        <p v-else-if="incomeLoading">Loading income...</p>
        <ul v-else-if="incomeRecords.length" class="list">
          <li v-for="record in incomeRecords" :key="record.income_id">
            <div>
              <strong>${{ formatCurrency(record.amount) }}</strong>
              <span>{{ record.source }}</span>
            </div>
            <time>{{ record.payment_date }}</time>
          </li>
        </ul>
        <p v-else class="empty-state">
          No income records for this property yet.
        </p>
      </div>

      <div>
        <h2>Expenses</h2>
        <form class="stack" @submit.prevent="submitExpense">
          <div class="grid">
            <label>
              Amount
              <input v-model="expenseForm.amount" type="number" min="0" step="0.01" required />
            </label>
            <label>
              Category
              <input v-model="expenseForm.category" type="text" placeholder="Maintenance" required />
            </label>
            <label>
              Expense date
              <input v-model="expenseForm.expense_date" type="date" required />
            </label>
            <label class="full-width">
              Description
              <input v-model="expenseForm.description" type="text" placeholder="Describe the expense" required />
            </label>
          </div>
          <button type="submit">Add Expense</button>
          <p v-if="expenseFeedback" class="feedback" :class="expenseFeedback.type">
            {{ expenseFeedback.message }}
          </p>
        </form>

        <p v-if="expensesError" class="feedback error">{{ expensesError }}</p>
        <p v-else-if="expensesLoading">Loading expenses...</p>
        <ul v-else-if="expenses.length" class="list">
          <li v-for="expense in expenses" :key="expense.expense_id">
            <div>
              <strong>${{ formatCurrency(expense.amount) }}</strong>
              <span>{{ expense.category }} - {{ expense.description }}</span>
              <span class="badge" :class="expense.status === 'Paid' ? 'paid' : 'pending'">
                {{ expense.status }}
              </span>
            </div>
            <div class="row-end">
              <time>{{ expense.expense_date }}</time>
              <button
                v-if="expense.status !== 'Paid'"
                type="button"
                class="small-btn"
                @click="payExpense(expense.expense_id)"
              >
                Mark Paid
              </button>
            </div>
          </li>
        </ul>
        <p v-else class="empty-state">
          No expenses recorded for this property yet.
        </p>
      </div>
    </section>

    <section class="panel panel-grid">
      <div>
        <div class="panel-header">
          <h2>Vacant Properties</h2>
          <button type="button" @click="loadVacantProperties" :disabled="vacantLoading">
            {{ vacantLoading ? "Refreshing..." : "Refresh" }}
          </button>
        </div>
        <p v-if="vacantError" class="feedback error">{{ vacantError }}</p>
        <p v-else-if="vacantLoading">Loading vacant properties...</p>
        <ul v-else-if="vacantProperties.length" class="list">
          <li v-for="property in vacantProperties" :key="property.property_id">
            <div>
              <strong>#{{ property.property_id }} {{ property.name }}</strong>
              <span>{{ property.city }}, {{ property.state }}</span>
            </div>
          </li>
        </ul>
        <p v-else class="empty-state">No vacant properties at the moment.</p>
      </div>

      <div>
        <div class="panel-header">
          <h2>Current Arrears</h2>
          <button type="button" @click="loadArrears" :disabled="arrearsLoading">
            {{ arrearsLoading ? "Refreshing..." : "Refresh" }}
          </button>
        </div>
        <p v-if="arrearsError" class="feedback error">{{ arrearsError }}</p>
        <p v-else-if="arrearsLoading">Loading arrears...</p>
        <ul v-else-if="arrears.length" class="list">
          <li v-for="row in arrears" :key="row.property_id">
            <div>
              <strong>{{ row.name }}</strong>
              <span>{{ row.tenant_name }}</span>
            </div>
            <div class="row-end">
              <span>Paid: ${{ formatCurrency(row.paid) }}</span>
              <strong>Debt: ${{ formatCurrency(row.debt) }}</strong>
            </div>
          </li>
        </ul>
        <p v-else class="empty-state">No arrears currently reported.</p>
      </div>
    </section>
  </main>
</template>
