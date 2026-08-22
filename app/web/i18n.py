"""Small English/Hungarian Phase 3 presentation dictionary."""

# ruff: noqa: E501 - translation strings are intentionally kept as whole sentences.

from typing import Literal, cast
from urllib.parse import urlencode

from fastapi import Request

Language = Literal["en", "hu"]

COPY: dict[str, dict[str, str]] = {
    "en": {
        "tagline": "Don't believe it. Investigate it.",
        "eyebrow": "Evidence investigation",
        "lead": "Submit a claim. We search fresh evidence in English and Hungarian, compare what supports and contradicts it, and show where uncertainty remains.",
        "free": "One free investigation — no account required",
        "claim_label": "What should we investigate?",
        "claim_placeholder": "Example: The European Union is planning to prohibit cash payments.",
        "submit": "Investigate the claim",
        "limit": "Maximum 500 characters",
        "step1": "Submit a claim",
        "step2": "We investigate the evidence",
        "step3": "See the assessment",
        "examples": "Example investigations",
        "confirm_title": "Is this what you want me to investigate?",
        "original": "Original claim",
        "interpreted": "Interpreted claim",
        "yes": "Yes, investigate this",
        "no": "No — I'll describe it myself",
        "correct_label": "Corrected claim",
        "correct_submit": "Investigate corrected claim",
        "one_correction": "You can correct the wording once.",
        "progress_title": "Investigation in progress",
        "progress_note": "A careful investigation may take 1–5 minutes. You can keep this page open.",
        "failed": "The investigation could not be completed. No credit was consumed.",
        "result_title": "Investigation result",
        "assessment": "Assessment",
        "balance": "Evidence balance",
        "confidence": "Confidence",
        "pro": "Strongest supporting arguments",
        "contra": "Strongest contradicting arguments",
        "methodology": "How did we reach this result?",
        "method_text": "Truth Hunter searched fresh English and Hungarian sources, extracted relevant evidence, assessed its relevance, strength, quality, independence and recency, then applied versioned deterministic scoring. The evidence balance is not a probability that the claim is true.",
        "metadata": "Investigation metadata",
        "sources": "Evidence and sources",
        "locked": "Detailed evidence excerpts and source URLs will be protected by server-side entitlement when payments are introduced in Phase 5.",
        "new": "Investigate another claim",
        "conflict": "Conflicting evidence detected",
        "insufficient_balance": "Insufficient evidence for a meaningful balance.",
        "not_probability": "not a probability",
        "timestamp": "Timestamp",
        "ai_model": "AI model",
        "search": "Search",
        "sources_analyzed": "Sources analyzed",
        "method": "Method",
        "feedback_question": "Was this investigation helpful?",
        "feedback_note": "Your response helps us improve evidence quality.",
        "helpful": "Helpful",
        "not_helpful": "Not helpful",
        "feedback_thanks": "Thanks — your feedback was recorded.",
    },
    "hu": {
        "tagline": "Ne hidd el. Vizsgáld meg.",
        "eyebrow": "Bizonyítékalapú vizsgálat",
        "lead": "Küldj be egy állítást. Friss magyar és angol bizonyítékokat keresünk, összevetjük az alátámasztó és cáfoló forrásokat, és jelezzük a bizonytalanságot.",
        "free": "Egy ingyenes vizsgálat — regisztráció nélkül",
        "claim_label": "Mit vizsgáljunk meg?",
        "claim_placeholder": "Példa: Az Európai Unió be akarja tiltani a készpénzes fizetést.",
        "submit": "Állítás vizsgálata",
        "limit": "Legfeljebb 500 karakter",
        "step1": "Küldj be egy állítást",
        "step2": "Megvizsgáljuk a bizonyítékokat",
        "step3": "Nézd meg az értékelést",
        "examples": "Példavizsgálatok",
        "confirm_title": "Ezt szeretnéd megvizsgáltatni?",
        "original": "Eredeti állítás",
        "interpreted": "Értelmezett állítás",
        "yes": "Igen, vizsgáld meg",
        "no": "Nem — én fogalmazom meg",
        "correct_label": "Javított állítás",
        "correct_submit": "Javított állítás vizsgálata",
        "one_correction": "A megfogalmazást egyszer javíthatod.",
        "progress_title": "A vizsgálat folyamatban van",
        "progress_note": "Az alapos vizsgálat 1–5 percig is tarthat. Hagyd nyitva ezt az oldalt.",
        "failed": "A vizsgálat nem fejeződött be. Kredit nem került levonásra.",
        "result_title": "Vizsgálati eredmény",
        "assessment": "Értékelés",
        "balance": "Bizonyítékok megoszlása",
        "confidence": "Megbízhatóság",
        "pro": "Legerősebb alátámasztó érvek",
        "contra": "Legerősebb cáfoló érvek",
        "methodology": "Hogyan jutottunk erre az eredményre?",
        "method_text": "A Truth Hunter friss magyar és angol forrásokat keresett, kinyerte a releváns bizonyítékokat, értékelte azok relevanciáját, erejét, minőségét, függetlenségét és frissességét, majd verziózott, determinisztikus pontozást alkalmazott. A bizonyítékok megoszlása nem az állítás igazságának valószínűsége.",
        "metadata": "Vizsgálati metaadatok",
        "sources": "Bizonyítékok és források",
        "locked": "A részletes bizonyítékrészleteket és forráslinkeket az 5. fázisban bevezetett szerveroldali jogosultság védi majd.",
        "new": "Új állítás vizsgálata",
        "conflict": "Ellentmondó bizonyítékot találtunk",
        "insufficient_balance": "Nincs elegendő bizonyíték az érdemi megoszláshoz.",
        "not_probability": "nem valószínűség",
        "timestamp": "Időbélyeg",
        "ai_model": "MI-modell",
        "search": "Keresés",
        "sources_analyzed": "Elemzett források",
        "method": "Módszer",
        "feedback_question": "Hasznos volt ez a vizsgálat?",
        "feedback_note": "A válaszod segít javítani a bizonyítékok minőségét.",
        "helpful": "Hasznos",
        "not_helpful": "Nem hasznos",
        "feedback_thanks": "Köszönjük — a visszajelzésedet rögzítettük.",
    },
}

