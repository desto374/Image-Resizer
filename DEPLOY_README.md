# Deploy Guide

## Frontend (GitHub Pages)

1) Push the repo to GitHub.
2) In GitHub repo settings → Pages:
   - Source: Deploy from a branch
   - Branch: main / root
3) Your site URL:
   https://desto374.github.io/Image-Resizer/

## Backend (Render)

1) Create a new Web Service on Render.
2) Root Directory: Backend Folder-FastAPI
3) Build Command:
   pip install -r requirements.txt
4) Start Command:
   uvicorn App:app --host 0.0.0.0 --port $PORT
5) Set environment variables (see RENDER_ENV_CHECKLIST.md).

## Google OAuth

Make sure your Google OAuth client includes:
- Redirect URI: https://image-resizer-deao.onrender.com/api/auth/google/callback
- JS Origin: https://desto374.github.io

## Notes

- Frontend uses environment detection; local uses http://127.0.0.1:8000, production uses Render.
- Cookies must be SameSite=None and Secure for GitHub Pages → Render.
