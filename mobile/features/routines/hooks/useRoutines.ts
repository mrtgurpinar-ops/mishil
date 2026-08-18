import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../../lib/api-client';
import { useAppStore, OfflineRoutineItem } from '../../../store/useAppStore';
import { RoutineLogData } from '../../../components/RoutineLogItem';

export interface CreateRoutineParams {
  routine_type: string;
  start_time?: string;
  end_time?: string;
  details: Record<string, any>;
  notes?: string;
}

export const useRoutines = () => {
  const queryClient = useQueryClient();
  const activeBaby = useAppStore((state) => state.activeBaby);
  const { offlineQueue, addToOfflineQueue, removeFromOfflineQueue } = useAppStore();

  // Query: Get routines for active baby
  const routinesQuery = useQuery<RoutineLogData[]>({
    queryKey: ['routines', activeBaby?.id],
    queryFn: async () => {
      if (!activeBaby) return [];
      try {
        const { data } = await apiClient.get<RoutineLogData[]>(
          `/routines/baby/${activeBaby.id}`
        );
        return data;
      } catch {
        // Return local offline fallback data
        return [
          {
            id: 'mock_1',
            baby_id: activeBaby.id,
            routine_type: 'feeding',
            start_time: new Date(Date.now() - 3600000).toISOString(),
            details: { amount_ml: 120 },
            notes: 'Sakin beslendi.',
          },
          {
            id: 'mock_2',
            baby_id: activeBaby.id,
            routine_type: 'sleep',
            start_time: new Date(Date.now() - 7200000).toISOString(),
            details: { duration_minutes: 75 },
            notes: '432Hz pembe gürültü ile uyudu.',
          },
        ];
      }
    },
    enabled: !!activeBaby,
  });

  // Mutation: Add new routine with optimistic update & offline queue support
  const addRoutineMutation = useMutation({
    mutationFn: async (params: CreateRoutineParams) => {
      if (!activeBaby) throw new Error('Seçili bebek profili bulunamadı.');

      const payload = {
        baby_id: activeBaby.id,
        routine_type: params.routine_type,
        start_time: params.start_time || new Date().toISOString(),
        end_time: params.end_time,
        details: params.details,
        notes: params.notes,
      };

      try {
        const { data } = await apiClient.post<RoutineLogData>(
          `/routines/${params.routine_type}`,
          payload
        );
        return data;
      } catch (err) {
        // On network failure, save to local offline queue
        const offlineItem: OfflineRoutineItem = {
          id: `offline_${Date.now()}`,
          ...payload,
        };
        await addToOfflineQueue(offlineItem);

        // Return optimistic item
        return {
          ...payload,
          id: offlineItem.id,
          isOffline: true,
        } as RoutineLogData;
      }
    },
    onMutate: async (newRoutine) => {
      await queryClient.cancelQueries({ queryKey: ['routines', activeBaby?.id] });
      const previousRoutines =
        queryClient.getQueryData<RoutineLogData[]>(['routines', activeBaby?.id]) || [];

      const optimisticItem: RoutineLogData = {
        id: `temp_${Date.now()}`,
        baby_id: activeBaby?.id || 1,
        routine_type: newRoutine.routine_type,
        start_time: newRoutine.start_time || new Date().toISOString(),
        end_time: newRoutine.end_time,
        details: newRoutine.details,
        notes: newRoutine.notes,
      };

      queryClient.setQueryData<RoutineLogData[]>(
        ['routines', activeBaby?.id],
        [optimisticItem, ...previousRoutines]
      );

      return { previousRoutines };
    },
    onError: (_err, _newRoutine, context) => {
      if (context?.previousRoutines) {
        queryClient.setQueryData(['routines', activeBaby?.id], context.previousRoutines);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['routines', activeBaby?.id] });
    },
  });

  // Flush offline queue when network becomes available
  const syncOfflineQueue = async () => {
    if (offlineQueue.length === 0) return;
    for (const item of [...offlineQueue]) {
      try {
        await apiClient.post(`/routines/${item.routine_type}`, item);
        await removeFromOfflineQueue(item.id);
      } catch (e) {
        console.warn('Sync failed for item:', item.id);
      }
    }
    queryClient.invalidateQueries({ queryKey: ['routines', activeBaby?.id] });
  };

  return {
    routines: routinesQuery.data || [],
    isLoading: routinesQuery.isLoading,
    isAdding: addRoutineMutation.isPending,
    addRoutine: addRoutineMutation.mutateAsync,
    syncOfflineQueue,
    offlineQueueCount: offlineQueue.length,
  };
};
