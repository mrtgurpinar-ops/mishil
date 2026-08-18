import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../../lib/api-client';
import { useAppStore } from '../../../store/useAppStore';

export interface SubscriptionStatusResponse {
  user_id: number;
  status: 'trial' | 'active' | 'expired' | 'cancelled' | 'grace_period';
  plan?: string;
  trial_ends_at?: string;
  is_active: boolean;
  days_left_in_trial?: number;
}

export const useSubscriptionStatus = () => {
  const queryClient = useQueryClient();
  const isAuthenticated = useAppStore((state) => state.isAuthenticated);

  const statusQuery = useQuery<SubscriptionStatusResponse>({
    queryKey: ['subscription-status'],
    queryFn: async () => {
      try {
        const { data } = await apiClient.get<SubscriptionStatusResponse>(
          '/subscription/status'
        );
        return data;
      } catch {
        // Safe default: Active trial
        return {
          user_id: 1,
          status: 'trial',
          plan: 'yearly',
          is_active: true,
          days_left_in_trial: 3,
        };
      }
    },
    enabled: isAuthenticated,
  });

  const startTrialMutation = useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<SubscriptionStatusResponse>(
        '/subscription/start-trial',
        {}
      );
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['subscription-status'], data);
    },
  });

  return {
    subscription: statusQuery.data,
    isPremiumActive: statusQuery.data?.is_active ?? true,
    isTrial: statusQuery.data?.status === 'trial',
    daysLeftInTrial: statusQuery.data?.days_left_in_trial ?? 3,
    isLoading: statusQuery.isLoading || startTrialMutation.isPending,
    startTrial: startTrialMutation.mutateAsync,
  };
};
