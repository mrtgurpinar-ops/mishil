import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { format } from 'date-fns';
import { tr } from 'date-fns/locale';
import { useAppStore } from '../store/useAppStore';
import { getTheme } from '../lib/theme';
import { Card } from './ui/Card';

export interface RoutineLogData {
  id: number | string;
  baby_id: number;
  routine_type: string;
  start_time: string;
  end_time?: string;
  details: Record<string, any>;
  notes?: string;
  isOffline?: boolean;
}

interface RoutineLogItemProps {
  log: RoutineLogData;
}

export const RoutineLogItem: React.FC<RoutineLogItemProps> = ({ log }) => {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);

  const getRoutineMeta = (type: string) => {
    switch (type.toLowerCase()) {
      case 'feeding':
        return {
          icon: '🍼',
          title: 'Beslenme',
          subtitle: log.details?.amount_ml
            ? `${log.details.amount_ml} ml mama / anne sütü`
            : log.details?.breast_side
            ? `${log.details.breast_side} göğüs`
            : 'Beslenme kaydedildi',
          color: theme.colors.accent,
        };
      case 'diaper':
        return {
          icon: '🚼',
          title: 'Bez Değişimi',
          subtitle: log.details?.condition || 'Bez temizlendi',
          color: theme.colors.moonBlue,
        };
      case 'sleep':
        return {
          icon: '🌙',
          title: 'Uyku',
          subtitle: log.details?.duration_minutes
            ? `${log.details.duration_minutes} dakika uyku`
            : 'Uyku kaydedildi',
          color: '#9B59B6',
        };
      case 'bath':
        return {
          icon: '🛁',
          title: 'Banyo',
          subtitle: log.details?.temperature || 'Ilık banyo',
          color: theme.colors.info,
        };
      case 'mood':
      default:
        return {
          icon: '👶',
          title: 'Ruh Hali / Aktivite',
          subtitle: log.details?.status || 'Aktivite tamamlandı',
          color: theme.colors.success,
        };
    }
  };

  const meta = getRoutineMeta(log.routine_type);
  const dateObj = new Date(log.start_time);
  const timeFormatted = isNaN(dateObj.getTime())
    ? '--:--'
    : format(dateObj, 'HH:mm', { locale: tr });

  return (
    <Card style={styles.container}>
      <View style={styles.row}>
        <View
          style={[
            styles.iconWrapper,
            { backgroundColor: theme.isDark ? '#25304C' : '#E8EDF5' },
          ]}
        >
          <Text style={styles.icon}>{meta.icon}</Text>
        </View>

        <View style={styles.content}>
          <View style={styles.topLine}>
            <Text style={[styles.title, { color: theme.colors.heading }]}>
              {meta.title}
            </Text>
            <Text style={[styles.time, { color: theme.colors.textMuted }]}>
              {timeFormatted}
            </Text>
          </View>

          <Text style={[styles.subtitle, { color: theme.colors.text }]}>
            {meta.subtitle}
          </Text>

          {log.notes ? (
            <Text style={[styles.notes, { color: theme.colors.textMuted }]}>
              "{log.notes}"
            </Text>
          ) : null}

          {log.isOffline ? (
            <View style={styles.offlineBadge}>
              <Text style={styles.offlineText}>⏳ Çevrimdışı (Eşitlenecek)</Text>
            </View>
          ) : null}
        </View>
      </View>
    </Card>
  );
};

const styles = StyleSheet.create({
  container: {
    marginVertical: 4,
    paddingVertical: 12,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconWrapper: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  icon: {
    fontSize: 20,
  },
  content: {
    flex: 1,
  },
  topLine: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 2,
  },
  title: {
    fontSize: 15,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  time: {
    fontSize: 13,
    fontFamily: 'Inter',
  },
  subtitle: {
    fontSize: 13,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  notes: {
    fontSize: 12,
    fontFamily: 'Inter',
    fontStyle: 'italic',
    marginTop: 4,
  },
  offlineBadge: {
    marginTop: 4,
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(243, 156, 18, 0.15)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  offlineText: {
    fontSize: 10,
    color: '#F39C12',
    fontFamily: 'Inter',
    fontWeight: '600',
  },
});
