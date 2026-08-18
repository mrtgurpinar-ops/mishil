import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { format } from 'date-fns';
import { tr } from 'date-fns/locale';

// Configure notification behavior
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export interface ScheduleNotificationParams {
  babyName: string;
  notificationTime: string;
  nextSleepTime: string;
}

export const requestNotificationPermissions = async (): Promise<boolean> => {
  if (Platform.OS === 'web') return false;

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  return finalStatus === 'granted';
};

export const scheduleSleepNotification = async ({
  babyName,
  notificationTime,
  nextSleepTime,
}: ScheduleNotificationParams): Promise<string | null> => {
  if (Platform.OS === 'web') return null;

  const hasPermission = await requestNotificationPermissions();
  if (!hasPermission) return null;

  // Cancel previous scheduled wake-window reminders
  await Notifications.cancelAllScheduledNotificationsAsync();

  const notifDate = new Date(notificationTime);
  const sleepDate = new Date(nextSleepTime);

  // If notification date is already in the past, skip
  if (notifDate.getTime() <= Date.now()) {
    return null;
  }

  const sleepTimeStr = format(sleepDate, 'HH:mm', { locale: tr });

  try {
    const id = await Notifications.scheduleNotificationAsync({
      content: {
        title: `🌙 ${babyName} için Uyku Vakti Yaklaşıyor!`,
        body: `Bir sonraki uyku saati: ${sleepTimeStr} (15 dk kaldı). Odayı loşlaştırıp pışpışlama sesini başlatabilirsiniz.`,
        sound: true,
        data: { type: 'WAKE_WINDOW_REMINDER', babyName },
      },
      trigger: notifDate,
    });
    return id;
  } catch (err) {
    console.warn('Failed to schedule local notification:', err);
    return null;
  }
};
