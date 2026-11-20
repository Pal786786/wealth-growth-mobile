# My Funding Bank — Apne VPS pe setup (Step by step)

Ye guide Emergent se hata kar app ko apne VPS pe chalane ke liye hai.
Ek baar setup ke baad, aage ke updates sirf ek command se ho jaayenge.

## VPS pe kya-kya chalega

| Container | Kaam | Address |
|---|---|---|
| `mfb_nginx` | SSL + traffic sahi jagah bhejna + website | port 80 / 443 |
| `mfb_backend` | FastAPI API (wallet, KYC, payments, AI...) | `https://API_DOMAIN/api/...` |
| `mfb_admin` | Admin panel | `https://ADMIN_DOMAIN` |
| `mfb_mongo` | Database | sirf andar (bahar se band) |
| `mfb_backup` | Roz raat MongoDB backup | — |
| `mfb_certbot` | SSL apne aap renew | — |

**Zaroorat:** Ubuntu 22.04/24.04, kam se kam 2 GB RAM (4 GB behtar), 25 GB+ disk, root access.

---

## Step 1 — DNS set karo (domain panel mein)

Teeno domains ka **A record** VPS ke IP pe point karo:

| Type | Name | Value |
|---|---|---|
| A | `api` | VPS IP |
| A | `admin` | VPS IP |
| A | `@` (main domain) | VPS IP |

> Cloudflare use kar rahe ho to pehli baar **"DNS only" (grey cloud)** rakhna, warna SSL nahi milega.
> Check: `ping api.aapkadomain.com` → VPS ka IP dikhna chahiye.

## Step 2 — VPS mein login karke code laao

```bash
ssh root@VPS_IP

apt-get update && apt-get install -y git
git clone -b vps-deploy https://github.com/Pal786786/wealth-growth-mobile.git /opt/mfb
cd /opt/mfb
```

Repo private hai, to GitHub username aur password ki jagah **Personal Access Token** maangega:
GitHub → Settings → Developer settings → Personal access tokens → *Fine-grained* → sirf is repo ka **Contents: Read** access.
Token save karne ke liye: `git config --global credential.helper store` (pehli baar ke baad dobara nahi maangega).

## Step 3 — Setup script chalao

```bash
sudo bash deploy/setup-vps.sh
```

Ye poochega: API domain, admin domain, website domain, aur email. Baaki kaam apne aap hoga —
Docker install, firewall, swap, random passwords, build, start, SSL.
Pehli build mein **5-15 minute** lagte hain.

## Step 4 — Check karo

- `https://API_DOMAIN/api/health/live` → `ok` jaisa jawab
- `https://ADMIN_DOMAIN` → admin login page
- `https://WEBSITE_DOMAIN` → website

**Sabse pehle admin password badlo.** Default admin `admin@mfb.in` apne aap ban jaata hai.

## Step 5 — API keys daalo

```bash
nano /opt/mfb/.env.prod      # Razorpay, MSG91, EMERGENT_LLM_KEY, market data keys...
bash deploy/update.sh        # restart taaki nayi keys lag jaayein
```

- `OTP_DEMO_MODE=true` rehne do jab tak MSG91 set na ho.
- `EMERGENT_LLM_KEY` daaloge to AI features chalenge (Emergent balance se paisa katega).
- **`.env.prod` ki copy apne computer pe safe rakho.** `KYC_ENCRYPTION_KEY` kho gaya to KYC documents wapas nahi khulenge.

---

## Roz ka kaam

| Kaam | Command (`/opt/mfb` ke andar) |
|---|---|
| Naya code lagana (Claude ne GitHub pe push kiya) | `bash deploy/update.sh` |
| Sab containers ka haal | `docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod ps` |
| Backend ke logs | `docker logs --tail=100 -f mfb_backend` |
| Nginx ke logs | `docker logs --tail=100 mfb_nginx` |
| Haath se backup | `docker exec mfb_backup bash -c 'source /etc/mfb_backup.env && mongo_backup.sh'` |
| Backups ki list | `docker exec mfb_backup ls -lh /backups` |
| SSL dobara try (agar DNS baad mein set kiya) | `bash deploy/init-letsencrypt.sh` |

Error aaye to command ka **poora output** Claude ko bhej do.

## Abhi baaki (agle steps)

1. **Mobile app** — APK ko naye `API_DOMAIN` ke saath dobara build karna (`EXPO_PUBLIC_BACKEND_URL`), phir Play Store update.
2. **Push notifications** — Emergent push se hata kar Firebase (FCM) / Expo push pe.
3. **AI** — chaho to Emergent LLM key ki jagah apni OpenAI/Claude key.
4. Sab theek chalne ke baad Emergent ka deployment band karna.
