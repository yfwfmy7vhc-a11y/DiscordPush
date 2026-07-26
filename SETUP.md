# Setup runbook — get DiscordPush live

Follow these in order. Each step ends with a **✅ Checkpoint** so you know it
worked before moving on. Total time: ~20–30 minutes, most of it collecting keys.

There are **4 things to collect** (Anthropic key, eBay App ID + Cert ID, and
Discord webhook URLs) and then you paste them into GitHub as secrets. That's it.

---

## Your decided settings

- **Local folder** (already exists, don't move it): `/Users/jasperdavis/DiscordPush`
- **GitHub repo name:** `DiscordPush`
- **Visibility:** **Public** — unlimited free Actions minutes, so the schedule
  runs at full speed. Your API keys stay hidden (GitHub never exposes secrets,
  even on public repos); only the code + card list + price history are visible,
  none of which is sensitive.

---

## Step 1 — Put the code on GitHub

You need the repo on GitHub first, because everything else (secrets, Actions)
lives there. Easiest path if the command line is fighting you: use the
**[GitHub Desktop](https://desktop.github.com/)** app — sign in via browser,
**File → Add Local Repository →** choose `/Users/jasperdavis/DiscordPush`, then
**Publish repository** (untick "Keep this code private"). That does everything
below with buttons.

Command-line version:

1. On <https://github.com/new>, create a new **empty** repo:
   - **Repository name:** `DiscordPush`
   - **Visibility:** **Public**
   - Leave "Add a README", ".gitignore", and "license" **unticked** — this
     project already has them.
   - Click **Create repository**.
2. In this project folder, run:

```bash
cd /Users/jasperdavis/DiscordPush && git init && git add . && git commit -m "Initial commit: DiscordPush alerts system"
```

3. Connect it to GitHub and push (replace `<you>` with your GitHub username):

```bash
git branch -M main && git remote add origin https://github.com/<you>/DiscordPush.git && git push -u origin main
```

> When `git push` asks for a password, it wants a **Personal Access Token**, not
> your GitHub password. Create one at
> <https://github.com/settings/tokens> → **Generate new token (classic)** → tick
> **`repo`** → copy it → paste as the password (the paste shows nothing on
> screen — that's normal). GitHub Desktop avoids this entirely.

**✅ Checkpoint:** Refresh your repo page on GitHub — you should see the `src/`,
`config/`, and `.github/` folders.

---

## Step 2 — Let Actions write state back to the repo

The system saves "already alerted" state by committing small files back to the
repo, so Actions needs write access.

1. On GitHub: **Settings → Actions → General**.
2. Scroll to **Workflow permissions**.
3. Select **Read and write permissions** → **Save**.

**✅ Checkpoint:** "Read and write permissions" is now the selected option.

---

## Step 3 — Get your Anthropic API key

Used by Claude Haiku to vet card listings and write the news digests.

1. Go to <https://console.anthropic.com/> → sign in.
2. Left sidebar: **API Keys → Create Key**. Name it `DiscordPush`.
3. **Copy the key now** (it starts with `sk-ant-...`; you can't see it again).
   Paste it somewhere temporary for Step 7.

> You'll need a small amount of credit on the account — usage here is tiny
> (Haiku, short prompts, only on listings already below your target price).

**✅ Checkpoint:** You have a string starting with `sk-ant-` saved.

---

## Step 4 — Get your eBay API credentials

Used to search eBay Australia. This is a free developer app; no user login is
involved (the code uses app-only "client credentials" auth).

1. Go to <https://developer.ebay.com/> → **Sign in / Register** (a normal eBay
   account works).
2. Open **Hi \<name> → Application Keysets** (or go to *Developer Account →
   Application Keys*).
3. Under **Production**, click **Create a keyset** if you don't have one.
   (If eBay asks you to accept terms or verify contact details, do so.)
4. From the Production keyset, copy two values:
   - **App ID (Client ID)** → this is your `EBAY_APP_ID`
   - **Cert ID (Client Secret)** → this is your `EBAY_CERT_ID`

> Ignore "Dev ID", redirect URLs, and RuName — you don't need them for this.

**✅ Checkpoint:** You have two eBay strings saved: an App ID and a Cert ID.

---

## Step 5 — Create your Discord webhooks

Each alert stream posts to its own channel. Create the channels you want (you
can reuse one channel for several streams — just paste the same URL into
multiple secrets), then make a webhook for each.

For **each** channel:

1. Hover the channel → ⚙️ **Edit Channel → Integrations → Webhooks**.
2. **New Webhook → Copy Webhook URL** (starts with
   `https://discord.com/api/webhooks/...`).

You want up to five URLs, one per stream:

| Stream | Suggested channel | Goes in secret |
|---|---|---|
| Pokémon deals | `#poke-deals` | `DISCORD_WEBHOOK_CARDS` |
| Cyber digest | `#cyber-news` | `DISCORD_WEBHOOK_CYBER` |
| Tech digest | `#tech-news` | `DISCORD_WEBHOOK_TECH` |
| AI digest | `#ai-news` | `DISCORD_WEBHOOK_AI` |
| Urgent AU cyber | `#urgent` | `DISCORD_WEBHOOK_URGENT` |

> A missing webhook just disables that one stream — it won't break anything.
> Fine to start with only the ones you care about.

**✅ Checkpoint:** You have one or more `https://discord.com/api/webhooks/...`
URLs saved.

---

## Step 6 — Add everything as GitHub secrets

Now paste all the values from Steps 3–5 into GitHub.

1. On GitHub: **Settings → Secrets and variables → Actions**.
2. Click **New repository secret**, and add each of these (Name on the left,
   your value on the right). Repeat for each row:

| Secret name | Value (from…) |
|---|---|
| `ANTHROPIC_API_KEY` | Step 3 |
| `EBAY_APP_ID` | Step 4 (App ID) |
| `EBAY_CERT_ID` | Step 4 (Cert ID) |
| `DISCORD_WEBHOOK_CARDS` | Step 5 |
| `DISCORD_WEBHOOK_CYBER` | Step 5 |
| `DISCORD_WEBHOOK_TECH` | Step 5 |
| `DISCORD_WEBHOOK_AI` | Step 5 |
| `DISCORD_WEBHOOK_URGENT` | Step 5 |

> Names must match **exactly** (they're case-sensitive). Skip any Discord
> secret for a stream you don't want.

**Optional — market-value context on card alerts:** if you have a
[PriceCharting API](https://www.pricecharting.com/api-documentation) token (paid
plan), add it as `PRICECHARTING_TOKEN`. Alerts will then show current market
value and "% under market". Skip it and you still get the *"cheapest since you
started tracking"* history (built automatically from eBay — no token needed).

**✅ Checkpoint:** Your **Actions secrets** list shows all the names you added.

---

## Step 7 — Set your Pokémon targets

The example cards in `config/watchlist.json` are **placeholders** — set real
target prices or you'll get noise (or nothing).

1. Edit `config/watchlist.json`. For each card set:
   - `query` — what you'd type into eBay search
   - `target_aud` — alert only at/below this total price (item + shipping)
   - `exclude` — words that mean "not the thing I want" (proxy, custom, lot…)
2. Commit and push (or, in GitHub Desktop, write a summary and click **Commit**
   then **Push**):

```bash
git add config/watchlist.json && git commit -m "Set my card watchlist" && git push
```

**✅ Checkpoint:** Your real cards and prices are in the file on GitHub.

---

## Step 8 — Test it right now (don't wait for the schedule)

You can trigger each workflow by hand to confirm the secrets work.

1. On GitHub: **Actions** tab.
2. Pick a workflow on the left, then **Run workflow → Run workflow**:
   - **Daily news digests** — with `force = true` (the default) it posts the
     three briefs immediately instead of waiting for 7am Sydney. This is the best
     first test: it needs only the Anthropic key + Discord webhooks (no eBay).
   - **Urgent AU cyber alerts** — scans the last 90 minutes; may find nothing,
     which is normal.
   - **Pokémon price monitor** — searches your watchlist once.
3. Click the run to watch the logs. Green check = success.

**✅ Checkpoint:** At least the **news digest** run is green and you see the
cyber / tech / AI briefs land in your Discord channels.

> Not seeing messages? Open the failed step's logs:
> - `Missing required environment variable` → a secret name is wrong/missing (Step 6).
> - eBay `401`/`invalid_client` → App ID or Cert ID is wrong (Step 4).
> - Discord `no webhook configured` → that stream's webhook secret is missing (Step 5).

---

## Step 9 — You're live

Once the manual tests pass, the schedules run automatically:

- **Every 30 min** — Pokémon monitor
- **Hourly** — urgent AU cyber scan
- **Daily 7am Sydney** — the three news digests

Nothing else to keep running — no server, no laptop. GitHub Actions handles it,
and the repo remembers what it's already alerted on.

> GitHub's scheduled runs can start a few minutes late (that's normal) and may
> pause if the repo has **no activity for 60 days** — just visit the repo or
> push a commit to keep them active.
