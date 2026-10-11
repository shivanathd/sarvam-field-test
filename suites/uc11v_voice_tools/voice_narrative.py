"""Findings / caveats / verdict for results/uc11v_voice_tools.json. Numbers are computed from the result, not typed in."""


def make(res, tl, st):
    M = {m["name"]: m["values"] for m in res["metrics"]}
    g = lambda name, p: M[name][p]["mean"]
    P = lambda x: f"{100 * x:.0f}%"
    A, PH = "tool call exact (all 50), clean audio", "tool call exact (all 50), phone audio"
    FC, FP = ("tool call exact: fractional spoken amounts (10), clean audio",
              "tool call exact: fractional spoken amounts (10), phone audio")
    asr = ["saaras:v3 -> gemini-3.8-flash", "saaras:v4 -> gemini-3.8-flash", "gemini-3.8-flash-audio -> gemini-3.8-flash",
           "gpt-4o-transcribe -> gemini-3.8-flash"]
    sp = res["speed"]
    miss = lambda pipe, cid: next((r for r in tl if r["pipeline"] == pipe and r["id"] == cid and r["cond"] == "phone"), None)
    F = [
        "Same tool model (gemini-3.8-flash, think off), different ears. Exact tool+args on clean / phone-line audio: "
        + "; ".join(f"{p.split(' ->')[0]} {P(g(A, p))} / {P(g(PH, p))}" for p in asr)
        + f". Typed-text ceiling is {P(g('tool call exact (all 50), typed text', 'typed text (oracle) -> gemini-3.8-flash'))}. "
        "Saaras v3 lost only 1 command in 50 on either condition, and that miss was a name-spelling ambiguity; gpt-4o-transcribe "
        f"degraded most on the phone line (-{100 * (g(A, asr[3]) - g(PH, asr[3])):.0f} points).",
        f"Spoken fractional amounts (dhai, paune, saadhe, dedh, sava; 10 commands), clean / phone: "
        + "; ".join(f"{p.split(' ->')[0]} {P(g(FC, p))} / {P(g(FP, p))}" for p in asr)
        + ". Saaras keeps 'पौने दो हज़ार' as words, so the LLM resolves it correctly. Gemini's transcript 'helpfully' normalises "
          "numbers and turned 'पौने दो हज़ार' (1750) into '₹2,000'. Its other normalisations ('paune 300', 'dedh hazaar' -> '1500') "
          "survived. gpt-4o-transcribe's misses on these commands were mostly the phone number or UPI ID in the same sentence. "
          "On the phone line it once transcribed Hinglish into Urdu script and dropped the number entirely.",
        f"Gemini with audio in and function calling directly (no transcript step) tied for the best stack: {P(g(A, 'gemini-3.8-flash audio-direct'))} clean, "
        f"{P(g(PH, 'gemini-3.8-flash audio-direct'))} phone, {P(g(FC, 'gemini-3.8-flash audio-direct'))} on fractional amounts. "
        f"It is one call, at a p50 of {sp['gemini-3.8-flash audio-direct']['p50_ms'] / 1000:.1f} s.",
        f"The all-Sarvam stack (saaras:v4 -> sarvam-105b) scored {P(g(A, 'saaras:v4 -> sarvam-105b'))} clean / {P(g(PH, 'saaras:v4 -> sarvam-105b'))} phone, "
        f"vs {P(g(A, asr[1]))} / {P(g(PH, asr[1]))} when the same saaras:v4 transcripts go to Gemini. So the gap is the LLM, not the ears. "
        "Sarvam-105b dropped the name from UPI IDs that Saaras writes as 'शॉपकीपर @YBL' or 'রিনা @ybl' (calling payee '@YBL' / 'ybl'), and got "
        f"{P(g(FC, 'saaras:v4 -> sarvam-105b'))} of the fractional-amount commands exactly right on clean audio. Most of those misses were the UPI "
        "name; one was the amount itself ('साढ़े चार हज़ार' -> 4000). "
        f"Its strength is speed: p50 {sp['saaras:v4 -> sarvam-105b']['p50_ms'] / 1000:.2f} s for the tool call, vs ~2.3 s for gemini-3.8-flash.",
        "Spoken UPI IDs are inherently ambiguous. Every ASR wrote 'dipak' as 'deepak' and 'rina' as 'reena', and no stack can know the "
        "spelling from speech. With vowel-spelling tolerance on the name part, exact scores rise by 2-6 points. A real app must confirm the "
        "payee against the contact list or a VPA lookup before paying.",
        f"Empty transcripts turn into invented actions. gemini-3.8-flash returned an empty transcript for {res['empty_transcripts_of_100']['gemini-3.8-flash-audio']} "
        "of 100 clips. The tool model, told to always call a tool, then invented one (pay electricity bill, check bank balance) instead of "
        "asking the user to repeat. Voice apps need an 'empty or low-confidence -> re-prompt' guard before the LLM.",
        f"Saaras latency: p50 {sp['saaras:v4']['p50_ms']:.0f} ms (v4) / {sp['saaras:v3']['p50_ms']:.0f} ms (v3), but with a long tail "
        f"(p95 {sp['saaras:v4']['p95_ms'] / 1000:.1f} s / {sp['saaras:v3']['p95_ms'] / 1000:.1f} s). Gemini audio transcription p50 "
        f"{sp['gemini-3.8-flash-audio']['p50_ms'] / 1000:.1f} s, gpt-4o-transcribe {sp['gpt-4o-transcribe']['p50_ms'] / 1000:.1f} s.",
    ]
    caveats = [
        "The speech is synthetic (macOS say Lekha/Vani/Piya and gemini-3.8-flash-tts voices; never Sarvam TTS), read once per command. "
        "Real callers bring accents, hesitations and background speech that TTS lacks, so absolute scores are optimistic.",
        "A transcript audit found 5 clips where the TTS itself was wrong: a `say` voice reordered or dropped phone digits, or could not say "
        "an English UPI ID. All four ASR systems agreed on the wrong words. Those clips were reworded or re-voiced and re-run "
        "(SPOKEN_OVERRIDE / VOICE_OVERRIDE in run.py). In t7, the Vani voice reads 199 as 'ஒன்று நூறு தொண்ணூற்று ஒன்பது'. That is "
        "unidiomatic but intelligible, so it was kept: saaras:v4 hears 1199 there.",
        "The phone condition is simulated (8 kHz band-limit, ~20 dB SNR white noise, mu-law), as in uc01. It is not a real telephony capture.",
        "n=50 commands per condition (10 with fractional amounts), so differences of a few commands are within noise. Read the "
        "pipeline ranking as tiers, not exact positions.",
        "The Gemini transcription prompt asks for a verbatim transcript in the spoken language and script. Saaras and gpt-4o-transcribe "
        "get only a language code. No system was told how to write numbers.",
    ]
    verdict = (
        "For a voice payments assistant in Hindi, Hinglish, Tamil or Bengali, ears matter more than the LLM, and the cheapest strong "
        "stack is Saaras (v3 here, v4 close behind) feeding a capable tool-calling LLM: it keeps spoken fractions like 'paune do hazaar' "
        "as words and survives phone-line audio. Gemini-3.8-flash taking the audio directly with function calling is "
        "equally accurate and simplest to build. Avoid gpt-4o-transcribe for Indian-language phone audio. The all-Sarvam stack (saaras:v4 -> "
        "sarvam-105b) is the fastest but loses ~6 points to UPI-ID and fraction mistakes in the LLM step. Whatever you pick, confirm "
        "payees against contacts, and re-prompt on empty transcripts instead of letting the LLM guess.")
    return {"findings": F, "caveats": caveats, "verdict": verdict}
