import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';
import { Card } from '../../components/ui/Card';
import { triggerHaptic } from '../../lib/haptics';
import { apiClient } from '../../lib/api-client';

interface ChatMessage {
  id: string;
  sender: 'user' | 'nanny';
  text: string;
  timestamp: string;
}

const DEFAULT_SUGGESTIONS = [
  '🌙 Uykusunun geldiğini nasıl anlarım?',
  '⚡ 4. ay uyku gerilemesinde ne yapmalıyım?',
  '🍼 Gece beslenmesini nasıl düzenleyebilirim?',
  '🎙️ Bebeğim çok ağlıyor, ne yapmalıyım?',
];

export default function CoachScreen() {
  const router = useRouter();
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);
  const activeBaby = useAppStore((state) => state.activeBaby);

  const babyName = activeBaby?.name || 'Bebeğiniz';
  const babyAge = activeBaby?.age_in_months || 6;

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'nanny',
      text: `🌸 Merhaba sevgili anneciğim/babacığım! Ben Mışıl Dadı. ${babyName}'in sirkadiyen ritmine, ${babyAge}. ayına ve uyku dinamiklerine hakimim. Uykuya direnişler, gece bölünmeleri, atak haftaları veya beslenme düzeniyle ilgili aklınıza takılan her şeyi bana sorabilirsiniz.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);

  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollViewRef = useRef<ScrollView>(null);

  useEffect(() => {
    scrollViewRef.current?.scrollToEnd({ animated: true });
  }, [messages, isLoading]);

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim();
    if (!text || isLoading) return;

    triggerHaptic('medium');
    const userMsgId = `user_${Date.now()}`;
    const newMessages: ChatMessage[] = [
      ...messages,
      {
        id: userMsgId,
        sender: 'user',
        text,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ];

    setMessages(newMessages);
    if (!textToSend) setInputMessage('');
    setIsLoading(true);

    try {
      // Live backend Gemini call
      const { data } = await apiClient.post('/coach/chat', {
        message: text,
        baby_name: babyName,
        baby_age_months: babyAge,
        user_role: 'Anne',
      });

      const replyText = data?.reply || data?.message || 'Bebeğinizin ritmini korumak için odasını loş tutun ve uyanıklık penceresine dikkat edin.';
      setMessages((prev) => [
        ...prev,
        {
          id: `nanny_${Date.now()}`,
          sender: 'nanny',
          text: replyText,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
      triggerHaptic('success');
    } catch (err) {
      // Intelligent offline pediatric fallback
      let fallbackReply = `🌸 ${babyName} için Mışıl Dadı yanınızda!\n\n${babyAge}. ayda bebekler genellikle 90-120 dakikalık uyanıklık pencerelerine sahiptir. Esneme, göz ovuşturma gibi ilk uyku sinyallerini gördüğünüz an yatağına götürmeniz aşırı yorgunluğu önler.`;
      
      if (text.toLowerCase().includes('ağla') || text.toLowerCase().includes('ses')) {
        fallbackReply = `🌸 Ağlama bebeğinizin en doğal iletişim dilidir. Açlık, gaz, aşırı yorgunluk veya ıslak bez olabilir. Dilerseniz Ağlama Analizi sekmemizden bebeğinizin sesini 5 saniye dinleterek ihtiyacını bilimsel olarak tespit edebiliriz.`;
      } else if (text.toLowerCase().includes('atak') || text.toLowerCase().includes('gerileme')) {
        fallbackReply = `⚡ Bu dönem zihinsel bir gelişim sıçraması (Wonder Weeks atağı) olabilir. Bebeğiniz dünyayı yeni bir algıyla deneyimlediği için daha fazla şefkat ve tensel temas arar. Uykusunu 15 dakika erkene almanız rahatlatacaktır.`;
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `nanny_${Date.now()}`,
          sender: 'nanny',
          text: fallbackReply,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={[styles.container, { backgroundColor: theme.colors.background }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={[styles.avatarWrap, { backgroundColor: theme.colors.accent }]}>
            <Text style={{ fontSize: 24 }}>👵</Text>
          </View>
          <View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Text style={[styles.title, { color: theme.colors.heading }]}>
                Mışıl Dadı AI
              </Text>
              <View style={styles.onlineBadge} />
            </View>
            <Text style={[styles.subtitle, { color: theme.colors.textMuted }]}>
              {babyName} ({babyAge} Aylık) • Pediatrik Danışman
            </Text>
          </View>
        </View>

        <TouchableOpacity
          onPress={() => router.push('/(tabs)/cry-analysis')}
          style={[styles.cryShortcutBtn, { backgroundColor: theme.isDark ? '#25304C' : '#E8EDF5' }]}
        >
          <Text style={{ fontSize: 13 }}>🎙️ Ağlama Analizi</Text>
        </TouchableOpacity>
      </View>

      {/* Messages ScrollView */}
      <ScrollView
        ref={scrollViewRef}
        style={styles.chatScroll}
        contentContainerStyle={styles.chatContent}
        showsVerticalScrollIndicator={false}
      >
        {messages.map((msg) => {
          const isNanny = msg.sender === 'nanny';
          return (
            <View
              key={msg.id}
              style={[
                styles.messageRow,
                isNanny ? styles.nannyRow : styles.userRow,
              ]}
            >
              {isNanny ? (
                <View style={styles.miniAvatar}>
                  <Text style={{ fontSize: 16 }}>👵</Text>
                </View>
              ) : null}

              <View
                style={[
                  styles.bubble,
                  isNanny
                    ? [styles.nannyBubble, { backgroundColor: theme.isDark ? '#1F2942' : '#FFFFFF', borderColor: theme.colors.border }]
                    : [styles.userBubble, { backgroundColor: theme.colors.accent }],
                ]}
              >
                <Text
                  style={[
                    styles.messageText,
                    { color: isNanny ? theme.colors.heading : '#141B2E' },
                  ]}
                >
                  {msg.text}
                </Text>
                <Text
                  style={[
                    styles.timestamp,
                    { color: isNanny ? theme.colors.textMuted : 'rgba(20, 27, 46, 0.6)' },
                  ]}
                >
                  {msg.timestamp}
                </Text>
              </View>
            </View>
          );
        })}

        {isLoading ? (
          <View style={[styles.messageRow, styles.nannyRow]}>
            <View style={styles.miniAvatar}>
              <Text style={{ fontSize: 16 }}>👵</Text>
            </View>
            <View
              style={[
                styles.bubble,
                styles.nannyBubble,
                { backgroundColor: theme.isDark ? '#1F2942' : '#FFFFFF', flexDirection: 'row', alignItems: 'center', gap: 8 },
              ]}
            >
              <ActivityIndicator size="small" color={theme.colors.accent} />
              <Text style={[styles.messageText, { color: theme.colors.textMuted }]}>
                Mışıl Dadı düşünüyor...
              </Text>
            </View>
          </View>
        ) : null}

        {/* Quick Suggestions Chips */}
        <View style={styles.suggestionsContainer}>
          <Text style={[styles.suggestionsTitle, { color: theme.colors.textMuted }]}>
            💡 Hızlı Sorular:
          </Text>
          <View style={styles.chipsWrap}>
            {DEFAULT_SUGGESTIONS.map((sug, idx) => (
              <TouchableOpacity
                key={idx}
                onPress={() => handleSendMessage(sug)}
                disabled={isLoading}
                style={[
                  styles.suggestionChip,
                  {
                    backgroundColor: theme.isDark ? '#1F2942' : '#FFFFFF',
                    borderColor: theme.colors.border,
                  },
                ]}
              >
                <Text style={[styles.suggestionText, { color: theme.colors.text }]}>
                  {sug}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </ScrollView>

      {/* Input Bar */}
      <View
        style={[
          styles.inputContainer,
          {
            backgroundColor: theme.isDark ? '#111728' : '#FFFFFF',
            borderTopColor: theme.colors.border,
          },
        ]}
      >
        <TextInput
          style={[
            styles.textInput,
            {
              backgroundColor: theme.isDark ? '#1E2638' : '#F1F4F9',
              color: theme.colors.heading,
              borderColor: theme.colors.border,
            },
          ]}
          placeholder="Mışıl Dadı'ya sorunuzu yazın..."
          placeholderTextColor={theme.colors.textMuted}
          value={inputMessage}
          onChangeText={setInputMessage}
          onSubmitEditing={() => handleSendMessage()}
          returnKeyType="send"
        />

        <TouchableOpacity
          onPress={() => handleSendMessage()}
          disabled={!inputMessage.trim() || isLoading}
          style={[
            styles.sendBtn,
            {
              backgroundColor: inputMessage.trim() && !isLoading ? theme.colors.accent : theme.colors.border,
            },
          ]}
        >
          <Text style={styles.sendIcon}>➤</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 56,
    paddingBottom: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: 'rgba(150, 150, 150, 0.2)',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  avatarWrap: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 18,
    fontFamily: 'Sora',
    fontWeight: '700',
  },
  subtitle: {
    fontSize: 11,
    fontFamily: 'Inter',
    marginTop: 2,
  },
  onlineBadge: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#2ECC71',
  },
  cryShortcutBtn: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 12,
  },
  chatScroll: {
    flex: 1,
  },
  chatContent: {
    padding: 16,
    paddingBottom: 30,
  },
  messageRow: {
    flexDirection: 'row',
    marginVertical: 6,
    alignItems: 'flex-end',
  },
  nannyRow: {
    justifyContent: 'flex-start',
  },
  userRow: {
    justifyContent: 'flex-end',
  },
  miniAvatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#25304C',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
    marginBottom: 4,
  },
  bubble: {
    maxWidth: '82%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
  },
  nannyBubble: {
    borderBottomLeftRadius: 4,
    borderWidth: 1,
  },
  userBubble: {
    borderBottomRightRadius: 4,
  },
  messageText: {
    fontSize: 14,
    fontFamily: 'Inter',
    lineHeight: 20,
  },
  timestamp: {
    fontSize: 10,
    fontFamily: 'Inter',
    marginTop: 4,
    alignSelf: 'flex-end',
  },
  suggestionsContainer: {
    marginTop: 20,
    marginBottom: 10,
  },
  suggestionsTitle: {
    fontSize: 12,
    fontFamily: 'Inter',
    fontWeight: '600',
    marginBottom: 8,
    marginLeft: 4,
  },
  chipsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  suggestionChip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 14,
    borderWidth: 1,
  },
  suggestionText: {
    fontSize: 12,
    fontFamily: 'Inter',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderTopWidth: 1,
    gap: 10,
  },
  textInput: {
    flex: 1,
    height: 44,
    borderRadius: 22,
    paddingHorizontal: 16,
    fontSize: 14,
    fontFamily: 'Inter',
    borderWidth: 1,
  },
  sendBtn: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendIcon: {
    color: '#141B2E',
    fontSize: 16,
    fontWeight: 'bold',
  },
});
