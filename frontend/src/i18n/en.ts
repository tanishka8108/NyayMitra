/* =========================================================
   ENGLISH DICTIONARY

   Flat dotted keys → English UI strings. `t("key")` in any
   component reads the active language's table; English is
   also the runtime fallback for keys a language is missing,
   and i18n.test.ts keeps the two tables key-for-key in
   parity so a missing Marathi value fails the build's tests
   rather than shipping silently.

   Scope: interface text only. User-generated content (case
   descriptions, legal documents, names, addresses) is never
   translated by this layer.
   ========================================================= */

export const en: Record<string, string> = {
  /* ---- App chrome (session bar / signed-out corner) ---- */
  "app.signOut": "Sign out",
  "app.role.user": "USER",
  "app.role.lawyer": "LAWYER",
  "app.role.admin": "ADMIN",
  "app.role.staff": "STAFF",
  "app.theme.toggleGroup": "Theme",
  "app.theme.toDark": "Switch to dark theme",
  "app.theme.toLight": "Switch to light theme",
  "app.lang.group": "Language",

  /* ---- Role dashboard shell ---- */
  "roleDashboard.badge.open": "Open",
  "roleDashboard.badge.soon": "Coming soon",
  "roleDashboard.cta.open": "Open section →",
  "roleDashboard.cta.underDevelopment": "Under development",

  /* ---- Login page ---- */
  "login.brand.tagline": "AI Court Assistant",
  "login.eyebrow": "ONE PLATFORM • FOUR ROLES",
  "login.hero.title1": "Welcome to",
  "login.hero.titleAccent": "NyayMitra.",
  "login.hero.copy":
    "A single login system identifies whether you " +
    "are a user, lawyer, administrator or staff " +
    "member — and opens the dashboard built for " +
    "your role.",
  "login.doors.label": "SIGN IN",
  "login.doors.heading": "Login as what role?",
  "login.doors.sub": "Choose the door that matches your role.",
  "login.door.user.title": "I am a Citizen",
  "login.door.user.role": "User",
  "login.door.user.desc":
    "Search cases, track timelines, read court orders, " +
    "find lawyers and translate legal documents.",
  "login.door.lawyer.title": "I am a Lawyer",
  "login.door.lawyer.role": "Lawyer",
  "login.door.lawyer.desc":
    "Manage your professional profile, cases, hearings " +
    "and client communication.",
  "login.door.admin.title": "I am an Administrator",
  "login.door.admin.role": "Admin",
  "login.door.admin.desc":
    "Manage users, lawyers, staff and platform access. " +
    "Staff members sign in through this door.",
  "login.door.cta": "Continue →",
  "login.registerLink": "New citizen? Create an account →",
  "login.demo.show": "Show demo credentials",
  "login.demo.hide": "Hide demo credentials",
  "login.demo.label": "DEMO ACCOUNTS — MOCK AUTH",
  "login.demo.use": "Use",
  "login.eyebrow.staff": "STAFF SIGN-IN",
  "login.eyebrow.door": "{role} SIGN-IN",
  "login.staff.title1": "Staff access",
  "login.staff.titleAccent": "via Admin.",
  "login.form.title1": "Sign in to",
  "login.form.titleAccent": "your dashboard.",
  "login.staff.desc":
    "Staff accounts are issued and managed by the " +
    "administrator. Sign in with the credentials you " +
    "were given.",
  "login.back": "← Change role",
  "login.label.staff": "STAFF",
  "login.heading.staff": "Staff sign-in",
  "login.heading.as": "Sign in as {role}",
  "login.staffLink": "Are you staff? Sign in here →",
  "login.adminBack": "← Administrator sign-in",
  "login.field.staffEmail": "Staff email",
  "login.field.identifier": "Email or User ID",
  "login.field.placeholder.staff": "you@nyaymitra.in",
  "login.field.placeholder.mock": "you@example.com or USER_0001",
  "login.field.placeholder": "you@example.com",
  "login.field.password": "Password",
  "login.field.passwordPlaceholder": "Enter your password",
  "login.password.show": "Show password",
  "login.password.hide": "Hide password",
  "login.password.showShort": "Show",
  "login.password.hideShort": "Hide",
  "login.error.staffEmail": "Enter your staff email.",
  "login.error.identifier": "Enter your email or User ID.",
  "login.error.password": "Enter your password.",
  "login.error.generic": "Unable to sign in. Please try again.",
  "login.submit.loading": "Verifying role...",
  "login.submit.staff": "Sign in as Staff",
  "login.submit.as": "Sign in as {role}",
  "login.note.mock": "Authentication is running in mock mode. ",
  "login.note.tail":
    "Your role is detected on sign-in and the matching " +
    "dashboard opens automatically.",

  /* ---- Register page ---- */
  "register.eyebrow": "CREATE ACCOUNT",
  "register.hero.title1": "Join",
  "register.hero.titleAccent": "NyayMitra.",
  "register.hero.copy":
    "One citizen account for case search, timelines, court " +
    "orders, translation and conversations with verified " +
    "lawyers — or register as a lawyer to take those " +
    "conversations.",
  "register.backToSignIn": "← Back to sign in",
  "register.choice.label": "ACCOUNT TYPE",
  "register.choice.heading": "How will you use NyayMitra?",
  "register.choice.sub": "Pick the account you want to create.",
  "register.door.citizen.role": "Citizen",
  "register.door.citizen.title": "Create User Account",
  "register.door.citizen.desc":
    "Search and save cases, read court orders, " +
    "translate, and chat with verified lawyers.",
  "register.door.advocate.role": "Advocate",
  "register.door.advocate.title": "Create Lawyer Account",
  "register.door.advocate.desc":
    "Register with your licence and practice areas. " +
    "Your registration is verified before you can " +
    "receive chats from users.",
  "register.signInLink": "Already have an account? Sign in →",
  "register.submitted.label": "LAWYER",
  "register.submitted.heading": "Registration submitted",
  "register.submitted.status":
    "Your lawyer registration is pending " +
    "admin verification.",
  "register.submitted.copy":
    "An administrator will review your licence " +
    "document and practice details. Until your " +
    "account is approved, verified-lawyer features — " +
    "such as receiving chats from users — stay " +
    "locked. You can sign in with your email and " +
    "password at any time to check your status.",
  "register.submitted.go": "Go to sign in",
  "register.chooseType": "← Choose account type",
  "register.citizen.label": "CITIZEN",
  "register.citizen.heading": "Create your account",
  "register.citizen.sub":
    "Your role is set for you — sign-in detects it " +
    "automatically.",
  "register.field.fullName": "Full name",
  "register.field.namePlaceholder.user": "e.g. Asha Verma",
  "register.field.email": "Email",
  "register.field.emailPlaceholder": "you@example.com",
  "register.field.confirm": "Confirm password",
  "register.field.confirmPlaceholder": "Repeat the password",
  "register.field.passwordPlaceholder": "At least 8 characters",
  "register.submit.creating": "Creating your account...",
  "register.submit.create": "Create account",
  "register.lawyer.label": "LAWYER",
  "register.lawyer.heading": "Register as a lawyer",
  "register.lawyer.sub":
    "Your registration starts as pending — an admin " +
    "verifies your licence before you can receive " +
    "chats from users.",
  "register.field.namePlaceholder.lawyer": "e.g. Adv. Priya Sharma",
  "register.field.lawEmailPlaceholder": "advocate@example.com",
  "register.field.license": "Licence / Bar Council registration ID",
  "register.field.licensePlaceholder": "e.g. MAH/1234/2020",
  "register.field.practiceAreas": "Practice areas",
  "register.field.practicePlaceholder":
    "e.g. Criminal Law, Family Law",
  "register.field.practiceHint": "Separate each area with a comma.",
  "register.optional.heading": "Other profile information",
  "register.optional.badge": "optional",
  "register.field.barCouncil": "Bar Council",
  "register.field.barCouncilPlaceholder":
    "e.g. Bar Council of Maharashtra",
  "register.field.years": "Years of experience",
  "register.field.yearsPlaceholder": "e.g. 7",
  "register.field.phone": "Phone",
  "register.field.bio": "Short bio",
  "register.field.bioPlaceholder":
    "A line about your practice (optional)",
  "register.field.document": "Licence / registration document",
  "register.field.documentHint":
    "PDF, JPG or PNG — up to 10 MB. An admin checks " +
    "this document during verification.",
  "register.field.photo": "Profile photo (optional)",
  "register.field.photoHint":
    "JPG, PNG or WebP — up to 2 MB. Saved on this device " +
    "and shown on your profile until server-side photo " +
    "storage is enabled.",
  "register.photo.alt": "Profile photo preview",
  "register.note.retry":
    "Your account was created — submitting again " +
    "only retries the document upload.",
  "register.submit.submitting": "Submitting registration...",
  "register.submit.retry": "Retry document upload",
  "register.submit.lawyer": "Submit lawyer registration",
  "register.err.name": "Enter your full name.",
  "register.err.email": "Enter a valid email address.",
  "register.err.passwordLength":
    "Password must be at least {n} characters.",
  "register.err.passwordMatch": "Passwords do not match.",
  "register.err.license":
    "Enter your licence or registration number.",
  "register.err.practiceMin": "List at least one practice area.",
  "register.err.practiceMax": "List at most {n} practice areas.",
  "register.err.practiceLength":
    "Each practice area must be {n} characters or fewer.",
  "register.err.barCouncil":
    "Bar Council must be {n} characters or fewer.",
  "register.err.years":
    "Years of experience must be between 0 and {n}.",
  "register.err.phone": "Enter a valid phone number.",
  "register.err.bio": "Bio must be {n} characters or fewer.",
  "register.err.documentMissing":
    "Attach your licence or registration document " +
    "(PDF, JPG or PNG).",
  "register.err.documentType": "Upload a PDF, JPG or PNG file.",
  "register.err.documentSize":
    "File too large. Maximum allowed size is 10 MB.",
  "register.err.photoType": "Upload a JPG, PNG or WebP image.",
  "register.err.photoSize":
    "Photo too large. Maximum allowed size is 2 MB.",
  "register.err.photoRead":
    "Could not read that image. Try another file.",
  "register.err.genericUser":
    "Unable to create the account. Please try again.",
  "register.err.genericLawyer":
    "Unable to submit the registration. Please try again.",

  /* ---- Shared navigation ---- */
  "nav.main": "Main navigation",
  "nav.brandTagline": "LEGAL ASSISTANCE",
  "nav.home": "Home",
  "nav.myCases": "My Cases",
  "nav.findLawyer": "Find a Lawyer",
  "nav.chat": "Chat",

  /* ---- Homepage ---- */
  "home.eyebrow": "YOUR LEGAL COMPANION",
  "home.title1": "Your legal journey,",
  "home.titleAccent": "simplified.",
  "home.copy":
    "Understand your cases, find trusted legal professionals, " +
    "translate documents, and get clear guidance — all in one place.",
  "home.ctaExplore": "Explore My Cases",
  "home.servicesLabel": "LEGAL SERVICES",
  "home.servicesHeading": "Everything your legal journey needs.",
  "home.tile.cases.label": "CASE SERVICES",
  "home.tile.cases.desc":
    "Search and track your cases, hearings and case status.",
  "home.tile.lawyer.label": "LEGAL PROFESSIONALS",
  "home.tile.lawyer.desc":
    "Find lawyers based on practice area, experience and location.",
  "home.tile.chat.label": "MESSAGES",
  "home.tile.chat.desc":
    "Continue a conversation with a lawyer you contacted, or with " +
    "the staff handling your account.",
  "home.tile.orders.label": "COURT DOCUMENTS",
  "home.tile.orders.title": "Court Orders",
  "home.tile.orders.desc":
    "Access court orders and understand important legal documents.",
  "home.tile.translate.label": "LANGUAGE ASSISTANCE",
  "home.tile.translate.title": "Translation",
  "home.tile.translate.desc":
    "Translate legal content into simpler and familiar languages.",
  "home.tile.delay.label": "CASE INSIGHTS",
  "home.tile.delay.title": "Delay Analysis",
  "home.tile.delay.desc":
    "Understand possible reasons for case delays and get useful " +
    "insights.",
  "home.tile.voice.label": "TELL US WHAT HAPPENED",
  "home.tile.voice.title": "Voice Assistance",
  "home.tile.voice.desc":
    "Describe an incident by voice or text, or ask what happened " +
    "in your case and what to do next.",
  "home.tile.timeline.label": "CASE HISTORY",
  "home.tile.timeline.title": "Case Timeline",
  "home.tile.timeline.desc":
    "Track important hearings, events and stages in your case journey.",
  "home.helpsLabel": "HOW NYAYMITRA HELPS",
  "home.helpsHeading": "Clear guidance. Confident decisions.",
  "home.info.understand.title": "Understand",
  "home.info.understand.desc":
    "Get simple explanations of legal terms, processes, and your rights.",
  "home.info.help.title": "Find Trusted Help",
  "home.info.help.desc":
    "Connect with verified lawyers and get legal support that's " +
    "right for you.",
  "home.info.translate.title": "Translate",
  "home.info.translate.desc":
    "Translate legal documents into simple language with confidence.",
  "home.trust.secure.title": "Secure & Private",
  "home.trust.secure.desc": "Your data is encrypted and always protected.",
  "home.trust.verified.title": "Verified Professionals",
  "home.trust.verified.desc":
    "Lawyers you can trust, for the results you deserve.",
  "home.trust.support.title": "Here to Support",
  "home.trust.support.desc":
    "We're here to help you at every step.",
  "home.ctaLabel": "NEED LEGAL ASSISTANCE?",
  "home.ctaHeading": "Start with your case.",
  "home.ctaCopy":
    "Search your case information and explore the available " +
    "NyayMitra services.",
  "trans.lang.mr": "Marathi",
  "trans.lang.hi": "Hindi",
  "trans.lang.en": "English",
  "trans.err.translate":
    "Unable to translate. Please make sure the NyayMitra translation " +
    "service is running.",
  "trans.err.simplify":
    "Unable to simplify and translate. Please make sure the NyayMitra " +
    "translation service is running.",
  "trans.note.copy":
    "Translation is intended to improve understanding of legal " +
    "information. The translated text should not be treated as a " +
    "replacement for the original legal document.",
  "trans.note.important": "Important:",
  "trans.example.updates.desc": "Understand important case information",
  "trans.example.updates.title": "Case Updates",
  "trans.example.notices.desc": "Translate formal legal communication",
  "trans.example.notices.title": "Legal Notices",
  "trans.example.orders.desc": "Understand directions issued by the court",
  "trans.example.orders.title": "Court Orders",
  "trans.quick.heading": "What can you translate?",
  "trans.quick.label": "QUICK START",
  "trans.demo.line4.note": "date fixed",
  "trans.demo.line4.label": "Listed for hearing",
  "trans.demo.line3.note": "application finished",
  "trans.demo.line3.label": "Disposed of",
  "trans.demo.line2.note": "petitioner told to file",
  "trans.demo.line2.label": "Reply directed",
  "trans.demo.line1.note": "hearing put off",
  "trans.demo.line1.label": "Adjourned",
  "trans.demo.note":
    "These are sample sentences invented to test the simplification " +
    "pipeline. They are not excerpts from any real case, and no real " +
    "party, date or order is represented by them.",
  "trans.demo.heading": "Four lines written for development",
  "trans.demo.label": "DEMO EXAMPLES · NOT REAL ORDERS",
  "trans.action.again": "Start Again",
  "trans.action.translate": "Translate Text",
  "trans.busy.pleaseWait":
    "Please wait while NyayMitra processes the legal text.",
  "trans.busy.working": "Working...",
  "trans.busy.translating": "Translating...",
  "trans.busy.simplifying": "Simplifying and translating...",
  "trans.output.footer": "NyayMitra language assistance",
  "trans.output.emptyDirectHint":
    "Enter legal text on the left and click “Translate Text”.",
  "trans.output.emptyDirect": "Your translation will appear here",
  "trans.output.emptySimplifyHint":
    "Enter legal text on the left and click “Simplify & Translate”.",
  "trans.output.emptySimplify": "Your three layers will appear here",
  "trans.output.copied": "Copied",
  "trans.output.copy": "Copy",
  "trans.output.labelDirect": "TRANSLATED TEXT",
  "trans.output.labelSimplify": "ORIGINAL · SIMPLE · TRANSLATED",
  "trans.editor.footer": "Legal document translation",
  "trans.editor.chars": "{n} characters",
  "trans.editor.placeholder":
    "Paste your court order, notice, judgment or legal text here...",
  "trans.editor.clear": "Clear",
  "trans.editor.sourceLabel": "YOUR LEGAL TEXT",
  "trans.swap.disabled":
    "English can only be the source language — this service translates " +
    "into Hindi or Marathi.",
  "trans.swap.title": "Swap languages",
  "trans.targetLabel": "TRANSLATE TO",
  "trans.sourceLabel": "SOURCE LANGUAGE",
  "trans.step3": "STEP 3 IN",
  "trans.mode.simplify": "Legal Simplification",
  "trans.mode.direct": "Direct Translation",
  "trans.pill.legal": "Legal Text",
  "trans.pill.marathi": "Marathi",
  "trans.pill.hindi": "Hindi",
  "trans.hero.copy":
    "Translate difficult legal language into Hindi or Marathi for " +
    "clearer understanding.",
  "trans.hero.titleAccent": "in your language",
  "trans.hero.title1": "Understand the law",
  "trans.hero.badge": "NYAYMITRA LANGUAGE ASSISTANCE",
  "trans.backToDashboard": "← Back to Dashboard",
  "orders.err.simplify": "The text could not be simplified and translated.",
  "orders.err.lang": "Unsupported language selected.",
  "orders.err.file": "The order was not filed.",
  "orders.err.explain": "The order could not be explained.",
  "orders.close": "Close explanation",
  "orders.dates.label": "Dates in this order",
  "orders.terms.label": "Words used, in plain terms",
  "orders.section.absent": "Not available in the document.",
  "orders.section.missing": "Not in this document",
  "orders.simplify.sectionLabel": "Simplify & Translate",
  "orders.simplify.again": "Run again",
  "orders.simplify.working": "Working…",
  "orders.simplify.intro":
    "Original wording → simple English → that plain English in the " +
    "language picked below.",
  "orders.simplify.title": "Understand this order",
  "orders.simplify.running": "Working out the three layers…",
  "orders.simplify.step3": "Step 3 in",
  "orders.layers.noRewording":
    "No plainer wording was found for this passage, so it is shown " +
    "exactly as written.",
  "orders.layer.translated": "3 · {target}, from the simple English",
  "orders.layer.simple": "2 · Simple English",
  "orders.layer.legal": "1 · Original legal text",
  "orders.badge.explainedIn": "Explained in {label}",
  "orders.badge.scan": "Security scan: {status}",
  "orders.badge.ocr": "Text read by OCR",
  "orders.badge.pages": "pages",
  "orders.badge.page": "page",
  "orders.paste.submit": "Explain in simple words",
  "orders.paste.placeholder": "Paste the text of the court order…",
  "orders.paste.note":
    "The file was not read, so there is nothing to summarise from it " +
    "yet. Paste the text of the order below and it will be shown in " +
    "three steps: as written, in simple English, and in the language " +
    "picked above.",
  "orders.card.remove": "Remove from this case",
  "orders.card.explain": "Explain this order",
  "orders.card.reading": "Reading the order…",
  "orders.card.uploaded": "Uploaded",
  "orders.card.size": "Size",
  "orders.card.recordOnly": "Record only",
  "orders.card.available": "Available",
  "orders.case.empty": "No court orders uploaded for this case yet.",
  "orders.case.countMany": "orders",
  "orders.case.countOne": "order",
  "orders.case.nextHearing": "Next hearing {date}",
  "orders.empty.copy":
    "Court orders are issued against a case. Search a CNR in My Cases, " +
    "save the case, and its orders will be listed here.",
  "orders.empty.heading": "No saved cases on this account",
  "orders.list.unit": "Orders",
  "orders.list.heading": "Court orders by case",
  "orders.list.label": "YOUR DOCUMENTS",
  "orders.upload.submit": "Upload and explain",
  "orders.upload.reading": "Reading…",
  "orders.upload.chooseFile": "Choose file",
  "orders.upload.langAria": "Language for the explanation",
  "orders.upload.noCases": "No saved cases",
  "orders.upload.caseAria": "Case this order belongs to",
  "orders.upload.desc":
    "Choose the case this order belongs to, then the file — a PDF or an " +
    "image. It is saved to that case and explained in three steps: the " +
    "order exactly as written, the same words in simple English, and " +
    "that plain English in Hindi or Marathi — whichever language is " +
    "picked below.",
  "orders.upload.heading": "Explain a Court Order",
  "orders.hero.copy":
    "Upload an order against the case it belongs to, and NyayMitra will " +
    "read it back to you in plain language — grouped by the matter, the " +
    "way your advocate would file them.",
  "orders.hero.titleAccent": "your court orders",
  "orders.hero.title1": "Find and understand",
  "orders.hero.badge": "NYAYMITRA COURT SERVICES",
  "orders.backToDashboard": "← Back to Dashboard",
  "explainer.urgency": "Urgency for this stage: {level}",
  "explainer.whatNext": "What to do next",
  "explainer.whereStage": "Where your case stands: {stage}",
  "explainer.error": "The next step could not be worked out just now.",
  "explainer.nextStep": "Explain Next Step",
  "explainer.shown": "Next step shown",
  "explainer.working": "Working it out…",
  "explainer.stop": "Stop ▪",
  "explainer.listen": "Listen",
  "explainer.copied": "Copied",
  "explainer.copy": "Copy",
  "explainer.glossary": "Words from the legal glossary in this text",
  "explainer.englishDone":
    "English was asked for, so step two is the finished answer.",
  "explainer.noPlainer":
    "No plainer wording was found for this passage, so it is " +
    "shown exactly as written.",
  "explainer.layer3": "3 · {lang}, from the simple English",
  "explainer.layer2": "2 · Simple English",
  "explainer.layer1": "1 · Original legal text",
  "explainer.step3": "Step 3 in {lang}",
  "explainer.title": "Legal Order Explainer",
  "explainer.lang.english": "English",
  "explainer.lang.hindi": "हिंदी (Hindi)",
  "explainer.lang.marathi": "मराठी (Marathi)",
  "ongoing.working": "Working…",
  "ongoing.versus": "v.",
  "ongoing.nextHearing": "Next hearing {date}",
  "ongoing.held": "Held {date}",
  "ongoing.today": "Today, {date}",
  "ongoing.dateNotSet": "Date not set",
  "docs.retry": "Try again",
  "docs.error": "Court documents could not be loaded just now.",
  "docs.forbidden": "You do not have access to the documents for this case.",
  "docs.signedOut":
    "Sign in again to view this case’s court documents.",
  "docs.unavailableNote":
    "The document service does not recognise this case — nothing is " +
    "being withheld; there is simply nothing to show here right now.",
  "docs.unavailable":
    "Court documents are not available for this case yet.",
  "docs.empty": "No court documents have been published for this case yet.",
  "docs.noDownloadTitle": "No downloadable file was supplied by the backend",
  "docs.downloadUnavailable": "Download unavailable",
  "docs.download": "Download",
  "docs.noViewTitle": "No viewable file was supplied by the backend",
  "docs.viewUnavailable": "View unavailable",
  "docs.view": "View",
  "docs.loading": "Fetching court documents…",
  "docs.demoBody":
    "Sample rows are shown because the document API is not connected " +
    "in this environment — they are not real court " +
    "documents and link nowhere.",
  "docs.demoStrong": "Development demo data.",
  "docs.demoChip": "DEMO",
  "docs.demoChipTitle": "Development-only sample records",
  "docs.copy":
    "Orders, notices and judgments published for this " +
    "matter by the case service — listed only when the " +
    "backend actually supplies them.",
  "docs.title": "Court documents",
  "detail.cat.other": "Other",
  "detail.cat.correspondence": "Correspondence",
  "detail.cat.courtOrder": "Court order",
  "detail.cat.identity": "Identity",
  "detail.cat.evidence": "Evidence",
  "detail.cat.filing": "Filing",
  "detail.doc.open": "Open",
  "detail.doc.remove": "Remove",
  "detail.doc.recordOnly": "Record only",
  "detail.doc.preview": "Preview",
  "detail.doc.hide": "Hide",
  "detail.timeline.empty":
    "No events are recorded for this case yet.",
  "detail.timeline.noDate": "Date not recorded",
  "detail.timeline.introHistory":
    "What the court has listed in this matter.",
  "detail.timeline.intro":
    "Oldest first, built only from dates the record carries.",
  "detail.timeline.history": "Hearing history",
  "detail.timeline.title": "Case timeline",
  "detail.orders.explain": "Explain this order",
  "detail.orders.no": "Order No. {n}",
  "detail.orders.empty":
    "No orders are recorded against this case yet.",
  "detail.orders.copy":
    "Recorded by the court in this matter — the docket entry, " +
    "not a copy of the order itself.",
  "detail.orders.title": "Orders passed",
  "detail.docs.empty": "No documents added to this matter yet.",
  "detail.docs.add": "＋ Add documents",
  "detail.docs.uploading": "Uploading…",
  "detail.docs.categoryAria": "Document category",
  "detail.docs.copy":
    "Everything added to this matter. The assigned lawyer " +
    "sees the same list.",
  "detail.docs.title": "Case documents",
  "detail.guidance.error":
    "Guidance could not be reached just now. Try again in a moment.",
  "detail.guidance.ask": "What should I do next?",
  "detail.guidance.asking": "Asking…",
  "detail.daysAtStage": "days at this stage",
  "detail.respondent.other": "respondents",
  "detail.respondent.one": "respondent",
  "detail.daysOnFile": "days on file",
  "detail.registrationDate": "Registration date",
  "detail.firstHearing": "First hearing",
  "detail.schedule": "Schedule",
  "detail.filingNumber": "Filing number",
  "detail.notListed": "Not yet listed",
  "detail.presidingJudge": "Presiding judge",
  "detail.district": "District",
  "detail.court": "Court",
  "detail.section": ", Section {n}",
  "detail.actApplied": "Act applied",
  "detail.petAdvocate": "Petitioner's advocate",
  "detail.parties": "Parties",
  "detail.source.dev": "Development data",
  "detail.source.live": "Live court data",
  "detail.assignedAdvocate": "Assigned advocate",
  "detail.chat": "Chat with assigned lawyer",
  "search.empty.noneBody":
    "We couldn't find any of your cases matching that search. " +
    "Try a different CNR number, petitioner name, or case type.",
  "search.empty.noneTitle": "No cases found",
  "search.empty.savedBody":
    "Search for an existing case by its CNR number in the box " +
    "above, then choose \"Save to My Cases\" to track it here — " +
    "documents, hearings and orders follow the case.",
  "search.empty.savedTitle": "No saved cases yet",
  "search.noFilter": "Only cases you saved to track are shown",
  "search.showing": "Showing your saved cases matching \"{q}\"",
  "search.saved.filtered": "{shown} of {total} saved cases",
  "search.saved.other": "{n} saved cases",
  "search.saved.one": "{n} saved case",
  "search.allTypes": "All Case Types",
  "search.clear": "Clear search",
  "search.placeholder": "Search by CNR, petitioner, case type...",
  "cnr.open": "Open full case",
  "cnr.saved": "Saved to My Cases",
  "cnr.save": "Save to My Cases",
  "cnr.orders.other": "{n} orders passed",
  "cnr.orders.one": "{n} order passed",
  "cnr.hearings.other": "{n} hearings recorded",
  "cnr.hearings.one": "{n} hearing recorded",
  "cnr.submit": "Look up case",
  "cnr.busy": "Looking up…",
  "cnr.err.notFound": "That CNR could not be looked up.",
  "cnr.err.offline":
    "The case service could not be reached. Try again in a moment.",
  "cnr.err.malformed": "That is not a CNR. {hint}",
  "cnr.err.empty": "Enter the CNR of the case you want to open.",
  "cnr.hintFormat": "Four letters then twelve digits, like {example}.",
  "cnr.hintLong": "A CNR is 16 characters — {n} too many.",
  "cnr.hintShort": "A CNR is 16 characters — {n} more to go.",
  "cnr.hintEmpty": "Enter a CNR to search — for example {example}.",
  "cnr.inputLabel": "CNR number",
  "cnr.intro":
    "Every case carries one 16-character CNR — four letters, then " +
    "twelve digits, as printed on a notice or order sheet. The " +
    "record opens here for reading; choose \"Save to My Cases\" to " +
    "start tracking it.",
  "cnr.heading": "Search by CNR number",
  "cnr.label": "LOOK UP A CASE",
  "cases.card.view": "View case",
  "cases.card.advocate": "Advocate:",
  "cases.label.nextHearing": "NEXT HEARING",
  "cases.label.court": "COURT",
  "cases.label.respondents": "RESPONDENTS",
  "cases.label.petitioner": "PETITIONER",
  "cases.label.cnr": "CNR NUMBER",
  "cases.filed": "filed",
  "cases.gone": "This case is no longer in your saved cases.",
  "cases.allCases": "← All cases",
  "cases.hero.copy":
    "Only cases you have saved appear on this page — nobody " +
    "else's. Search by CNR, open a case to read it in full, " +
    "add documents, and speak to the advocate handling it.",
  "cases.hero.titleAccent": "your cases",
  "cases.hero.title1": "Track",
  "cases.eyebrow": "NYAYMITRA MY CASES",
  "cases.backToDashboard": "← Back to Dashboard",
  "chat.error.start": "Could not start the chat.",
  "chat.error.delete": "Conversation not deleted.",
  "chat.error.send": "Message not sent.",
  "chat.error.loadLawyers": "Could not load verified lawyers.",
  "chat.error.openChat": "Could not open the chat.",
  "chat.error.loadConversations": "Could not load conversations.",
  "chat.send": "Send",
  "chat.sending": "Sending…",
  "chat.composer.aria": "Message",
  "chat.composer.placeholder": "Message {name}…",
  "chat.thread.empty": "No messages yet — say hello.",
  "chat.case": "Case {cnr}",
  "chat.placeholder": "Select a conversation to read it.",
  "chat.picker.empty": "No one new to message right now.",
  "chat.picker.title": "Start a conversation",
  "chat.delete.confirm": "Confirm deleting the conversation with {name}",
  "chat.delete.label": "Delete the conversation with {name}",
  "chat.delete.armed": "Delete",
  "chat.noMessages": "No messages yet",
  "chat.you": "You: ",
  "chat.role.admin": "Admin",
  "chat.role.staff": "Staff",
  "chat.role.lawyer": "Lawyer",
  "chat.role.user": "User",
  "chat.category.admins": "Admins",
  "chat.category.fromStaff": "From staff",
  "chat.category.fromLawyers": "From lawyers",
  "chat.category.admin": "Admin",
  "chat.category.staff": "Staff",
  "chat.category.lawyers": "Lawyers",
  "chat.category.clients": "Clients",
  "chat.category.all": "All",
  "chat.empty.with": "No conversations with {who} yet.",
  "chat.empty.from": "No messages {who} yet.",
  "chat.empty.all": "No conversations here yet.",
  "chat.empty.hint": "Start one below, or open a lawyer's profile from Find a Lawyer and press “Chat”.",
  "chat.empty.title": "No conversations yet.",
  "chat.loading": "Loading conversations…",
  "chat.close": "Close",
  "chat.newChat": "＋ New chat",
  "chat.sidebar.title": "Messages",
  "chat.hero.recordNote": "Every message stays inside the case record.",
  "chat.hero.citizen": "a citizen",
  "chat.hero.canMessage": "As {role}, you can message: {list}.",
  "chat.titleAccent": "conversations",
  "chat.title1": "Your",
  "chat.eyebrow": "NYAYMITRA MESSAGES",
  "chat.backToDashboard": "← Back to Dashboard",
  "lawyerProfile.footer": "NyayMitra lawyer information is provided through the connected backend API.",
  "lawyerProfile.hoursUnavailable": "Office hours not available",
  "lawyerProfile.hoursLabel": "WORKING OFFICE HOURS",
  "lawyerProfile.bioUnavailable": "Professional biography not available.",
  "lawyerProfile.bioLabel": "Professional Bio",
  "lawyerProfile.section.overview": "Professional Overview",
  "lawyerProfile.section.additional": "ADDITIONAL INFORMATION",
  "lawyerProfile.block.languages": "Languages Known",
  "lawyerProfile.block.education": "Education Qualifications",
  "lawyerProfile.section.qualifications": "Qualifications",
  "lawyerProfile.section.educationLanguages": "EDUCATION & LANGUAGES",
  "lawyerProfile.field.website": "Website",
  "lawyerProfile.field.preferredContact": "Preferred Contact",
  "lawyerProfile.field.officePhone": "Office Phone",
  "lawyerProfile.field.professionalEmail": "Professional Email",
  "lawyerProfile.field.professionalPhone": "Professional Phone",
  "lawyerProfile.section.professionalContact": "Professional Contact",
  "lawyerProfile.section.contact": "CONTACT",
  "lawyerProfile.officeAddressUnavailable": "Office address not available",
  "lawyerProfile.officeAddressLabel": "OFFICE ADDRESS",
  "lawyerProfile.field.pincode": "Pincode",
  "lawyerProfile.field.city": "City",
  "lawyerProfile.field.district": "District",
  "lawyerProfile.field.state": "State",
  "lawyerProfile.section.professionalLocation": "Professional Location",
  "lawyerProfile.section.officeLocation": "OFFICE & LOCATION",
  "lawyerProfile.block.courtsOfPractice": "Courts of Practice",
  "lawyerProfile.notAvailable": "Not available",
  "lawyerProfile.block.practiceAreas": "Practice Areas",
  "lawyerProfile.years": "{n} years",
  "lawyerProfile.field.yearsOfExperience": "Years of Experience",
  "lawyerProfile.field.yearOfEnrollment": "Year of Enrollment",
  "lawyerProfile.field.barCouncil": "Bar Council",
  "lawyerProfile.field.barId": "Bar ID / Bar Code",
  "lawyerProfile.field.registrationNumber": "Registration Number",
  "lawyerProfile.field.enrollmentNumber": "Enrollment Number",
  "lawyerProfile.section.legalPractice": "Legal Practice",
  "lawyerProfile.section.professional": "PROFESSIONAL INFORMATION",
  "lawyerProfile.field.dob": "Date of Birth",
  "lawyerProfile.field.gender": "Gender",
  "lawyerProfile.field.fullName": "Full Name",
  "lawyerProfile.field.lawyerId": "Lawyer ID",
  "lawyerProfile.section.personal": "Personal Details",
  "lawyerProfile.section.basic": "BASIC INFORMATION",
  "lawyerProfile.summary.currentStatus": "current status",
  "lawyerProfile.summary.profileStatus": "PROFILE STATUS",
  "lawyerProfile.summary.registrationAuthority": "registration authority",
  "lawyerProfile.summary.barCouncil": "BAR COUNCIL",
  "lawyerProfile.summary.barEnrollment": "bar enrollment",
  "lawyerProfile.summary.enrollmentYear": "ENROLLMENT YEAR",
  "lawyerProfile.summary.years": "years",
  "lawyerProfile.summary.experience": "EXPERIENCE",
  "lawyerProfile.editProfile": "Edit profile",
  "lawyerProfile.record.copy": "Everything below is what NyayMitra has on file for you. If something has changed, correct it here.",
  "lawyerProfile.record.label": "YOUR RECORD",
  "lawyerProfile.locationUnavailable": "Location not available",
  "lawyerProfile.legalProfessional": "Legal Professional",
  "lawyerProfile.eyebrow": "NYAYMITRA LAWYER PROFILE",
  "lawyerProfile.back": "← Dashboard",
  "lawyerProfile.edit.field.educationQualifications": "Education qualifications",
  "lawyerProfile.edit.field.languagesKnown": "Languages known",
  "lawyerProfile.edit.field.courtsOfPractice": "Courts of practice",
  "lawyerProfile.edit.field.practiceAreas": "Practice areas",
  "lawyerProfile.edit.field.officeAddress": "Office address",
  "lawyerProfile.edit.field.preferredContact": "Preferred contact method",
  "lawyerProfile.edit.field.officePhone": "Office phone",
  "lawyerProfile.edit.field.professionalPhone": "Professional phone",
  "lawyerProfile.edit.field.professionalEmail": "Professional email",
  "lawyerProfile.edit.field.workingOfficeHours": "Working office hours",
  "lawyerProfile.edit.field.professionalBio": "Professional bio",
  "lawyerProfile.edit.discard": "Discard",
  "lawyerProfile.edit.save": "Save changes",
  "lawyerProfile.edit.onePerLine": "One entry per line",
  "lawyerProfile.edit.readonlyNote": "Enrollment number, registration and bar council are what the council has on record. They are shown for reference and cannot be edited here.",
  "lawyerProfile.edit.detailsHeading": "Correct what has changed",
  "lawyerProfile.edit.detailsLabel": "YOUR DETAILS",
  "lawyerProfile.edit.note": "Corrections are kept on this device and read back everywhere your profile is shown.",
  "lawyerProfile.edit.eyebrow": "EDITING YOUR PROFILE",
  "lawyerProfile.edit.cancelBack": "← Cancel",
  "lawyerProfile.notFound.copy": "No lawyer information was returned by the API.",
  "lawyerProfile.notFound.title": "Lawyer profile not found",
  "lawyerProfile.error.load": "Unable to load lawyer profile.",
  "lawyerProfile.error.title": "Unable to load profile",
  "lawyerProfile.loading.copy": "Fetching professional information from NyayMitra.",
  "lawyerProfile.loading.title": "Loading lawyer profile...",
  "lawyerProfile.backToDashboard": "← Back to Dashboard",
  "lawyer.pagination.next": "Next →",
  "lawyer.pagination.page": "Page {page} of {totalPages}",
  "lawyer.pagination.previous": "← Previous",
  "lawyer.card.viewProfile": "View Profile",
  "lawyer.card.notListed": "Not listed",
  "lawyer.card.languages": "Languages",
  "lawyer.card.enrolled": "enrolled",
  "lawyer.card.location": "location",
  "lawyer.card.experience": "experience",
  "lawyer.card.yrs": "{n} yrs",
  "lawyer.card.generalPractice": "General Practice",
  "lawyer.card.verified": "Verified",
  "lawyer.card.senior": "Senior counsel",
  "lawyer.empty.clear": "Clear filters",
  "lawyer.empty.copy": "Try changing your search or selecting another practice area or city.",
  "lawyer.empty.title": "No lawyers found",
  "lawyer.error.retry": "Retry",
  "lawyer.error.hint": "Start the FastAPI service on port 8000, then try again.",
  "lawyer.error.service": "Unable to reach the NyayMitra lawyer service.",
  "lawyer.error.title": "Lawyer service unavailable",
  "lawyer.results.verified": "Verified profiles",
  "lawyer.results.heading": "Lawyers for your legal needs",
  "lawyer.results.label": "VERIFIED ADVOCATES",
  "lawyer.filters.reset": "Reset filters",
  "lawyer.results.showing": "showing {first}–{last}",
  "lawyer.results.found": "lawyers found",
  "lawyer.filter.allCities": "All cities",
  "lawyer.filter.allPracticeAreas": "All practice areas",
  "lawyer.search.placeholder": "Search lawyer by name...",
  "lawyer.heroCopy": "Search verified lawyers by name, practice area and location — live from the NyayMitra advocate registry.",
  "lawyer.titleAccent": " legal expert.",
  "lawyer.title1": "Find the right",
  "lawyer.eyebrow": "LEGAL PROFESSIONAL NETWORK",
  "lawyer.backToDashboard": "← Back to Dashboard",
};
