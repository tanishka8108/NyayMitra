"""
Tests the full chain: audio -> /api/voice (transcribe) -> /api/translate/indic-to-indic.
Now uses the real Marathi-to-Hindi model instead of the English-only endpoint.
"""
import requests

API_KEY = "nyaymitra-local-test-2026"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def test_voice_then_translate():
    with open("test_audio.wav", "rb") as f:
        voice_response = requests.post(
            "http://localhost:8001/api/voice?target_lang=mr",
            headers=HEADERS,
            files={"audio": f},
        )

    print("----- VOICE STEP -----")
    print(f"Status: {voice_response.status_code}")
    voice_data = voice_response.json()
    print(voice_data)

    if voice_response.status_code != 200:
        print("FAILED at voice step - cannot continue to translation")
        return

    transcribed_text = voice_data["transcribed_text"]

    translate_response = requests.post(
        "http://localhost:8001/api/translate/indic-to-indic",
        headers=HEADERS,
        json={
            "case_id": "voice-chain-test",
            "source_text": transcribed_text,
            "source_lang": "mr",
            "target_lang": "hi",
        },
    )

    print("\n----- TRANSLATION STEP (Marathi -> Hindi) -----")
    print(f"Status: {translate_response.status_code}")
    print(translate_response.json())

if __name__ == "__main__":
    test_voice_then_translate()
