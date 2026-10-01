# Setup checklist (free version)

Everything here costs $0. The free version ranks jobs with the rules in
`config.yaml` instead of Claude. Claude scoring and the "Tailor application"
button need a paid Anthropic API key, so leave `ANTHROPIC_API_KEY` unset.

## 1. Gmail account that sends the email (about 5 min)
- [ ] Choose the sending Gmail account (yours is fine).
- [ ] Turn on 2-Step Verification: myaccount.google.com/security
- [ ] Create an app password at myaccount.google.com/apppasswords and name it
      "job digest". Copy the 16-character password; Google shows it only once.

## 2. Free job-site keys (about 10 min)
- [ ] **USAJobs:** request a key at developer.usajobs.gov/apirequest. It
      arrives by email. Note which email you used.
- [ ] **Adzuna:** sign up at developer.adzuna.com/signup. The dashboard shows
      an **App ID** and an **App Key**.
- Remotive (remote jobs) needs no key.

## 3. Make the repo private (recommended, 1 min)
- [ ] GitHub → this repo → **Settings → General → Danger Zone → Change
      visibility → Private**. Free accounts get 2,000 Actions minutes a month
      for private repos, and the digest uses about 3 minutes a day.

## 4. Add secrets (about 5 min)
GitHub → this repo → **Settings → Secrets and variables → Actions → New
repository secret**. Add each one:

- [ ] `SMTP_USER`: the sending Gmail address
- [ ] `SMTP_PASSWORD`: the 16-character app password from step 1
- [ ] `EMAIL_TO`: `fmdenver@gmail.com,sandrapatton.sp@gmail.com`
- [ ] `USAJOBS_API_KEY`: the key from the USAJobs email
- [ ] `USAJOBS_EMAIL`: the email you requested that key with
- [ ] `ADZUNA_APP_ID`
- [ ] `ADZUNA_APP_KEY`
- [ ] Do **not** add `ANTHROPIC_API_KEY`. Leaving it out keeps the digest free.

## 5. Turn it on (about 3 min)
- [ ] Merge the `claude/intelligent-knuth-rfd538` branch into `main`. On the
      repo page, click **Compare & pull request**, then **Merge**. Scheduled
      runs only work from `main`.
- [ ] Open the **Actions** tab and, if asked, click **Enable workflows**.
- [ ] Click **Daily job digest → Run workflow** to send the first email now.
- [ ] Check both inboxes, including spam. If it landed in spam, mark it
      **Not spam** so later emails arrive normally.

After that it runs every morning at about 6:45am Eastern.

## 6. Optional
- [ ] Put the OPM salary in `benchmark.salary` in `config.yaml`.
- [ ] Add company career pages: put Greenhouse/Lever board names in
      `config.yaml`. The board name is the part after `boards.greenhouse.io/`
      or `jobs.lever.co/` in a careers link.
- [ ] Free tailoring: paste a posting plus her resume into claude.ai (free plan)
      and ask for a tailored resume summary and cover letter.

## If emails stop
- GitHub pauses scheduled workflows after 60 days with no repo activity. It
  emails the repo owner; click **Enable workflow** on the Actions tab.
- A failed run shows a red ✗ on the Actions tab. Open it to see which source or
  secret had the problem.