STATUS_COPY: dict[str, dict[str, str]] = {
    "en": {
        "CREATED": "Understanding claim",
        "INTERPRETING": "Understanding claim",
        "AWAITING_CONFIRMATION": "Waiting for confirmation",
        "SEARCHING": "Searching sources",
        "COLLECTING_SOURCES": "Collecting sources",
        "EVALUATING_EVIDENCE": "Evaluating evidence",
        "CALCULATING_ASSESSMENT": "Comparing evidence",
        "GENERATING_RESULT": "Preparing assessment",
        "COMPLETED": "Assessment ready",
        "FAILED": "Investigation failed",
    },
    "hu": {
        "CREATED": "Az állítás értelmezése",
        "INTERPRETING": "Az állítás értelmezése",
        "AWAITING_CONFIRMATION": "Megerősítésre vár",
        "SEARCHING": "Források keresése",
        "COLLECTING_SOURCES": "Források gyűjtése",
        "EVALUATING_EVIDENCE": "Bizonyítékok értékelése",
        "CALCULATING_ASSESSMENT": "Bizonyítékok összevetése",
        "GENERATING_RESULT": "Értékelés készítése",
        "COMPLETED": "Az értékelés elkészült",
        "FAILED": "A vizsgálat sikertelen",
    },
}

VERDICT_COPY = {
    "en": {
        "TRUE": "True",
        "MOSTLY_TRUE": "Mostly True",
        "MIXED": "Mixed",
        "MOSTLY_FALSE": "Mostly False",
        "FALSE": "False",
        "INCONCLUSIVE": "Inconclusive",
    },
    "hu": {
        "TRUE": "Igaz",
        "MOSTLY_TRUE": "Többnyire igaz",
        "MIXED": "Vegyes",
        "MOSTLY_FALSE": "Többnyire hamis",
        "FALSE": "Hamis",
        "INCONCLUSIVE": "Nem eldönthető",
    },
}

CONFIDENCE_COPY = {
    "en": {"LOW": "Low", "MEDIUM": "Medium", "HIGH": "High"},
    "hu": {"LOW": "Alacsony", "MEDIUM": "Közepes", "HIGH": "Magas"},
}

