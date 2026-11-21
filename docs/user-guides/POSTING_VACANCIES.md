# Posting vacancies on MHRS

How to advertise a job on the MUDHOTECH HR RECRUITING SYSTEM, from creating the employer account to
a live vacancy that candidates can find and apply to.

**Website:** https://hr.agribizframework.com · **Job board:** https://hr.agribizframework.com/jobs

---

## At a glance

| Step | Who | Done |
|---|---|---|
| 1. Create the employer organisation | The employer's administrator | Once |
| 2. Verify the organisation | MudhoTech platform admin | Once |
| 3. Set up profile, departments, locations, team | Organisation admin | Once |
| 4. Create the vacancy (5-step wizard) | Recruiter or HR manager | Each vacancy |
| 5. Approve and publish | HR manager or organisation admin | Each vacancy |
| 6. Share it | Anyone in the team | Each vacancy |

Every vacancy belongs to an **employer organisation**. The MudhoTech platform admin account manages
the platform but does not post jobs itself; jobs are posted by the employer's own team.

---

## Step 1 — Create the employer organisation (once)

1. Open **https://hr.agribizframework.com/employers** (the *For employers* link at the top of the site).
2. Sign in, or create an account with the email address of the person who will manage this employer,
   and confirm the email address from the link that arrives.
3. Fill in the organisation form: legal name, registration number, city and website.
4. Click **Create organisation**. The person who creates it becomes the organisation's **admin**.

## Step 2 — Verify the organisation (MudhoTech, once)

1. Sign in as the platform admin (mudhotechsolutions@gmail.com).
2. Open **Admin → Organisations**, find the new organisation and click **Verify**, then confirm.

Until it is verified the organisation can be set up, but it cannot publish vacancies.

## Step 3 — Set up the organisation (once)

Signed in as the organisation admin:

- **Settings → Organisation:** logo, description and the public company page candidates see.
- **Settings → Departments & locations:** add the departments and work locations you will use in
  vacancies.
- **Settings → Team:** invite colleagues by email and give each a role:

| Role | What they do with vacancies |
|---|---|
| Recruiter | Creates vacancies and submits them for approval; reviews applicants |
| HR manager | Approves, publishes, pauses and closes vacancies; everything a recruiter does |
| Organisation admin | Everything, plus team and settings |
| Hiring manager | Sees the shortlisted applicants for their vacancies |

A small organisation can have one person do everything. Admins and HR managers must set up
two-factor authentication within 7 days of getting the role.

- **Settings → Policies** (optional): blind review (on by default), the delay before outcome
  messages go out (15 minutes by default), and whether a second person must approve.

---

## Step 4 — Create the vacancy

Go to **Jobs → New vacancy**. The wizard has five steps and saves as you go; use **Save and continue**
to move on, and come back any time.

### 4.1 Details
Job title, department, location(s), employment type (full-time, part-time, contract, temporary,
internship, industrial attachment), workplace (on-site, hybrid, remote), salary (optional) and the
**closing date and time**. The closing date is shown to candidates in the vacancy's time zone
(Africa/Harare by default) and applications stop automatically at that moment.

### 4.2 Requirements
The job description: what the person will do and what they need. Use the editor's headings and
lists; formatting is cleaned for safety, so pasted content from Word is fine.

### 4.3 Questions
Questions every applicant answers, for example:
- **Knock-out questions** (e.g. "Do you have a valid driver's licence?"), and
- **Screening questions** (e.g. "Describe a project where you used Python").

The system refuses questions about **age, gender, religion, tribe, marital status, pregnancy, health,
disability, HIV status or political opinion**. Answers count as evidence in the screening.

### 4.4 Rubric (the criteria)
This is the most important step: the criteria every application is judged against, by the AI
assistant and by your team.

- Add the **skills, years of experience, qualifications, certifications and languages** the job
  needs, each with a **weight** (how much it matters).
- Mark only the true must-haves as **essential**, and write why each is essential.
- The system can **suggest criteria** from the description; suggestions are labelled and optional.

**Tips for a good rubric**

- Be specific: "PostgreSQL" rather than "databases"; "3 years' accounting experience" rather than
  "experienced".
- Make a language, qualification or location essential only when the job truly needs it: such
  requirements can exclude good people by origin or background.
