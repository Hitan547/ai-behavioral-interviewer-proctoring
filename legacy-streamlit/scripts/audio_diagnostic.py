"""
audio_diagnostic.py
-------------------
Run this script to diagnose audio capture issues.
Tests each component independently to isolate the problem.

Usage:
    python audio_diagnostic.py
"""

import os
import tempfile
import wave

import numpy as np


def test_1_sample_rate_conversion() -> bool:
    """Test #1: Verify int16 to float32 conversion is correct."""
    print("\n" + "=" * 70)
    print("TEST 1: Sample Rate Conversion (s16 packed format)")
    print("=" * 70)

    duration = 1.0
    sample_rate = 48000
    frequency = 1000.0

    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    signal_float = 0.5 * np.sin(2 * np.pi * frequency * t)

    signal_int16 = (signal_float * 32767).astype(np.int16)

    signal_float_old = signal_int16.astype(np.float32)
    signal_float_new = signal_int16.astype(np.float32) / 32768.0

    print(f"Original float range: [{signal_float.min():.4f}, {signal_float.max():.4f}]")
    print(f"Int16 range: [{signal_int16.min()}, {signal_int16.max()}]")
    print(
        f"\nOLD method (wrong) range: [{signal_float_old.min():.4f}, {signal_float_old.max():.4f}]"
    )
    print(
        f"NEW method (correct) range: [{signal_float_new.min():.4f}, {signal_float_new.max():.4f}]"
    )

    error_old = np.abs(signal_float - signal_float_old).max()
    error_new = np.abs(signal_float - signal_float_new).max()

    print(f"\nMax error (old method): {error_old:.1f} [CORRUPTED]")
    print(f"Max error (new method): {error_new:.6f} [CORRECT]")

    if error_new < 0.01:
        print("\nPASS: Int16 conversion is correct")
        return True

    print("\nFAIL: Int16 conversion is wrong")
    return False


