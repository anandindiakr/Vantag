# Security Policy

## Secrets Management

### After pulling or first-time setup

1. **Generate `.env` from the example template:**
   ```sh
   cp .env.example .env      # Linux / macOS
   copy .env.example .env    # Windows
   ```

2. **Generate a strong JWT secret (minimum 32 characters):**
   ```sh
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Set the output as `VANTAG_JWT_SECRET` (and `JWT_SECRET_KEY`) in `.env`.

3. **Generate a Fernet encryption key for RTSP / face data:**
   ```sh
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Set the output as `VANTAG_FACE_KEY` (and `FACE_ENCRYPTION_KEY`) in `.env`.

4. **Never commit `.env`** — it is listed in `.gitignore`.  
   Only `.env.example` (with placeholder values) belongs in the repository.

---

## VPS / Production post-deploy steps

After each new deployment to a VPS or container environment:

1. **Rotate the JWT secret** — generate a new `VANTAG_JWT_SECRET` and update  
   the `EnvironmentFile=` in your systemd unit or the `--env-file` passed to Docker.  
   All existing sessions will be invalidated (users must log in again).

2. **Rotate the Fernet encryption key** — run the migration helper  
   `python -m backend.tools.reencrypt_cameras` to re-encrypt stored RTSP URLs  
   with the new key before restarting the service.

3. **RTSP credentials** — never store live `rtsp://user:pass@...` URLs in  
   `cameras.yaml`. Use `cameras.example.yaml` as a template, copy to  
   `backend/config/cameras.yaml` on the server (it is gitignored), and let the  
   application encrypt credentials on first load.

4. **Razorpay secrets** — set `RAZORPAY_KEY_SECRET_IN/SG/MY` and  
   `RAZORPAY_WEBHOOK_SECRET_IN/SG/MY` via your deployment secrets manager.  
   Never hard-code these values.

---

## Reporting a Vulnerability

Please email **security@vantag.in** with a description of the issue.  
We aim to respond within 48 hours and patch critical issues within 7 days.
