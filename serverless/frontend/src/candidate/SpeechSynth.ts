/**
 * SpeechSynth — Browser-native text-to-speech via SpeechSynthesis API.
 *
 * Replaces the Streamlit server-side speak_question() function.
 * Reads interview questions aloud using the browser's built-in TTS engine.
 */

export class SpeechSynth {
  private utterance: SpeechSynthesisUtterance | null = null;
  private _speaking = false;

  get speaking(): boolean {
    return this._speaking;
  }

  /**
   * Read text aloud. Returns a promise that resolves when speech completes.
   */
  speak(text: string, options?: { rate?: number; pitch?: number; volume?: number }): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!SpeechSynth.isSupported()) {
        // Silently resolve if TTS not supported — interview still works
        resolve();
        return;
      }

      // Cancel any ongoing speech
      this.cancel();

      this.utterance = new SpeechSynthesisUtterance(text);
      this.utterance.rate = options?.rate ?? 0.92;
      this.utterance.pitch = options?.pitch ?? 1.0;
      this.utterance.volume = options?.volume ?? 1.0;
      this.utterance.lang = "en-US";

      // Try to pick a good English voice
      const voices = speechSynthesis.getVoices();
      const preferred = voices.find(
        (v) => v.lang.startsWith("en") && (v.name.includes("Google") || v.name.includes("Microsoft")),
      );
      if (preferred) {
        this.utterance.voice = preferred;
      }

      this.utterance.onstart = () => {
        this._speaking = true;
      };

      this.utterance.onend = () => {
        this._speaking = false;
        resolve();
      };

      this.utterance.onerror = (event) => {
        this._speaking = false;
        // "interrupted" and "canceled" are normal when navigating away
        if (event.error === "interrupted" || event.error === "canceled") {
          resolve();
        } else {
          reject(new Error(`Speech error: ${event.error}`));
        }
      };

      speechSynthesis.speak(this.utterance);
    });
  }

  /**
   * Stop any ongoing speech immediately.
   */
  cancel(): void {
    if (SpeechSynth.isSupported()) {
      speechSynthesis.cancel();
    }
    this._speaking = false;
  }

  /**
   * Check if the browser supports speech synthesis.
   */
  static isSupported(): boolean {
    return typeof speechSynthesis !== "undefined";
  }
}
