import { Audio, InterruptionModeIOS, InterruptionModeAndroid } from 'expo-av';

/**
 * Native arka plan ses motoru.
 *
 * WKWebView / Android WebView içindeki <audio> ve Web Audio API ekran kilitlenince
 * durduğu için, ninni/gürültü çalma native tarafa taşındı. WebView yalnızca UI'dır;
 * `AUDIO_PLAY / AUDIO_STOP / AUDIO_TIMER / AUDIO_VOLUME` köprü mesajları buraya düşer.
 *
 * Tek seferde tek parça çalar (uygulamanın davranışı bu). Sesler Railway'den stream
 * edilir; expo-av dosyayı tampona alıp kesintisiz döngüler.
 */

export interface AudioState {
  playing: boolean;
  id: string | null;
  reason?: 'user' | 'timer' | 'error' | 'interrupted';
}

type StateListener = (s: AudioState) => void;

let sound: Audio.Sound | null = null;
let currentId: string | null = null;
let currentVolume = 1.0;
let timer: ReturnType<typeof setTimeout> | null = null;
let modeReady = false;

async function ensureAudioMode() {
  if (modeReady) return;
  await Audio.setAudioModeAsync({
    playsInSilentModeIOS: true,        // sessiz moddayken bile çal (ninni!)
    staysActiveInBackground: true,     // ekran kilitli / arka plan
    interruptionModeIOS: InterruptionModeIOS.DoNotMix,
    interruptionModeAndroid: InterruptionModeAndroid.DoNotMix,
    shouldDuckAndroid: false,
    playThroughEarpieceAndroid: false,
  });
  modeReady = true;
}

function clearTimer() {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
}

async function unloadInternal() {
  clearTimer();
  const s = sound;
  sound = null;
  currentId = null;
  if (s) {
    try {
      await s.stopAsync();
    } catch {}
    try {
      await s.unloadAsync();
    } catch {}
  }
}

export async function playSound(id: string, url: string, onState: StateListener): Promise<void> {
  try {
    await ensureAudioMode();
    await unloadInternal();

    const { sound: snd } = await Audio.Sound.createAsync(
      { uri: url },
      { shouldPlay: true, isLooping: true, volume: currentVolume },
    );
    sound = snd;
    currentId = id;

    snd.setOnPlaybackStatusUpdate((st: any) => {
      if (!st) return;
      if (!st.isLoaded && st.error) {
        onState({ playing: false, id: null, reason: 'error' });
        void unloadInternal();
      }
    });

    onState({ playing: true, id });
  } catch (e) {
    console.log('[nativeAudio] playSound hatası:', e);
    await unloadInternal();
    onState({ playing: false, id: null, reason: 'error' });
  }
}

export async function stopSound(onState: StateListener, reason: AudioState['reason'] = 'user'): Promise<void> {
  await unloadInternal();
  onState({ playing: false, id: null, reason });
}

export async function setVolume(value: number): Promise<void> {
  currentVolume = Math.max(0, Math.min(1, value));
  if (sound) {
    try {
      await sound.setStatusAsync({ volume: currentVolume });
    } catch {}
  }
}

/** minutes <= 0 => zamanlayıcı iptal (sürekli çal) */
export function startTimer(minutes: number, onState: StateListener): void {
  clearTimer();
  if (!minutes || minutes <= 0) return;
  timer = setTimeout(() => {
    void stopSound(onState, 'timer');
  }, minutes * 60000);
}

export function getCurrentId(): string | null {
  return currentId;
}

export async function shutdown(): Promise<void> {
  await unloadInternal();
}
