import { useState, useRef, useEffect } from 'react';
import { Audio } from 'expo-av';

const MAX_RECORDING_SECONDS = 30;

export const useCryRecorder = () => {
  const [recording, setRecording] = useState<Audio.Recording | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [meteringLevel, setMeteringLevel] = useState(0);
  const [recordedUri, setRecordedUri] = useState<string | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (recording) {
        recording.stopAndUnloadAsync();
      }
    };
  }, [recording]);

  const requestPermission = async (): Promise<boolean> => {
    const { status } = await Audio.requestPermissionsAsync();
    return status === 'granted';
  };

  const startRecording = async () => {
    try {
      const hasPermission = await requestPermission();
      if (!hasPermission) {
        throw new Error('Mikrofon erişim izni verilmedi.');
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      // Prepare recording options (high quality AAC/M4A)
      const newRecording = new Audio.Recording();
      await newRecording.prepareToRecordAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY
      );

      // Status update callback for metering
      newRecording.setOnRecordingStatusUpdate((status) => {
        if (status.isRecording && status.metering !== undefined) {
          // Normalize dB (-160 to 0) to 0.0 - 1.0 range
          const norm = Math.max(0, (status.metering + 80) / 80);
          setMeteringLevel(norm);
        }
      });
      newRecording.setProgressUpdateInterval(100);

      await newRecording.startAsync();
      setRecording(newRecording);
      setIsRecording(true);
      setRecordingSeconds(0);
      setRecordedUri(null);

      // Start 30-sec limit timer
      timerRef.current = setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev + 1 >= MAX_RECORDING_SECONDS) {
            stopRecording();
            return MAX_RECORDING_SECONDS;
          }
          return prev + 1;
        });
      }, 1000);
    } catch (err: any) {
      console.error('Failed to start cry recording:', err);
      throw err;
    }
  };

  const stopRecording = async (): Promise<string | null> => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (!recording) return null;

    try {
      setIsRecording(false);
      await recording.stopAndUnloadAsync();
      const uri = recording.getURI();
      setRecordedUri(uri);
      setRecording(null);
      return uri;
    } catch (err) {
      console.error('Failed to stop recording:', err);
      return null;
    }
  };

  const cancelRecording = async () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (recording) {
      await recording.stopAndUnloadAsync();
      setRecording(null);
    }
    setIsRecording(false);
    setRecordingSeconds(0);
    setRecordedUri(null);
  };

  return {
    isRecording,
    recordingSeconds,
    meteringLevel,
    recordedUri,
    startRecording,
    stopRecording,
    cancelRecording,
    maxSeconds: MAX_RECORDING_SECONDS,
  };
};
