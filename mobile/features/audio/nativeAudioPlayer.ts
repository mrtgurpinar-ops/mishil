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
let userVolume = 1.0;
let currentVolume = 1.0;
let timer: ReturnType<typeof setTimeout> | null = null;
let fadeStartTimer: ReturnType<typeof setTimeout> | null = null;
let fadeInterval: ReturnType<typeof setInterval> | null = null;
let timerGen = 0;
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

function clearFadeOnly() {
  if (fadeStartTimer) {
    clearTimeout(fadeStartTimer);
    fadeStartTimer = null;
  }
  if (fadeInterval) {
    clearInterval(fadeInterval);
    fadeInterval = null;
  }
  currentVolume = userVolume;
}

function clearTimer() {
  timerGen++;
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  clearFadeOnly();
}

async function unloadInternal(keepTimer = false) {
  if (keepTimer) {
    clearFadeOnly();
  } else {
    clearTimer();
  }
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

async function loadAndPlay(id: string, url: string): Promise<void> {
  await ensureAudioMode();
  await unloadInternal(true);
  const { sound: snd } = await Audio.Sound.createAsync(
    { uri: url },
    { shouldPlay: true, isLooping: true, volume: userVolume },
  );
  sound = snd;
  currentId = id;
}

export async function playSound(id: string, url: string, onState: StateListener): Promise<void> {
  // 1. deneme normal URL; hata olursa 2. deneme cache-bust ile (iOS AVPlayer kısmi/bozuk
  // cache'i bazen atlatır). İki deneme de olmazsa 'error'.
  for (let attempt = 0; attempt < 2; attempt++) {
    const tryUrl = attempt === 0 ? url : `${url}${url.includes('?') ? '&' : '?'}rc=${Date.now()}`;
    try {
      await loadAndPlay(id, tryUrl);
      sound?.setOnPlaybackStatusUpdate((st: any) => {
        if (!st) return;
        if (!st.isLoaded && st.error) {
          onState({ playing: false, id: null, reason: 'error' });
          void unloadInternal();
        }
      });
      onState({ playing: true, id });
      return;
    } catch (e) {
      console.log(`[nativeAudio] playSound deneme ${attempt + 1} hatası:`, e);
      await unloadInternal();
    }
  }
  onState({ playing: false, id: null, reason: 'error' });
}

export async function stopSound(onState: StateListener, reason: AudioState['reason'] = 'user'): Promise<void> {
  await unloadInternal();
  onState({ playing: false, id: null, reason });
}

export async function setVolume(value: number, isFadeStep = false): Promise<void> {
  currentVolume = Math.max(0, Math.min(1, value));
  if (!isFadeStep && currentVolume > 0.05) {
    userVolume = currentVolume;
  }
  if (sound) {
    try {
      await sound.setStatusAsync({ volume: currentVolume });
    } catch {}
  }
}

/** minutes <= 0 => zamanlayıcı iptal (sürekli çal) */
export function startTimer(minutes: number, onState: StateListener, fadeOut = true): void {
  clearTimer();
  if (!minutes || minutes <= 0) return;

  const gen = timerGen;
  const totalMs = Math.max(1000, Math.round(minutes * 60000));
  const baseVol = userVolume > 0.05 ? userVolume : 1.0;

  if (fadeOut) {
    const fadeDurationMs = Math.min(30000, Math.floor(totalMs * 0.5));
    const fadeStartDelayMs = Math.max(0, totalMs - fadeDurationMs);
    fadeStartTimer = setTimeout(() => {
      if (gen !== timerGen) return;
      const steps = 20;
      const stepMs = Math.max(250, Math.floor(fadeDurationMs / steps));
      let step = 0;
      fadeInterval = setInterval(() => {
        if (gen !== timerGen || !sound) {
          clearFadeOnly();
          return;
        }
        step++;
        const nextVol = Math.max(0.03, Number((baseVol * (1 - step / steps)).toFixed(2)));
        void setVolume(nextVol, true);
        if (step >= steps && fadeInterval) {
          clearInterval(fadeInterval);
          fadeInterval = null;
        }
      }, stepMs);
    }, fadeStartDelayMs);
  }

  timer = setTimeout(() => {
    if (gen !== timerGen) return;
    if (sound) {
      void stopSound(onState, 'timer');
    } else {
      clearTimer();
    }
  }, totalMs);
}

export function getCurrentId(): string | null {
  return currentId;
}

export async function shutdown(): Promise<void> {
  await unloadInternal();
}