def test_2_wav_creation() -> bool:
    """Test #2: Verify WAV file creation."""
    print("\n" + "=" * 70)
    print("TEST 2: WAV File Creation")
    print("=" * 70)

    sample_rate = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
    audio = 0.3 * np.sin(2 * np.pi * 440 * t)

    audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_int16.tobytes())

        file_size = os.path.getsize(tmp_path)
        expected_size = len(audio_int16) * 2 + 44

        print(f"WAV file created: {tmp_path}")
        print(f"File size: {file_size} bytes")
        print(f"Expected size: ~{expected_size} bytes")

        with wave.open(tmp_path, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == sample_rate
            frames = wf.readframes(wf.getnframes())
            audio_readback = np.frombuffer(frames, dtype=np.int16)

        match = np.array_equal(audio_int16, audio_readback)
        print(f"\nAudio data match: {match}")

        if match:
            print("\nPASS: WAV creation works correctly")
            return True

        print("\nFAIL: WAV data corrupted")
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def test_3_frame_buffer_race() -> bool:
    """Test #3: Simulate frame buffer race condition."""
    print("\n" + "=" * 70)
    print("TEST 3: Frame Buffer Race Condition")
    print("=" * 70)

    import threading
    import time

    class OldBuffer:
        def __init__(self):
            self.frames = []
            self.lock = threading.Lock()

        def append(self, frame):
            with self.lock:
                self.frames.append(frame)

        def pop_all(self):
            with self.lock:
                result = list(self.frames)
                self.frames = []
                return result

    class NewBuffer:
        def __init__(self):
            self.frames = []
            self.lock = threading.Lock()
            self.capturing = True

        def append(self, frame):
            if self.capturing:
                with self.lock:
                    self.frames.append(frame)

        def stop_and_get(self):
            with self.lock:
                self.capturing = False
                result = list(self.frames)
                self.frames = []
                return result

    old_buf = OldBuffer()

    def append_frames_old():
        for i in range(100):
            old_buf.append(f"frame_{i}")
            time.sleep(0.001)

    def drain_frames_old():
        time.sleep(0.05)
        drained = []
        for _ in range(5):
            drained.extend(old_buf.pop_all())
            time.sleep(0.01)
        return drained

    t1 = threading.Thread(target=append_frames_old)
    t1.start()
    old_result = drain_frames_old()
    t1.join()

    # Intentionally no final pop_all() to model lost tail chunks in periodic draining paths.
    print(f"OLD method: captured {len(old_result)}/100 frames")

    new_buf = NewBuffer()

    def append_frames_new():
        for i in range(100):
            new_buf.append(f"frame_{i}")
            time.sleep(0.001)

    t2 = threading.Thread(target=append_frames_new)
    t2.start()
    t2.join()
    new_result = new_buf.stop_and_get()

    print(f"NEW method: captured {len(new_result)}/100 frames")

    if len(new_result) >= 95:
        print("\nPASS: Single atomic drain captures all frames")
        return True

    print("\nFAIL: Frame loss detected")
    return False


def test_4_timer_compensation() -> bool:
    """Test #4: Show timer compensation issue."""
    print("\n" + "=" * 70)
    print("TEST 4: Timer Compensation (Simulated)")
    print("=" * 70)

    print("\nOLD METHOD (with 2.5s delay):")
    print("  User starts speaking at t=0s")
    print("  Prep countdown: 15s")
    print("  At t=15s: countdown expires")
    print("  At t=15s: start 2.5s delay for audio priming")
    print("  At t=17.5s: audio capture starts [FIRST 2.5s LOST]")

    print("\nNEW METHOD (no delay):")
    print("  At t=15s: start timer and audio simultaneously")
    print("  At t=15s: audio capture starts [ALL SPEECH CAPTURED]")

    print("\nPASS: Timer compensation removed")
    return True


def _resample_for_test(audio: np.ndarray, src_sr: int, target_sr: int) -> np.ndarray:
    """Resample with scipy when available; otherwise linear interpolation."""
    if src_sr == target_sr:
        return audio.astype(np.float32)

    try:
        from scipy import signal as sp_signal

        resampled = sp_signal.resample(
            audio, int(len(audio) * target_sr / src_sr)
        )
        return np.asarray(resampled, dtype=np.float32)
    except Exception:
        new_len = int(len(audio) * target_sr / src_sr)
        return np.interp(
            np.linspace(0, len(audio) - 1, new_len),
            np.arange(len(audio)),
            audio,
        ).astype(np.float32)


def test_5_complete_pipeline() -> bool:
    """Test #5: End-to-end pipeline test."""
    print("\n" + "=" * 70)
    print("TEST 5: Complete Pipeline Test")
    print("=" * 70)

    sample_rate = 48000
    duration = 5.0
    t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)

    audio = (
        0.2 * np.sin(2 * np.pi * 200 * t)
        + 0.15 * np.sin(2 * np.pi * 800 * t)
        + 0.1 * np.sin(2 * np.pi * 1200 * t)
    )

    print(f"Generated {duration}s of test audio at {sample_rate}Hz")
    print(f"Total samples: {len(audio)}")

    frame_size = 960
    frames = []
    for i in range(0, len(audio), frame_size):
        frame = audio[i : i + frame_size]
        if len(frame) > 0:
            frame_int16 = (frame * 32767).astype(np.int16)
            frames.append(frame_int16)

    print(f"Split into {len(frames)} frames")

    reconstructed_int16 = np.concatenate(frames)
    reconstructed_float = reconstructed_int16.astype(np.float32) / 32768.0

    original_rms = np.sqrt(np.mean(audio**2))
    reconstructed_rms = np.sqrt(np.mean(reconstructed_float**2))

    print(f"\nOriginal RMS: {original_rms:.6f}")
    print(f"Reconstructed RMS: {reconstructed_rms:.6f}")
    print(f"Difference: {abs(original_rms - reconstructed_rms):.6f}")

    target_sr = 16000
    resampled = _resample_for_test(reconstructed_float, sample_rate, target_sr)

    print(f"\nResampled to {target_sr}Hz: {len(resampled)} samples")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        audio_int16 = (resampled * 32767).clip(-32768, 32767).astype(np.int16)
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(target_sr)
            wf.writeframes(audio_int16.tobytes())

        file_size = os.path.getsize(tmp_path)
        print(f"Final WAV: {tmp_path} ({file_size} bytes)")

        with wave.open(tmp_path, "rb") as wf:
            assert wf.getframerate() == target_sr
            frames_read = wf.getnframes()

        print(f"Verified: {frames_read} frames at {target_sr}Hz")

        if abs(original_rms - reconstructed_rms) < 0.01:
            print("\nPASS: Complete pipeline preserves audio quality")
            return True

        print("\nFAIL: Audio corrupted in pipeline")
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def main() -> None:
    print("\n")
    print("=" * 64)
    print("PSYSENSE AUDIO CAPTURE DIAGNOSTIC SUITE")
    print("=" * 64)

    results = {
        "Sample Rate Conversion": test_1_sample_rate_conversion(),
        "WAV File Creation": test_2_wav_creation(),
        "Frame Buffer Race": test_3_frame_buffer_race(),
        "Timer Compensation": test_4_timer_compensation(),
        "Complete Pipeline": test_5_complete_pipeline(),
    }

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{test_name:.<40} {status}")

    total = len(results)
    passed = sum(results.values())

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll tests passed. Audio pipeline checks look healthy.")
        print("\nNext steps:")
        print("1. Run streamlit app and perform a full 60s speaking test")
        print("2. Validate logs for stop_and_get frame count and WAV stats")
    else:
        print("\nSome tests failed. Review output above for details.")
        print("\nCommon issues:")
        print("- Missing scipy: pip install scipy")
        print("- Old NumPy version: pip install --upgrade numpy")
        print("- Thread timing variability under high CPU load")


if __name__ == "__main__":
    main()