- Foreign qualifications that are verified count the same as local ones.
- Missing information never counts as a fail: an unmatched requirement is marked *unknown* and goes to
  a person, who can ask the candidate.

### 4.5 Preview
Check the vacancy as candidates will see it, and the **publish readiness** list (anything still
missing). Then click **Submit for approval**.

---

## Step 5 — Approve and publish

An HR manager or the organisation admin opens the vacancy (**Jobs**, status *Pending approval*):

1. Check the description, the criteria and their weights, the essentials and their reasons, and the
   questions.
2. Click **Approve**, or **Request changes** with a comment for the recruiter.
3. Click **Publish now**, or **Schedule** to publish at a chosen date and time.

The vacancy is live as soon as it is published. If your organisation requires a second person to
approve, the approver must be someone other than the person who created it.

**Once applications have arrived, a vacancy's criteria are fixed.** To change them, use
**Create new version**; applications keep the version they were judged against, and HR can re-run the
screening against the new version.

---

## Step 6 — Where the vacancy appears and how to share it

| Where | Address |
|---|---|
| Public job board (search and filters) | https://hr.agribizframework.com/jobs |
| The vacancy's own page (share this link) | copy it from the vacancy page or the job board |
| The employer's company page | linked from each vacancy |
| RSS feed of all vacancies | https://hr.agribizframework.com/jobs/feed.rss |
| JSON feed of all vacancies | https://hr.agribizframework.com/jobs/feed.json |
| One employer's vacancies (XML / JSON) | `https://hr.agribizframework.com/api/v1/feeds/<organisation-slug>/jobs.xml` (or `jobs.json`) |
| Search engines | listed automatically in https://hr.agribizframework.com/sitemap.xml |

**Getting applicants:** share the vacancy link on WhatsApp, Facebook, LinkedIn and your own website,
in emails and newsletters, or give a job board the feed address so it imports your vacancies
automatically. Wherever candidates find the vacancy, they apply on MHRS, so every application lands
in one place.

---

## Managing a live vacancy

From the vacancy page:

| Action | What it does |
|---|---|
| **Pause** / **Resume** | Temporarily stops new applications without closing |
| **Extend deadline** | Moves the closing date later (candidates see the new date) |
| **Close vacancy** | Stops applications now; unfinished drafts are closed and their candidates told |
| **Duplicate** | Starts a new vacancy from this one (for a similar role) |
| **Create new version** | Changes the criteria once applications exist (see Step 5) |
| **Archive** | Removes it from your active list after the process is finished |

## What happens when candidates apply

1. The candidate creates an account, uploads a CV, checks what was read from it and answers your
   questions.
2. The CV is virus-checked and read; the application is compared with your rubric, usually within
   minutes.
3. Under **Jobs → (vacancy) → Applicants** you see every application with its band (*Recommended for
   review*, *Review needed*, *Eligibility review*, *Lower match*) and the evidence for each criterion.
   The AI only suggests; your team decides.
4. You review, ask clarification questions, build a shortlist and approve it. Candidates are told
   after the short undo delay.

The full process (shortlisting, interviews, offers and hiring) is described in the MHRS System
Guide (`docs/MHRS_System_Guide.pdf`), chapters 6 to 10.

---

## Checklist before publishing

- [ ] The organisation is verified (Admin → Organisations).
- [ ] The job title and closing date are correct.
- [ ] The description says what the job involves and where it is based.
- [ ] Every criterion has a sensible weight; essentials are truly essential and justified.
- [ ] Questions are relevant and ask nothing about protected characteristics.
- [ ] The preview reads well on a phone (most candidates apply from one).
- [ ] You have done one test application with a second email address before the first real vacancy.

## Common questions

**The Publish button is missing.** The vacancy has not been approved yet, your role cannot publish
(ask an HR manager or the organisation admin), or the organisation is not verified yet.

**Can I edit a vacancy after publishing?** Use **Extend deadline** to change the closing date. For
any other change (description, criteria, questions), use **Create new version**: once a version has
been used by applicants it is fixed, so every application keeps the exact version it was judged
against.

**Candidates say they cannot apply.** Check the vacancy is published, not paused, and before its
closing date. Candidates must confirm their email address before submitting.

**Where do I see the applications?** Jobs → (the vacancy) → Applicants.

**Need help?** Contact MudhoTech support at the address in the system's emails.
