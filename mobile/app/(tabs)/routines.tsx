import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Modal,
  ScrollView,
} from 'react-native';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { RoutineLogItem } from '../../components/RoutineLogItem';
import { useRoutines } from '../../features/routines/hooks/useRoutines';
import { triggerHaptic } from '../../lib/haptics';

export default function RoutinesScreen() {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);
  const activeBaby = useAppStore((state) => state.activeBaby);

  const { routines, isLoading, isAdding, addRoutine, syncOfflineQueue, offlineQueueCount } =
    useRoutines();

  const [modalVisible, setModalVisible] = useState(false);
  const [selectedType, setSelectedType] = useState('feeding');
  const [amountMl, setAmountMl] = useState('120');
  const [durationMins, setDurationMins] = useState('45');
  const [notes, setNotes] = useState('');
  const [filterCategory, setFilterCategory] = useState<string>('all');

  const handleSave = async () => {
    triggerHaptic('success');
    await addRoutine({
      routine_type: selectedType,
      details:
        selectedType === 'feeding'
          ? { amount_ml: parseInt(amountMl, 10) || 100 }
          : selectedType === 'sleep'
          ? { duration_minutes: parseInt(durationMins, 10) || 30 }
          : {},
      notes,
    });
    setModalVisible(false);
    setNotes('');
  };

  const openAddModal = (type: string = 'feeding') => {
    triggerHaptic('medium');
    setSelectedType(type);
    setModalVisible(true);
  };

  const handleFilter = (cat: string) => {
    triggerHaptic('selection');
    setFilterCategory(cat);
  };

  const routineTypes = [
    { id: 'feeding', title: 'Beslenme', icon: '🍼' },
    { id: 'diaper', title: 'Bez', icon: '🚼' },
    { id: 'sleep', title: 'Uyku', icon: '🌙' },
    { id: 'bath', title: 'Banyo', icon: '🛁' },
    { id: 'mood', title: 'Ruh Hali', icon: '👶' },
  ];

  // Calculate daily summary metrics
  const totalSleepMinutes = routines
    .filter((r: any) => r.routine_type === 'sleep')
    .reduce((acc: number, curr: any) => acc + (curr.details?.duration_minutes || 45), 0);

  const totalFeedingMl = routines
    .filter((r: any) => r.routine_type === 'feeding')
    .reduce((acc: number, curr: any) => acc + (curr.details?.amount_ml || 100), 0);

  const totalDiapers = routines.filter((r: any) => r.routine_type === 'diaper').length;

  const filteredRoutines = routines.filter((r: any) =>
    filterCategory === 'all' ? true : r.routine_type === filterCategory
  );

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.background }]}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={[styles.title, { color: theme.colors.heading }]}>
            Günlük Rutinler
          </Text>
          <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
            {activeBaby ? `${activeBaby.name}'in günlüğü` : 'Kayıtlar'}
          </Text>
        </View>

        <Button
          title="+ Rutin Ekle"
          size="sm"
          onPress={() => openAddModal('feeding')}
        />
      </View>

      {/* Offline Sync Banner */}
      {offlineQueueCount > 0 ? (
        <TouchableOpacity
          onPress={() => {
            triggerHaptic('warning');
            syncOfflineQueue();
          }}
          style={[styles.syncBanner, { backgroundColor: 'rgba(243, 156, 18, 0.15)' }]}
        >
          <Text style={styles.syncText}>
            ⏳ {offlineQueueCount} çevrimdışı kayıt bekliyor. Eşitlemek için dokunun.
          </Text>
        </TouchableOpacity>
      ) : null}

      {/* Bento-Grid Daily Stats Summary */}
      <View style={styles.bentoContainer}>
        <View
          style={[
            styles.bentoBox,
            { backgroundColor: theme.colors.card, borderColor: theme.colors.border },
          ]}
        >
          <Text style={styles.bentoIcon}>🌙</Text>
          <Text style={[styles.bentoVal, { color: theme.colors.heading }]}>
            {Math.floor(totalSleepMinutes / 60)}s {totalSleepMinutes % 60}d
          </Text>
          <Text style={[styles.bentoLabel, { color: theme.colors.textMuted }]}>
            Toplam Uyku
          </Text>
        </View>

        <View
          style={[
            styles.bentoBox,
            { backgroundColor: theme.colors.card, borderColor: theme.colors.border },
          ]}
        >
          <Text style={styles.bentoIcon}>🍼</Text>
          <Text style={[styles.bentoVal, { color: theme.colors.accent }]}>
            {totalFeedingMl} ml
          </Text>
          <Text style={[styles.bentoLabel, { color: theme.colors.textMuted }]}>
            Beslenme
          </Text>
        </View>

        <View
          style={[
            styles.bentoBox,
            { backgroundColor: theme.colors.card, borderColor: theme.colors.border },
          ]}
        >
          <Text style={styles.bentoIcon}>🚼</Text>
          <Text style={[styles.bentoVal, { color: theme.colors.heading }]}>
            {totalDiapers} adet
          </Text>
          <Text style={[styles.bentoLabel, { color: theme.colors.textMuted }]}>
            Bez Değişimi
          </Text>
        </View>
      </View>

      {/* Category Filter Chips */}
      <View style={styles.filterRow}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {[
            { id: 'all', label: 'Tümü' },
            { id: 'sleep', label: '🌙 Uyku' },
            { id: 'feeding', label: '🍼 Beslenme' },
            { id: 'diaper', label: '🚼 Bez' },
            { id: 'bath', label: '🛁 Banyo' },
          ].map((cat) => {
            const isSelected = filterCategory === cat.id;
            return (
              <TouchableOpacity
                key={cat.id}
                onPress={() => handleFilter(cat.id)}
                style={[
                  styles.filterChip,
                  {
                    backgroundColor: isSelected
                      ? theme.colors.accent
                      : theme.isDark
                      ? '#1D2640'
                      : '#EDE8DF',
                  },
                ]}
              >
                <Text
                  style={[
                    styles.filterChipText,
                    {
                      color: isSelected ? '#141B2E' : theme.colors.text,
                      fontWeight: isSelected ? '700' : '500',
                    },
                  ]}
                >
                  {cat.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {/* Vertical Timeline Routines List */}
      <FlatList
        data={filteredRoutines}
        keyExtractor={(item) => item.id.toString()}
        renderItem={({ item, index }) => (
          <RoutineLogItem
            log={item}
            isFirst={index === 0}
            isLast={index === filteredRoutines.length - 1}
          />
        )}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyIcon}>📋</Text>
            <Text style={[styles.emptyTitle, { color: theme.colors.heading }]}>
              Henüz bu kategoride rutin yok.
            </Text>
            <Text style={[styles.emptySub, { color: theme.colors.textMuted }]}>
              İlk kaydı eklemek için yukarıdaki butona dokunun.
            </Text>
          </View>
        }
      />

      {/* Add Routine Modal */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        transparent
        onRequestClose={() => setModalVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View
            style={[
              styles.modalCard,
              { backgroundColor: theme.colors.card, borderColor: theme.colors.border },
            ]}
          >
            <Text style={[styles.modalTitle, { color: theme.colors.heading }]}>
              Yeni Rutin Kaydı
            </Text>

            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.typeSelector}>
              {routineTypes.map((t) => {
                const isSelected = selectedType === t.id;
                return (
                  <TouchableOpacity
                    key={t.id}
                    onPress={() => {
                      triggerHaptic('selection');
                      setSelectedType(t.id);
                    }}
                    style={[
                      styles.typeChip,
                      {
                        backgroundColor: isSelected
                          ? theme.colors.accent
                          : theme.isDark
                          ? '#25304C'
                          : '#E8EDF5',
                      },
                    ]}
                  >
                    <Text style={styles.typeChipIcon}>{t.icon}</Text>
                    <Text
                      style={[
                        styles.typeChipText,
                        {
                          color: isSelected ? '#141B2E' : theme.colors.text,
                          fontWeight: isSelected ? '700' : '500',
                        },
                      ]}
                    >
                      {t.title}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>

            {selectedType === 'feeding' ? (
              <Input
                label="Miktar (ml)"
                placeholder="120"
                value={amountMl}
                onChangeText={setAmountMl}
                keyboardType="numeric"
              />
            ) : null}

            {selectedType === 'sleep' ? (
              <Input
                label="Uyku Süresi (Dakika)"
                placeholder="45"
                value={durationMins}
                onChangeText={setDurationMins}
                keyboardType="numeric"
              />
            ) : null}

            <Input
              label="Not (Opsiyonel)"
              placeholder="Örn: Rahat uyudu, gazı çıkarıldı."
              value={notes}
              onChangeText={setNotes}
            />

            <View style={styles.modalActions}>
              <Button
                title="Kaydet"
                onPress={handleSave}
                loading={isAdding}
                style={{ flex: 1 }}
              />
              <Button
                title="Vazgeç"
                variant="ghost"
                onPress={() => {
                  triggerHaptic('light');
                  setModalVisible(false);
                }}
              />
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 56,
    paddingBottom: 12,
  },
  title: {
    fontSize: 24,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  subtitle: {
    fontSize: 13,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  syncBanner: {
    marginHorizontal: 20,
    marginBottom: 10,
    padding: 10,
    borderRadius: 12,
    alignItems: 'center',
  },
  syncText: {
    fontSize: 12,
    color: '#F39C12',
    fontFamily: 'Inter',
    fontWeight: '600',
  },
  bentoContainer: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    gap: 10,
    marginBottom: 14,
  },
  bentoBox: {
    flex: 1,
    padding: 12,
    borderRadius: 16,
    borderWidth: 1,
    alignItems: 'center',
  },
  bentoIcon: {
    fontSize: 18,
    marginBottom: 2,
  },
  bentoVal: {
    fontSize: 14,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  bentoLabel: {
    fontSize: 11,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  filterRow: {
    paddingHorizontal: 20,
    marginBottom: 14,
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 14,
    marginRight: 8,
  },
  filterChipText: {
    fontSize: 12,
    fontFamily: 'Inter',
  },
  list: {
    paddingHorizontal: 20,
    paddingBottom: 100,
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
  },
  emptyIcon: {
    fontSize: 40,
    marginBottom: 12,
  },
  emptyTitle: {
    fontSize: 16,
    fontFamily: 'Sora',
    fontWeight: '600',
    marginBottom: 6,
  },
  emptySub: {
    fontSize: 13,
    fontFamily: 'Inter',
    textAlign: 'center',
    paddingHorizontal: 32,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    borderWidth: 1,
    padding: 24,
    paddingBottom: 40,
  },
  modalTitle: {
    fontSize: 18,
    fontFamily: 'Sora',
    fontWeight: '700',
    marginBottom: 16,
  },
  typeSelector: {
    marginBottom: 16,
  },
  typeChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 20,
    marginRight: 8,
  },
  typeChipIcon: {
    fontSize: 16,
    marginRight: 6,
  },
  typeChipText: {
    fontSize: 13,
    fontFamily: 'Inter',
  },
  modalActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginTop: 20,
  },
});
