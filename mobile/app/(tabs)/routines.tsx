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

export default function RoutinesScreen() {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);
  const activeBaby = useAppStore((state) => state.activeBaby);

  const { routines, isLoading, isAdding, addRoutine, syncOfflineQueue, offlineQueueCount } =
    useRoutines();

  const [modalVisible, setModalVisible] = useState(false);
  const [selectedType, setSelectedType] = useState('feeding');
  const [amountMl, setAmountMl] = useState('120');
  const [notes, setNotes] = useState('');

  const handleSave = async () => {
    await addRoutine({
      routine_type: selectedType,
      details: selectedType === 'feeding' ? { amount_ml: parseInt(amountMl, 10) || 100 } : {},
      notes,
    });
    setModalVisible(false);
    setNotes('');
  };

  const routineTypes = [
    { id: 'feeding', title: 'Beslenme', icon: '🍼' },
    { id: 'diaper', title: 'Bez', icon: '🚼' },
    { id: 'sleep', title: 'Uyku', icon: '🌙' },
    { id: 'bath', title: 'Banyo', icon: '🛁' },
    { id: 'mood', title: 'Ruh Hali', icon: '👶' },
  ];

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
          onPress={() => setModalVisible(true)}
        />
      </View>

      {/* Offline Sync Banner (if any offline items exist) */}
      {offlineQueueCount > 0 ? (
        <TouchableOpacity
          onPress={syncOfflineQueue}
          style={[styles.syncBanner, { backgroundColor: 'rgba(243, 156, 18, 0.15)' }]}
        >
          <Text style={styles.syncText}>
            ⏳ {offlineQueueCount} çevrimdışı kayıt bekliyor. Eşitlemek için dokunun.
          </Text>
        </TouchableOpacity>
      ) : null}

      {/* Routines List */}
      <FlatList
        data={routines}
        keyExtractor={(item) => item.id.toString()}
        renderItem={({ item }) => <RoutineLogItem log={item} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyIcon}>📋</Text>
            <Text style={[styles.emptyTitle, { color: theme.colors.heading }]}>
              Henüz bir rutin kaydedilmedi.
            </Text>
            <Text style={[styles.emptySub, { color: theme.colors.textMuted }]}>
              İlk beslenme veya uyku kaydınızı ekleyerek başlayabilirsiniz.
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
                    onPress={() => setSelectedType(t.id)}
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
                onPress={() => setModalVisible(false)}
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
    paddingBottom: 16,
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
    marginBottom: 8,
    padding: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  syncText: {
    fontSize: 12,
    color: '#F39C12',
    fontFamily: 'Inter',
    fontWeight: '600',
  },
  list: {
    paddingHorizontal: 20,
    paddingBottom: 80,
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
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
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
