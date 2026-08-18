import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../../lib/api-client';
import { scheduleSleepNotification } from '../notifications';
import { useAppStore } from '../../../store/useAppStore';

export interface WakeWindowResponse {
  baby_age_months: number;
  base_wake_window_minutes: number;
  adjusted_wake_window_minutes: number;
  is_overtired_risk: boolean;
  overtired_explanation?: string;
  last_wake_time: string;
  next_sleep_time: string;
  notification_time: string;
  daily_total_sleep_hours_recommended: number;
  recommended_daily_nap_count: number;
  remaining_naps_plan: Array<{
    nap_number: number;
    expected_start_time: string;
    expected_duration_minutes: number;
    sleep_type: string;
  }>;
  advice: string;
}

export interface CalculateWakeWindowParams {
  baby_age_months: number;
  last_wake_time: string;
  previous_nap_duration_minutes?: number;
  daily_naps_completed?: number;
}

export const useWakeWindow = () => {
  const queryClient = useQueryClient();
  const activeBaby = useAppStore((state) => state.activeBaby);

  // Calculate Wake Window Mutation
  const calculateMutation = useMutation({
    mutationFn: async (params: CalculateWakeWindowParams) => {
      const { data } = await apiClient.post<WakeWindowResponse>(
        '/wake-window/calculate',
        params
      );
      return data;
    },
    onSuccess: async (data) => {
      queryClient.setQueryData(['wake-window', activeBaby?.id], data);

      // Schedule local push notification 15 mins before next sleep
      if (data.notification_time && activeBaby) {
        await scheduleSleepNotification({
          babyName: activeBaby.name,
          notificationTime: data.notification_time,
          nextSleepTime: data.next_sleep_time,
        });
      }
    },
  });

  // Cached Wake Window Data
  const wakeWindowQuery = useQuery({
    queryKey: ['wake-window', activeBaby?.id],
    queryFn: async () => {
      if (!activeBaby) return null;
      try {
        const { data } = await apiClient.get<WakeWindowResponse>(
          `/wake-window/calculate/baby/${activeBaby.id}`
        );
        return data;
      } catch {
        // Fallback calculation for offline / demo mode
        const now = new Date();
        const nextSleep = new Date(now.getTime() + 120 * 60000);
        const notifTime = new Date(nextSleep.getTime() - 15 * 60000);
        return {
          baby_age_months: activeBaby.age_in_months || 6,
          base_wake_window_minutes: 120,
          adjusted_wake_window_minutes: 120,
          is_overtired_risk: false,
          last_wake_time: now.toISOString(),
          next_sleep_time: nextSleep.toISOString(),
          notification_time: notifTime.toISOString(),
          daily_total_sleep_hours_recommended: 14.0,
          recommended_daily_nap_count: 3,
          remaining_naps_plan: [],
          advice: 'Ortalama 2 saatlik uyanıklık penceresi hedeflenmektedir.',
        } as WakeWindowResponse;
      }
    },
    enabled: !!activeBaby,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });

  return {
    wakeWindowData: wakeWindowQuery.data,
    isLoading: wakeWindowQuery.isLoading || calculateMutation.isPending,
    error: wakeWindowQuery.error || calculateMutation.error,
    calculate: calculateMutation.mutateAsync,
    refetch: wakeWindowQuery.refetch,
  };
};
