import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { format } from 'date-fns';
import { tr } from 'date-fns/locale';
import { useAppStore } from '../store/useAppStore';
import { getTheme } from '../lib/theme';

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
  isFirst?: boolean;
  isLast?: boolean;
}

export const RoutineLogItem: React.FC<RoutineLogItemProps> = ({
  log,
  isFirst = false,
  isLast = false,
}) => {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);

  const getRoutineMeta = (type: string) => {
    switch (type.toLowerCase()) {
      case 'feeding':
        return {
          icon: '🍼',
          title: 'Beslenme',
          subtitle: log.details?.amount_ml
            ? `${log.details.amount_ml} ml mama / süt`
            : log.details?.breast_side
            ? `${log.details.breast_side} göğüs`
            : 'Beslenme kaydedildi',
          color: theme.colors.accent,
          bgColor: theme.isDark ? 'rgba(232, 168, 85, 0.15)' : 'rgba(232, 168, 85, 0.12)',
        };
      case 'diaper':
        return {
          icon: '🚼',
          title: 'Bez Değişimi',
          subtitle: log.details?.condition || 'Bez temizlendi',
          color: theme.colors.moonBlue,
          bgColor: theme.isDark ? 'rgba(74, 105, 189, 0.15)' : 'rgba(74, 105, 189, 0.12)',
        };
      case 'sleep':
        return {
          icon: '🌙',
          title: 'Uyku Seansı',
          subtitle: log.details?.duration_minutes
            ? `${log.details.duration_minutes} dakika derin uyku`
            : 'Uyku tamamlandı',
          color: '#A569BD',
          bgColor: theme.isDark ? 'rgba(165, 105, 189, 0.18)' : 'rgba(165, 105, 189, 0.12)',
        };
      case 'bath':
        return {
          icon: '🛁',
          title: 'Banyo',
          subtitle: log.details?.temperature || 'Ilık banyo yapıldı',
          color: theme.colors.info,
          bgColor: theme.isDark ? 'rgba(52, 152, 219, 0.15)' : 'rgba(52, 152, 219, 0.12)',
        };
      case 'mood':
      default:
        return {
          icon: '👶',
          title: 'Aktivite & Ruh Hali',
          subtitle: log.details?.status || 'Oyun / Sakin uyanıklık',
          color: theme.colors.success,
          bgColor: theme.isDark ? 'rgba(78, 186, 134, 0.15)' : 'rgba(78, 186, 134, 0.12)',
        };
    }
  };

  const meta = getRoutineMeta(log.routine_type);
  const dateObj = new Date(log.start_time);
  const timeFormatted = isNaN(dateObj.getTime())
    ? '--:--'
    : format(dateObj, 'HH:mm', { locale: tr });

  return (
    <View style={styles.container}>
      {/* Timeline Column */}
      <View style={styles.timelineCol}>
        <View
          style={[
            styles.timelineNode,
            { backgroundColor: meta.bgColor, borderColor: meta.color },
          ]}
        >
          <Text style={styles.nodeIcon}>{meta.icon}</Text>
        </View>
        {!isLast ? (
          <View
            style={[
              styles.timelineLine,
              { backgroundColor: theme.isDark ? '#2A3656' : '#E5E0D8' },
            ]}
          />
        ) : null}
      </View>

      {/* Routine Content Bento Card */}
      <View
        style={[
          styles.card,
          {
            backgroundColor: theme.colors.card,
            borderColor: theme.colors.border,
          },
        ]}
      >
        <View style={styles.topRow}>
          <Text style={[styles.title, { color: theme.colors.heading }]}>
            {meta.title}
          </Text>
          <View
            style={[
              styles.timeBadge,
              { backgroundColor: theme.isDark ? '#141B2E' : '#EDE8DF' },
            ]}
          >
            <Text style={[styles.timeText, { color: theme.colors.accent }]}>
              {timeFormatted}
            </Text>
          </View>
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
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    marginBottom: 12,
  },
  timelineCol: {
    width: 44,
    alignItems: 'center',
    marginRight: 10,
  },
  timelineNode: {
    width: 36,
    height: 36,
    borderRadius: 18,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 2,
  },
  nodeIcon: {
    fontSize: 16,
  },
  timelineLine: {
    width: 2,
    flex: 1,
    marginTop: 4,
    marginBottom: -8,
  },
  card: {
    flex: 1,
    borderRadius: 16,
    borderWidth: 1,
    padding: 14,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  title: {
    fontSize: 15,
    fontFamily: 'Sora',
    fontWeight: '600',
  },
  timeBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 8,
  },
  timeText: {
    fontSize: 11,
    fontFamily: 'Inter',
    fontWeight: '700',
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
    marginTop: 6,
  },
  offlineBadge: {
    marginTop: 6,
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(243, 156, 18, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
  },
  offlineText: {
    fontSize: 10,
    color: '#F39C12',
    fontFamily: 'Inter',
    fontWeight: '600',
  },
});
