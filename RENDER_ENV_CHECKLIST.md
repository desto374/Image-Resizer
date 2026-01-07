# Render Environment Checklist

Set these environment variables in Render for the FastAPI backend:

- ENV=prod
- COOKIE_SAMESITE=none
- COOKIE_SECURE=true
- GOOGLE_CLIENT_ID=your-google-client-id
- GOOGLE_CLIENT_SECRET=your-google-client-secret
- GOOGLE_REDIRECT_URL=https://image-resizer-deao.onrender.com/api/auth/google/callback
- FRONTEND_REDIRECT_URL=https://desto374.github.io/Image-Resizer/Landing.html
- SESSION_SECRET=use-a-long-random-string

Optional:
- PORT is provided by Render automatically.

Make sure your Google OAuth client has:
- Authorized redirect URI: https://image-resizer-deao.onrender.com/api/auth/google/callback
- Authorized JS origins: https://desto374.github.io
