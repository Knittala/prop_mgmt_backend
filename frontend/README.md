# Property Management Frontend (Vue)

This directory contains the Vue single-page application for the Property Management App.

## API configuration

The UI calls the backend API URL via:

- `VITE_API_BASE_URL` (optional environment variable)
- fallback default: `https://prop-mgmt-api-315889448859.us-central1.run.app`

Example:

```bash
VITE_API_BASE_URL=https://prop-mgmt-api-315889448859.us-central1.run.app npm run dev
```

## Local development

```bash
npm install
npm run dev
```

## Production build

```bash
npm run build
```

## Deploy to Google Cloud Run

Build and deploy from this `frontend/` directory:

```bash
gcloud run deploy prop-mgmt-frontend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```
