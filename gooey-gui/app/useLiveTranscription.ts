import { useEffect, useRef, useState } from "react";
import { fetchServerAPI } from "~/fetchServerAPI";

export type MicState = "idle" | "connecting" | "recording";

type RecordingSession = {
  pc: RTCPeerConnection;
  dc: RTCDataChannel;
  stream: MediaStream;
};

type UseLiveTranscriptionArgs = {
  value: string;
  setValue: (value: string) => void;
  setError: (error: string | null) => void;
};

export function useLiveTranscription({
  value,
  setValue,
  setError,
}: UseLiveTranscriptionArgs) {
  const [micState, setMicState] = useState<MicState>("idle");
  // synchronous lock: react state updates too late to stop a double-click
  // from starting two parallel sessions
  const micBusyRef = useRef(false);
  const recordingRef = useRef<RecordingSession | null>(null);
  const committedTextRef = useRef("");
  const partialTextRef = useRef("");

  const toggleRecording = async () => {
    if (micBusyRef.current) return;
    if (recordingRef.current) {
      stopRecording();
      return;
    }
    micBusyRef.current = true;
    setMicState("connecting");
    setError(null);
    try {
      await startRecording();
      setMicState("recording");
      playCue("start");
    } catch (err) {
      console.error(err);
      stopRecording();
      setError(
        err instanceof Error
          ? err.message
          : "Could not access the microphone. Try again."
      );
    } finally {
      micBusyRef.current = false;
    }
  };

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const pc = new RTCPeerConnection();
    try {
      // seed the transcript with whatever is already typed
      if (value.trim()) {
        committedTextRef.current = value.replace(/\s+$/, "") + " ";
      } else {
        committedTextRef.current = "";
      }
      partialTextRef.current = "";

      // our server mints an ephemeral openai key bound to a transcription
      // session (gpt-live-transcribe); the browser then talks to openai directly
      const { value: ephemeralKey } = await fetchServerAPI<{ value: string }>(
        "/__/asr/live-transcribe/token"
      );

      pc.addTrack(stream.getAudioTracks()[0], stream);
      const dc = pc.createDataChannel("oai-events");
      dc.onmessage = (event) => {
        let msg;
        try {
          msg = JSON.parse(event.data);
        } catch {
          return;
        }
        if (msg.type === "conversation.item.input_audio_transcription.delta") {
          partialTextRef.current += msg.delta || "";
          setValue(committedTextRef.current + partialTextRef.current);
        } else if (
          msg.type === "conversation.item.input_audio_transcription.completed"
        ) {
          const transcript = (msg.transcript || partialTextRef.current).trim();
          if (transcript) {
            committedTextRef.current += transcript + " ";
          }
          partialTextRef.current = "";
          setValue(committedTextRef.current);
        } else if (msg.type === "error") {
          console.error(msg);
          setError("Transcription failed. Try again.");
          stopRecording();
        }
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "failed") {
          setError("Transcription connection failed. Try again.");
          stopRecording();
        }
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const sdpResponse = await fetch(
        "https://api.openai.com/v1/realtime/calls",
        {
          method: "POST",
          body: offer.sdp,
          headers: {
            Authorization: `Bearer ${ephemeralKey}`,
            "Content-Type": "application/sdp",
          },
        }
      );
      if (!sdpResponse.ok) {
        throw new Error(`Transcription connection failed. Try again.`);
      }
      await pc.setRemoteDescription({
        type: "answer",
        sdp: await sdpResponse.text(),
      });

      // the connection isn't live until the data channel opens; flipping the
      // ui to "recording" any earlier makes users speak into a dead mic
      await waitForDataChannelOpen(dc);

      recordingRef.current = { pc, dc, stream };
    } catch (err) {
      for (const track of stream.getTracks()) track.stop();
      pc.close();
      throw err;
    }
  };

  const stopRecording = () => {
    setMicState("idle");
    const rec = recordingRef.current;
    recordingRef.current = null;
    if (!rec) return;
    rec.dc.close();
    rec.pc.close();
    for (const track of rec.stream.getTracks()) track.stop();
    playCue("stop");
  };

  useEffect(() => {
    return stopRecording;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { micState, toggleRecording, stopRecording };
}

// short synthesized earcons so we don't need to ship audio assets:
// mimics the ios dictation cue - a bright pair of pure tones that rise
// when listening starts and fall when it stops
function playCue(kind: "start" | "stop") {
  try {
    const ctx = new AudioContext();
    // bright, high sine notes ~A5 and ~D6 (a perfect fourth) like ios
    let notes;
    if (kind === "start") {
      notes = [880, 1174.66];
    } else {
      notes = [1174.66, 880];
    }
    const noteDuration = 0.085;
    const gap = 0.06;

    notes.forEach((freq, i) => {
      const startAt = ctx.currentTime + i * gap;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      // pure sine keeps it clean and bell-like, matching ios earcons
      osc.type = "sine";
      osc.frequency.value = freq;
      // very fast attack + short decay for a crisp, tight "ping"
      gain.gain.setValueAtTime(0.0001, startAt);
      gain.gain.exponentialRampToValueAtTime(0.14, startAt + 0.004);
      gain.gain.exponentialRampToValueAtTime(0.0001, startAt + noteDuration);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(startAt);
      osc.stop(startAt + noteDuration);
    });

    const totalMs = ((notes.length - 1) * gap + noteDuration) * 1000;
    setTimeout(() => ctx.close(), totalMs + 100);
  } catch (err) {
    // audio cues are best-effort; never let them break recording
    console.error(err);
  }
}

function waitForDataChannelOpen(dc: RTCDataChannel): Promise<void> {
  if (dc.readyState === "open") return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error("Transcription connection timed out. Try again."));
    }, 15000);
    dc.addEventListener("open", () => {
      clearTimeout(timeout);
      resolve();
    });
    const fail = () => {
      clearTimeout(timeout);
      reject(new Error("Transcription connection failed. Try again."));
    };
    dc.addEventListener("error", fail);
    dc.addEventListener("close", fail);
  });
}
