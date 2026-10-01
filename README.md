# Job search digest

A daily email of new jobs that fit an I-O psychology master's + PMP background,
ranked for a family in Marietta, GA (remote first, then hybrid with a short
commute, relocation last) and compared against a relocation offer being weighed.
For any job in the email, one click drafts a tailored resume, cover letter and
interview prep.

## How it works

1. **Fetch** postings from the sources you've configured (all optional):
   USAJobs (federal), Adzuna (aggregates Indeed, Glassdoor and company sites),
   Remotive (remote jobs, no key), and any Greenhouse/Lever company boards
   listed in `config.yaml`.
2. **Filter and pre-score** with simple rules (`config.yaml`): title relevance,
   remote/commute tier, family-fit signals such as flexible hours or heavy
   travel.
3. **Claude reviews** the top 40 against the resume: fit score, why, concerns,
   how it compares to the OPM offer, and what to lead with.
4. **Email** the best 15 new ones. Jobs already sent are remembered in the
   GitHub Actions cache and won't be repeated.

## Setup (about 20 minutes, one time)

Add each item under **Settings → Secrets and variables → Actions → New
repository secret**. Everything personal lives in secrets because this repo is
public.

| Secret | What it is | Where to get it | Needed? |
|---|---|---|---|
| `RESUME_TEXT` | Resume as plain text or Markdown | Paste it in | Yes |
| `ANTHROPIC_API_KEY` | Claude API key (scoring + tailoring) | console.anthropic.com → API keys | Yes, for AI scoring |
| `EMAIL_TO` | Comma-separated recipients | — | Yes |
| `SMTP_USER` | Gmail address that sends the mail | — | Yes |
| `SMTP_PASSWORD` | Gmail **app password** (not the normal password) | myaccount.google.com/apppasswords (needs 2-step verification) | Yes |
| `USAJOBS_API_KEY` | USAJobs key, free, emailed within minutes | developer.usajobs.gov/apirequest | Recommended |
| `USAJOBS_EMAIL` | The email used to request that key | — | With the key |
| `CANDIDATE_CONTEXT` | Private notes for Claude, e.g. household situation | Write it yourself | Optional |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna API credentials, free tier | developer.adzuna.com/signup | Recommended |

Then open **Actions → Daily job digest → Run workflow** to send the first
email right away. Scheduled runs only start once the workflows are on the
default branch (`main`).

To tailor an application: **Actions → Tailor application → Run workflow**, then
paste the job ID from the email (or a posting URL). The kit arrives by email.
The GitHub mobile app can do this too.

## Tuning

Everything is in `config.yaml`: search keywords, commute tiers, scoring
weights, family signals, how many jobs go to Claude, and how many get emailed.
Fill in `benchmark.salary` with the OPM offer so comparisons are concrete.

## Cost

About 5 Claude calls a day (40 jobs in batches of 8, with the resume prompt
cached across batches), so roughly a dollar a day or less. Each application kit
is one more call.

## Local use

```bash
pip install -r requirements.txt
cp your-resume.md private/resume.md          # private/ is gitignored
python -m jobsearch digest --dry-run          # prints instead of emailing
python -m jobsearch digest --fixture tests/fixtures/sample_jobs.json --no-ai --dry-run
python -m pytest -q
```
