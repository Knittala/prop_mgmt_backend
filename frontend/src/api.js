const DEFAULT_BASE_URL = 'https://prop-mgmt-api-315889448859.us-central1.run.app'

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  DEFAULT_BASE_URL
).replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  if (!response.ok) {
    let message = `Request failed (${response.status})`

    try {
      const payload = await response.json()
      if (payload?.detail) {
        message = typeof payload.detail === 'string'
          ? payload.detail
          : JSON.stringify(payload.detail)
      }
    } catch {
      // Keep generic fallback message if response is not JSON.
    }

    throw new Error(message)
  }

  if (response.status === 204) {
    return null
  }

  return response.json()
}

export function getProperties() {
  return request('/properties')
}

export function updateProperty(propertyId, payload) {
  return request(`/properties/${propertyId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function getIncomeRecords(propertyId) {
  return request(`/income/${propertyId}`)
}

export function createIncome(propertyId, payload) {
  return request(`/income/${propertyId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getExpenses(propertyId) {
  return request(`/expenses/${propertyId}`)
}

export function createExpense(propertyId, payload) {
  return request(`/expenses/${propertyId}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function markExpensePaid(expenseId) {
  return request(`/expenses/${expenseId}/pay`, {
    method: 'PATCH',
  })
}

export function getVacantProperties() {
  return request('/occupancy/vacant')
}

export function getArrears() {
  return request('/income/status/arrears')
}
