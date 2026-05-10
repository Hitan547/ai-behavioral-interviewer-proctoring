/**
 * AudioRecorder — Browser-native audio recording via MediaRecorder API.
 *
 * Replaces the Streamlit WebRTC AudioCaptureProcessor.
 * Records audio entirely in the browser, producing a Blob that can be
 * uploaded to S3 for server-side transcription.
 */

export type AudioRecorderState = "idle" | "recording" | "stopped" | "error";

export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];
  private _state: AudioRecorderState = "idle";
  private _error: string | null = null;

  get state(): AudioRecorderState {
    return this._state;
  }

  get error(): string | null {
    return this._error;
  }

  /**
   * Reuse the audio track from the camera/microphone permission step.
   * This avoids opening a second microphone stream that some browsers/devices
   * leave muted or inactive.
   *
   * IMPORTANT: We keep the ORIGINAL stream reference — creating a new
   * MediaStream(audioTracks) detaches the tracks and some browsers
   * (Chrome) stop delivering audio data to the copy.
   */
  useStream(stream: MediaStream): boolean {
    const audioTracks = stream.getAudioTracks().filter((track) => track.readyState === "live");
    if (audioTracks.length === 0) {
      console.warn("[AudioRecorder] useStream: No live audio tracks found in stream", {
        allAudioTracks: stream.getAudioTracks().map(t => ({ label: t.label, readyState: t.readyState, muted: t.muted })),
      });
      this._error = "No live microphone track was found.";
      this._state = "error";
      return false;
    }
    // Keep the ORIGINAL stream — do NOT create new MediaStream(audioTracks)
    this.stream = stream;
    this._error = null;
    this._state = "idle";
    console.log("[AudioRecorder] useStream: OK —", audioTracks.length, "live audio track(s)",
      audioTracks.map(t => ({ label: t.label, readyState: t.readyState, muted: t.muted })));
    return true;
  }

  /**
   * Request microphone access and verify it works.
   * Call this during camera_setup phase.
   */
  async requestMicAccess(): Promise<boolean> {
    if (this.stream?.getAudioTracks().some((track) => track.readyState === "live")) {
      return true;
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 48000,
        },
      });
      return true;
    } catch (err) {
      this._error = err instanceof Error ? err.message : "Microphone access denied";
      this._state = "error";
      return false;
    }
  }

  /**
   * Start recording audio from the microphone.
   * Must call requestMicAccess() or useStream() first.
   */
  start(): boolean {
    let stream = this.stream;
    let liveAudioTracks = stream?.getAudioTracks().filter((track) => track.readyState === "live") ?? [];

    console.log("[AudioRecorder] start() called", {
      hasStream: !!stream,
      audioTracks: stream?.getAudioTracks().map(t => ({ label: t.label, readyState: t.readyState, muted: t.muted, enabled: t.enabled })),
      liveCount: liveAudioTracks.length,
    });

    if (!stream || liveAudioTracks.length === 0) {
      console.warn("[AudioRecorder] No live audio tracks — will request fresh mic access");
      this._error = "No microphone stream. Call requestMicAccess() first.";
      this._state = "error";
      return false;
    }

    // Ensure all audio tracks are enabled (some browsers disable them)
    for (const track of liveAudioTracks) {
      if (!track.enabled) {
        console.warn("[AudioRecorder] Re-enabling disabled audio track:", track.label);
        track.enabled = true;
      }
    }

    // Create an audio-only stream for MediaRecorder to avoid recording video
    const audioOnlyStream = new MediaStream(liveAudioTracks);

    // Pick best supported format
    const mimeType = this.getSupportedMimeType();
    if (!mimeType) {
      this._error = "No supported audio recording format found in this browser.";
      this._state = "error";
      return false;
    }

    try {
      this.chunks = [];
      this.mediaRecorder = new MediaRecorder(audioOnlyStream, {
        mimeType,
        audioBitsPerSecond: 128000,
      });

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.chunks.push(event.data);
          if (this.chunks.length <= 3 || this.chunks.length % 10 === 0) {
            console.log(`[AudioRecorder] chunk #${this.chunks.length}: ${event.data.size} bytes`);
          }
        }
      };

      this.mediaRecorder.onerror = (event) => {
        console.error("[AudioRecorder] MediaRecorder error:", event);
        this._state = "error";
        this._error = "Recording failed unexpectedly.";
      };

      this.mediaRecorder.start(250); // collect smaller chunks so short answers are preserved
      this._state = "recording";
      this._error = null;
      console.log("[AudioRecorder] Recording started — mimeType:", mimeType, "state:", this.mediaRecorder.state);
      return true;
    } catch (err) {
      console.error("[AudioRecorder] Failed to start:", err);
      this._error = err instanceof Error ? err.message : "Failed to start recording";
      this._state = "error";
      return false;
    }
  }

  /**
   * Stop recording and return the audio as a Blob.
   * Returns null if no audio was captured.
   */
  stop(): Promise<Blob | null> {
    return new Promise((resolve) => {
      console.log("[AudioRecorder] stop() called", {
        state: this._state,
        hasMediaRecorder: !!this.mediaRecorder,
        mediaRecorderState: this.mediaRecorder?.state,
        chunksCollected: this.chunks.length,
      });

      if (!this.mediaRecorder || this._state !== "recording") {
        console.warn("[AudioRecorder] stop() — not in recording state, returning null");
        this._state = "stopped";
        resolve(null);
        return;
      }

      let settled = false;
      const finish = (blob: Blob | null) => {
        if (settled) return;
        settled = true;
        console.log("[AudioRecorder] stop() finished —", blob ? `${blob.size} bytes, ${this.chunks.length} chunks` : "NO BLOB");
        this.chunks = [];
        resolve(blob);
      };

      this.mediaRecorder.onstop = () => {
        this._state = "stopped";
        if (this.chunks.length === 0) {
          console.warn("[AudioRecorder] onstop fired but 0 chunks collected");
          finish(null);
          return;
        }
        const blob = new Blob(this.chunks, { type: this.mediaRecorder?.mimeType || "audio/webm" });
        console.log("[AudioRecorder] onstop — blob created:", blob.size, "bytes from", this.chunks.length, "chunks");
        finish(blob);
      };

      window.setTimeout(() => {
        if (!settled) {
          console.warn("[AudioRecorder] stop() timed out after 4s — forcing resolve");
        }
        finish(null);
      }, 4000);
      try {
        this.mediaRecorder.requestData();
      } catch {
        // Some browsers throw if requestData races with stop; stop still flushes.
      }
      this.mediaRecorder.stop();
    });
  }

  /**
   * Release all resources (microphone stream).
   */
  destroy(): void {
    if (this.mediaRecorder && this._state === "recording") {
      try {
        this.mediaRecorder.stop();
      } catch {
        // ignore
      }
    }
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    this.mediaRecorder = null;
    this.chunks = [];
    this._state = "idle";
  }

  /**
   * Check if the browser supports audio recording.
   */
  static isSupported(): boolean {
    return Boolean(
      typeof MediaRecorder !== "undefined" &&
        navigator.mediaDevices &&
        navigator.mediaDevices.getUserMedia,
    );
  }

  /**
   * Get the best supported MIME type for audio recording.
   */
  private getSupportedMimeType(): string | null {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/mp4",
    ];
    for (const mime of candidates) {
      if (MediaRecorder.isTypeSupported(mime)) {
        return mime;
      }
    }
    return null;
  }

  /**
   * Get the file extension for the recorded audio.
   */
  getFileExtension(): string {
    const mime = this.mediaRecorder?.mimeType || "";
    if (mime.includes("webm")) return "webm";
    if (mime.includes("ogg")) return "ogg";
    if (mime.includes("mp4")) return "m4a";
    return "webm";
  }
}