ACCOUNT_COPY: dict[str, dict[str, str]] = {
    "en": {
        "account": "Account",
        "history_nav": "History",
        "sign_in": "Sign in",
        "register": "Register",
        "create_account": "Create account",
        "email": "Email",
        "password": "Password",
        "password_hint": "Use at least 12 characters.",
        "already_registered": "Already registered?",
        "no_account": "No account?",
        "password_updated": "Password updated. Sign in again.",
        "account_deleted": "Your account and data were deleted. Register again to return.",
        "forgot_password": "Forgot password?",
        "reset_password": "Reset password",
        "request_reset": "Request reset link",
        "new_password": "New password",
        "choose_password": "Choose a new password",
        "update_password": "Update password",
        "check_email": "Check your email",
        "verify_message": "Use the verification link to activate your account.",
        "verification_failed": "Verification failed",
        "request_received": "Request received",
        "reset_message": "If the account exists, a reset link will be sent.",
        "development_link": "Development email link",
        "continue_securely": "Continue securely",
        "development_note": "This link appears only in development mode.",
        "history_title": "Investigation history",
        "no_investigations": "No investigations yet.",
        "investigate_claim": "Investigate a claim",
        "your_account": "Your account",
        "sign_out": "Sign out",
        "delete_title": "Delete account and data",
        "delete_note": "This permanently deletes your investigations and anonymizes the account record.",
        "delete_confirm": "Type DELETE to confirm",
        "delete_button": "Delete account",
        "too_many": "Too many attempts. Try again later.",
        "delete_error": "Type DELETE to confirm.",
        "email_unavailable": "Email delivery is temporarily unavailable. Please try again.",
    },
    "hu": {
        "account": "Fiók",
        "history_nav": "Előzmények",
        "sign_in": "Bejelentkezés",
        "register": "Regisztráció",
        "create_account": "Fiók létrehozása",
        "email": "E-mail-cím",
        "password": "Jelszó",
        "password_hint": "Használj legalább 12 karaktert.",
        "already_registered": "Már regisztráltál?",
        "no_account": "Még nincs fiókod?",
        "password_updated": "A jelszó frissült. Jelentkezz be újra.",
        "account_deleted": "A fiókodat és az adataidat töröltük. A visszatéréshez regisztrálj újra.",
        "forgot_password": "Elfelejtetted a jelszavad?",
        "reset_password": "Jelszó visszaállítása",
        "request_reset": "Visszaállító link kérése",
        "new_password": "Új jelszó",
        "choose_password": "Válassz új jelszót",
        "update_password": "Jelszó frissítése",
        "check_email": "Ellenőrizd az e-mailjeidet",
        "verify_message": "A fiók aktiválásához nyisd meg a megerősítő linket.",
        "verification_failed": "A megerősítés sikertelen",
        "request_received": "A kérést fogadtuk",
        "reset_message": "Ha a fiók létezik, elküldjük a visszaállító linket.",
        "development_link": "Fejlesztői e-mail-link",
        "continue_securely": "Biztonságos folytatás",
        "development_note": "Ez a link csak fejlesztői módban jelenik meg.",
        "history_title": "Vizsgálati előzmények",
        "no_investigations": "Még nincs vizsgálatod.",
        "investigate_claim": "Állítás vizsgálata",
        "your_account": "Saját fiók",
        "sign_out": "Kijelentkezés",
        "delete_title": "Fiók és adatok törlése",
        "delete_note": "Ez véglegesen törli a vizsgálataidat, és anonimizálja a fiók rekordját.",
        "delete_confirm": "A megerősítéshez írd be: DELETE",
        "delete_button": "Fiók törlése",
        "too_many": "Túl sok próbálkozás. Próbáld újra később.",
        "delete_error": "A megerősítéshez írd be: DELETE.",
        "email_unavailable": "Az e-mail-küldés átmenetileg nem érhető el. Próbáld újra.",
    },
}

ACCOUNT_ERROR_COPY: dict[str, dict[str, str]] = {
    "hu": {
        "Enter a valid email address.": "Adj meg egy érvényes e-mail-címet.",
        "Password must contain between 12 and 256 characters.": "A jelszónak 12–256 karakterből kell állnia.",
        "An account with this email already exists.": "Ezzel az e-mail-címmel már létezik fiók.",
        "This email cannot currently be registered.": "Ez az e-mail-cím jelenleg nem regisztrálható.",
        "We couldn't sign you in. Check your email and password. If the account was deleted, register again.": "Nem sikerült bejelentkezni. Ellenőrizd az e-mail-címedet és a jelszavadat. Ha törölted a fiókot, regisztrálj újra.",
        "Verify your email before signing in.": "Bejelentkezés előtt erősítsd meg az e-mail-címedet.",
        "This password-reset link is no longer valid.": "Ez a jelszó-visszaállító link már nem érvényes.",
        "This account link is invalid.": "Ez a fióklink érvénytelen.",
        "This account link is invalid or expired.": "Ez a fióklink érvénytelen vagy lejárt.",
    }
}


def copy_for(language: str | None) -> dict[str, str]:
    return COPY["hu" if language == "hu" else "en"]


def account_copy_for(language: str | None) -> dict[str, str]:
    return ACCOUNT_COPY["hu" if language == "hu" else "en"]


def account_error_for(language: str | None, message: str) -> str:
    if language == "hu":
        return ACCOUNT_ERROR_COPY["hu"].get(message, message)
    return message


def language_from_request(request: Request) -> Language:
    requested = request.query_params.get("lang")
    if requested in {"en", "hu"}:
        request.session["language"] = requested
        return cast(Language, requested)
    selected = request.session.get("language")
    if selected in {"en", "hu"}:
        return cast(Language, selected)
    return "hu" if request.headers.get("accept-language", "").lower().startswith("hu") else "en"


def language_switch_url(request: Request, language: Language) -> str:
    parameters = [
        (key, value) for key, value in request.query_params.multi_items() if key != "lang"
    ]
    parameters.append(("lang", language))
    return f"{request.url.path}?{urlencode(parameters)}"
